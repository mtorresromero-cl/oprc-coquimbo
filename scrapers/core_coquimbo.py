"""Votaciones nominales del Consejo Regional (CORE) de Coquimbo, vía el
buscador de acuerdos propio del CORE (acuerdos.corecoquimbo.cl) — sitio
independiente del gorecoquimbo.cl institucional, con paginación y ficha por
acuerdo accesibles sin JavaScript pesado.

Reutiliza las mismas tablas votacion_sesion/voto que Senado
(scrapers/senado.py), con camara='core' — el CORE también es un cuerpo
colegiado que vota acuerdos, así que el mismo modelo de datos aplica
directamente y la ficha de cada consejero/gobernador en el sitio ya
muestra "Historial de votaciones" sin cambios adicionales.

Solo se recolectan acuerdos recientes (últimos 45 días) — hay más de
10.000 acuerdos históricos desde 2013 en el buscador, muy por fuera del
alcance de un scraper semanal (mismo criterio que "votaciones recientes"
del Senado).
"""

import json
import re
import sqlite3
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from base import BaseScraper
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

BASE_URL = "https://acuerdos.corecoquimbo.cl"
DIAS_ATRAS = 45

CATEGORIA_A_VOTO = [
    (re.compile(r"a favor", re.IGNORECASE), "favor"),
    (re.compile(r"de rechazo", re.IGNORECASE), "contra"),
    (re.compile(r"de abstenci", re.IGNORECASE), "abstencion"),
    (re.compile(r"se inhabilitan", re.IGNORECASE), "inhabilitado"),
    (re.compile(r"no votan", re.IGNORECASE), "ausente"),
]


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.upper().strip()


class ScraperCoreCoquimbo(BaseScraper):
    """Recolecta acuerdos recientes del CORE y el voto nominal de cada
    consejero/gobernador de nuestro catálogo en cada uno."""

    nombre = "core_coquimbo"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        consejeros = self.db.execute(
            "SELECT id, nombre_completo FROM autoridad "
            "WHERE activo = 1 AND cargo IN ('core', 'gobernador')"
        ).fetchall()
        nombre_a_id = {_normalizar(nombre): autoridad_id for autoridad_id, nombre in consejeros}

        fecha_fin = datetime.now()
        fecha_inicio = fecha_fin - timedelta(days=DIAS_ATRAS)
        url_busqueda = (
            f"{BASE_URL}/index.php/busqueda_avanzada/busqueda/1/acuerdos/200/0/"
            f"{fecha_inicio:%d-%m-%Y}/{fecha_fin:%d-%m-%Y}/null/null"
        )

        registros = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url_busqueda, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(1500)
            acuerdo_ids = []
            for a in page.locator("a").all():
                href = a.get_attribute("href") or ""
                if href.startswith("/acuerdos/acuerdo/"):
                    acuerdo_ids.append(href.rsplit("/", 1)[-1])
            page.close()
            print(f"{len(acuerdo_ids)} acuerdos en los últimos {DIAS_ATRAS} días")

            for acuerdo_id in acuerdo_ids:
                try:
                    registro = self._extraer_acuerdo(browser, acuerdo_id, nombre_a_id)
                except Exception as e:
                    print(f"[acuerdo {acuerdo_id}] ERROR: {e}")
                    self.stats["errores"] += 1
                    continue
                if registro:
                    registros.append(registro)
                    print(
                        f"[acuerdo {acuerdo_id}] {registro['fecha']} "
                        f"{len(registro['votos'])} votos de nuestro catálogo"
                    )
                time.sleep(1)
            browser.close()
        return registros

    def _extraer_acuerdo(self, browser, acuerdo_id: str, nombre_a_id: dict) -> dict | None:
        page = browser.new_page(user_agent=USER_AGENT)
        url = f"{BASE_URL}/acuerdos/acuerdo/{acuerdo_id}"
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        texto = page.locator("body").inner_text()
        page.close()

        lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
        idx_breadcrumb = next(
            (i for i, linea in enumerate(lineas) if linea.startswith("Sesiones /")), None
        )
        if idx_breadcrumb is None or idx_breadcrumb + 1 >= len(lineas):
            return None
        sesion_m = re.search(r"Sesión N[ºo°]\s*(\d+)", lineas[idx_breadcrumb])
        numero_sesion = sesion_m.group(1) if sesion_m else None
        titulo = lineas[idx_breadcrumb + 1]

        fecha_m = re.search(r"BIP:\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto)
        if not fecha_m:
            fecha_m = re.search(r"(\d{2}/\d{2}/\d{4})", texto)
        if not fecha_m:
            return None
        fecha_iso = datetime.strptime(fecha_m.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")

        bloque_m = re.search(
            r"ha sido adoptado por(.+?)(?:www\.gorecoquimbo|Descargar acuerdo)", texto, re.DOTALL
        )
        votos = []
        conteos = {"favor": 0, "contra": 0, "abstencion": 0}
        if bloque_m:
            for segmento in bloque_m.group(1).split(";"):
                voto_tipo = next(
                    (v for patron, v in CATEGORIA_A_VOTO if patron.search(segmento)), None
                )
                if voto_tipo is None:
                    continue
                cantidad_m = re.search(r"(\d+)\s*voto", segmento)
                if voto_tipo in conteos and cantidad_m:
                    conteos[voto_tipo] = int(cantidad_m.group(1))

                segmento_norm = _normalizar(segmento)
                for nombre_norm, autoridad_id in nombre_a_id.items():
                    if nombre_norm in segmento_norm:
                        votos.append({"autoridad_id": autoridad_id, "voto": voto_tipo})

        if not votos:
            return None  # ninguna autoridad de nuestro catálogo votó (o no se pudo parsear)

        return {
            "sesion_id": f"core-{acuerdo_id}",
            "fecha": fecha_iso,
            "numero_sesion": numero_sesion,
            "descripcion": titulo,
            "resultado": "aprobado" if conteos["favor"] > conteos["contra"] else "rechazado",
            "votos_favor": conteos["favor"],
            "votos_contra": conteos["contra"],
            "abstenciones": conteos["abstencion"],
            "fuente_url": f"{BASE_URL}/acuerdos/acuerdo/{acuerdo_id}",
            "votos": votos,
        }

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        for r in registros:
            self.db.execute(
                """
                INSERT INTO votacion_sesion
                    (id, camara, fecha, numero_sesion, descripcion, resultado,
                     votos_favor, votos_contra, abstenciones, fuente_url)
                VALUES (?, 'core', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    descripcion = excluded.descripcion,
                    resultado = excluded.resultado,
                    votos_favor = excluded.votos_favor,
                    votos_contra = excluded.votos_contra,
                    abstenciones = excluded.abstenciones
                """,
                (
                    r["sesion_id"], r["fecha"], r["numero_sesion"], r["descripcion"],
                    r["resultado"], r["votos_favor"], r["votos_contra"],
                    r["abstenciones"], r["fuente_url"],
                ),
            )
            for v in r["votos"]:
                self.db.execute(
                    """
                    INSERT INTO voto (autoridad_id, sesion_id, voto, fecha)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(autoridad_id, sesion_id) DO UPDATE SET voto = excluded.voto
                    """,
                    (v["autoridad_id"], r["sesion_id"], v["voto"], r["fecha"]),
                )
                self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        sesiones = self.db.execute(
            "SELECT * FROM votacion_sesion WHERE camara = 'core' ORDER BY fecha DESC"
        ).fetchall()

        salida = []
        for s in sesiones:
            votos = self.db.execute(
                "SELECT autoridad_id, voto FROM voto WHERE sesion_id = ?", (s["id"],)
            ).fetchall()
            salida.append({**dict(s), "votos": [dict(v) for v in votos]})

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "votaciones-core.json").write_text(
            json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportadas {len(salida)} votaciones CORE a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperCoreCoquimbo()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
