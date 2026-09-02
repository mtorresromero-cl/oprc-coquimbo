"""Fase 1 de análisis de prensa regional — descubrimiento vía RSS.

Recorre los 28 feeds RSS de medios de la Región de Coquimbo (15 de la Red
Comunales, uno por comuna, más 13 medios externos regionales) y arma un
inventario: título, url, fecha, fuente, comuna (si aplica) y el extracto
que trae el propio RSS. Solo analiza texto — no republica artículos
completos (ver docs/06-bitacora.md para la decisión).

Este scraper SOLO descubre qué noticias existen; no visita cada página
todavía. El texto completo de cada noticia se agrega en una fase
posterior (`prensa_texto.py`, pendiente), que recorre las filas con
`texto_completo IS NULL` de esta misma tabla.

Feeds confirmados funcionando el 2026-09-02. Dos dominios de la Red
Comunales usan "ñ" (elvicuñense.cl, elvileño.cl) — se codifican a
punycode a mano abajo porque `httpx` no hace esa conversión solo; en
Python alcanza con `"elvicuñense.cl".encode("idna")`.
"""

import json
import sqlite3
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

# (nombre del medio, comuna_id o None, url del feed)
FUENTES: list[tuple[str, str | None, str]] = [
    # Red Comunales — 15 medios, uno por comuna
    ("El Comunal", "la-higuera", "https://elcomunal.cl/feed/"),
    ("El Serenense", "la-serena", "https://elserenense.cl/feed/"),
    ("El Coquimbano", "coquimbo", "https://elcoquimbano.cl/feed/"),
    ("El Vicuñense", "vicuna", "https://xn--elvicuense-y9a.cl/feed/"),
    ("El Paihuanino", "paihuano", "https://elpaihuanino.cl/feed/"),
    ("El Andacollino", "andacollo", "https://elandacollino.cl/feed/"),
    ("El Hurtadino", "rio-hurtado", "https://elhurtadino.cl/feed/"),
    ("El Montepatrino", "monte-patria", "https://elmontepatrino.cl/feed/"),
    ("La Perla del Limarí", "ovalle", "https://laperladellimari.cl/feed/"),
    ("El Punitaquino", "punitaqui", "https://elpunitaquino.cl/feed/"),
    ("El Combarbalino", "combarbala", "https://elcombarbalino.cl/feed/"),
    ("El Canelino", "canela", "https://elcanelino.cl/feed/"),
    ("El Illapelino", "illapel", "https://elillapelino.cl/feed/"),
    ("El Salamanquino", "salamanca", "https://elsalamanquino.cl/feed/"),
    ("El Vileño", "los-vilos", "https://xn--elvileo-9za.cl/feed/"),
    # Externos — medios regionales fuera de la Red Comunales, sin comuna fija
    ("Miradio", None, "https://miradiols.cl/feed/"),
    ("Radio Guayacán", None, "https://radioguayacan.cl/feed/"),
    ("Radio Montecarlo", None, "https://radiomontecarlo.cl/feed/"),
    # 4 feeds temáticos del mismo diario — mismo nombre de fuente a
    # propósito, para que cuenten como un solo medio en el análisis (no
    # 4 medios distintos); es normal que termine con más artículos que
    # el resto, porque le leemos 4 feeds en vez de 1
    ("Diario El Día", None, "https://diarioeldia.cl/rss/politica/"),
    ("Diario El Día", None, "https://diarioeldia.cl/rss/region/"),
    ("Diario El Día", None, "https://diarioeldia.cl/rss/pais/"),
    ("Diario El Día", None, "https://diarioeldia.cl/rss/opinion/"),
    ("Diario La Región", None, "https://diariolaregion.cl/feed/"),
    ("El Ovallino", None, "https://elovallino.cl/feed/"),
    ("David Noticias", None, "https://davidnoticias.cl/feed/"),
    ("Elqui Global", None, "https://elquiglobal.cl/feed"),
    ("La Serena Online", None, "https://laserenaonline.cl/feed/"),
    ("El Observatodo", None, "https://www.elobservatodo.cl/rss/noticias"),
]


def _texto(item: ET.Element, tag: str) -> str | None:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _fecha_iso(pubdate: str | None) -> str | None:
    if not pubdate:
        return None
    try:
        return parsedate_to_datetime(pubdate).astimezone(UTC).isoformat()
    except (TypeError, ValueError, IndexError):
        return None


class ScraperPrensaRSS(BaseScraper):
    """Fase 1: descubre noticias nuevas vía RSS. No baja el texto completo."""

    nombre = "prensa_rss"
    frecuencia = "diaria"

    def recolectar(self) -> list[dict]:
        registros = []
        for fuente, comuna_id, url in FUENTES:
            try:
                resp = self.client.get(url, timeout=20, follow_redirects=True)
                resp.raise_for_status()
                raiz = ET.fromstring(resp.text)
            except Exception as e:
                print(f"  [{fuente}] ERROR: {e}", flush=True)
                self.stats["errores"] += 1
                continue

            items = raiz.findall(".//item")
            for item in items:
                link = _texto(item, "link")
                titulo = _texto(item, "title")
                if not link or not titulo:
                    continue
                categorias = [c.text.strip() for c in item.findall("category") if c.text]
                registros.append({
                    "fuente": fuente,
                    "comuna_id": comuna_id,
                    "titulo": titulo,
                    "url": link,
                    "fecha": _fecha_iso(_texto(item, "pubDate")),
                    "extracto": _texto(item, "description"),
                    "categorias": ", ".join(categorias) if categorias else None,
                })
            print(f"  [{fuente}] {len(items)} noticias en el feed", flush=True)
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return [r for r in registros if r["fecha"]]

    def guardar(self, registros: list[dict]) -> None:
        ahora = datetime.now().isoformat()
        for r in registros:
            cur = self.db.execute(
                """
                INSERT INTO prensa_articulo
                    (fuente, comuna_id, titulo, url, fecha, extracto, categorias, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO NOTHING
                """,
                (
                    r["fuente"], r["comuna_id"], r["titulo"], r["url"], r["fecha"],
                    r["extracto"], r["categorias"], ahora,
                ),
            )
            if cur.rowcount:
                self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        filas = self.db.execute(
            """
            SELECT fuente, comuna_id, titulo, url, fecha, extracto, categorias
            FROM prensa_articulo ORDER BY fecha DESC LIMIT 500
            """
        ).fetchall()
        salida = [dict(f) for f in filas]
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "prensa-recientes.json").write_text(
            json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportadas {len(salida)} noticias recientes a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperPrensaRSS()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
