"""Votaciones de sala de los diputados de la Región de Coquimbo, vía
camara.cl (ficha personal de cada diputado).

Investigado y verificado manualmente el 2026-08-25:
- La ficha de votaciones (`/diputados/detalle/votaciones_sala.aspx?prmId=`)
  responde sin bloqueo con GET simple, igual que la de mociones.
- Es el voto INDIVIDUAL del diputado en cada proyecto, no el resultado ni
  los conteos de toda la Cámara (155 integrantes) — por eso no se guarda
  en votacion_sesion/voto (esas tablas asumen que sabemos el resultado
  agregado de la sesión, que acá no tenemos). Se guarda en voto_diputado,
  un historial personal, igual de honesto sobre lo que sí y no sabemos.
- La lista trae solo la página más reciente (paginada por controles
  __doPostBack, ~10-20 páginas según cuánto lleve votando ese año). No
  navegamos esa paginación — mismo criterio que con mociones y asistencia:
  no repetir el patrón de interacción que gatilló el bloqueo del
  formulario de búsqueda. El historial que guardamos crece semana a
  semana con upsert, pero no es retroactivamente completo desde el inicio
  del período.
- Ver docs/05-scrapers.md para el detalle completo de esta investigación.
"""

import json
import re
import sqlite3
import time
from pathlib import Path

from base import BaseScraper
from camara_mociones import DIPUTADOS_COQUIMBO
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MES_A_NUM = {
    "ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
    "jul": "07", "ago": "08", "sep": "09", "oct": "10", "nov": "11", "dic": "12",
}

VOTO_A_ETIQUETA = {
    "afirmativo": "favor",
    "en contra": "contra",
    "abstención": "abstencion",
    "abstencion": "abstencion",
    "pareo": "pareo",
}


def _fecha_sesion_a_partes(texto: str) -> dict | None:
    # "19 de ago de 2026 - 13:33 - Sesión 60ª"
    patron = r"(\d{1,2}) de ([a-zé]{3}) de (\d{4}) - (\d{2}:\d{2}) - (.+)"
    m = re.match(patron, texto.strip().lower())
    if not m:
        return None
    dia, mes_abr, anno, hora, sesion = m.groups()
    mes = MES_A_NUM.get(mes_abr)
    if not mes:
        return None
    return {"fecha": f"{anno}-{mes}-{int(dia):02d}", "hora": hora, "sesion": sesion.strip()}


def _boletin(texto: str) -> str | None:
    m = re.search(r"(\d{4,6}-\d{1,2})", texto)
    return m.group(1) if m else None


class ScraperCamaraVotaciones(BaseScraper):
    """Recolecta el voto individual reciente de cada diputado de la
    Región de Coquimbo en votaciones de sala, desde su ficha en camara.cl."""

    nombre = "camara_votaciones"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        registros = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for autoridad_id, dip_id in DIPUTADOS_COQUIMBO.items():
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                url = f"https://camara.cl/diputados/detalle/votaciones_sala.aspx?prmId={dip_id}"
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                filas = page.locator("table.tabla tbody tr").all()
                i = 0
                while i < len(filas):
                    celdas = filas[i].locator("td").all()
                    if len(celdas) < 4:
                        i += 1
                        continue

                    boletin = _boletin(celdas[0].inner_text())
                    partes = _fecha_sesion_a_partes(celdas[1].inner_text())
                    voto_raw = celdas[2].inner_text().strip().lower()
                    titulo = ""
                    if i + 1 < len(filas):
                        siguiente = filas[i + 1].locator("td").all()
                        if len(siguiente) == 1:
                            titulo = siguiente[0].inner_text().strip()
                            i += 1

                    i += 1
                    if not boletin or not partes:
                        continue

                    registros.append(
                        {
                            "autoridad_id": autoridad_id,
                            "boletin": boletin,
                            "titulo": titulo,
                            "voto": VOTO_A_ETIQUETA.get(voto_raw, "otro"),
                            "fecha": partes["fecha"],
                            "hora": partes["hora"],
                            "sesion": partes["sesion"],
                            "url_bcn": url,
                        }
                    )

                context.close()
                time.sleep(5)
            browser.close()
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        vistos: set[tuple[str, str, str, str]] = set()
        unicos = []
        for r in registros:
            clave = (r["autoridad_id"], r["boletin"], r["fecha"], r["hora"])
            if clave in vistos:
                continue
            vistos.add(clave)
            unicos.append(r)
        return unicos

    def guardar(self, registros: list[dict]) -> None:
        for r in registros:
            if r["titulo"]:
                self.db.execute(
                    """
                    INSERT INTO proyecto_ley (id, titulo, camara_origen, url_bcn)
                    VALUES (?, ?, 'camara', ?)
                    ON CONFLICT(id) DO UPDATE SET
                        titulo = CASE
                            WHEN excluded.titulo != '' THEN excluded.titulo
                            ELSE proyecto_ley.titulo
                        END
                    """,
                    (r["boletin"], r["titulo"], r["url_bcn"]),
                )
            else:
                # boletín sin título propio en esta fuente (indicación, no el
                # proyecto en sí): solo lo creamos si todavía no existe, para
                # no pisar un título real que ya tengamos de otra fuente.
                self.db.execute(
                    """
                    INSERT OR IGNORE INTO proyecto_ley (id, titulo, camara_origen, url_bcn)
                    VALUES (?, ?, 'camara', ?)
                    """,
                    (r["boletin"], f"Boletín N° {r['boletin']}", r["url_bcn"]),
                )
            self.db.execute(
                """
                INSERT INTO voto_diputado
                    (autoridad_id, proyecto_ley_id, fecha, hora, sesion, voto, fuente_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(autoridad_id, proyecto_ley_id, fecha, hora) DO UPDATE SET
                    voto = excluded.voto,
                    sesion = excluded.sesion,
                    fuente_url = excluded.fuente_url
                """,
                (
                    r["autoridad_id"], r["boletin"], r["fecha"], r["hora"],
                    r["sesion"], r["voto"], r["url_bcn"],
                ),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        autoridad_ids = tuple(DIPUTADOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(autoridad_ids))
        filas = self.db.execute(
            f"""
            SELECT v.autoridad_id, v.fecha, v.hora, v.sesion, v.voto,
                   p.id AS boletin, p.titulo, v.fuente_url
            FROM voto_diputado v JOIN proyecto_ley p ON p.id = v.proyecto_ley_id
            WHERE v.autoridad_id IN ({placeholders})
            ORDER BY v.fecha DESC, v.hora DESC
            """,
            autoridad_ids,
        ).fetchall()

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "votaciones-diputados.json").write_text(
            json.dumps([dict(f) for f in filas], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportados {len(filas)} votos de diputados a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperCamaraVotaciones()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
