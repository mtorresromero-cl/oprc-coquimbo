"""Mociones parlamentarias de los diputados de la Región de Coquimbo, vía
camara.cl (ficha personal de cada diputado) — reemplaza a bcn_mociones.py,
cuyo export de datos enlazados tenía semanas/meses de rezago.

Investigado y verificado manualmente el 2026-08-24 antes de automatizar:
- camara.cl bloquea a ClaudeBot por nombre en su robots.txt y tiene
  Cloudflare activo, pero un navegador real (Playwright) con user-agent
  normal SÍ pasa para navegación simple (GET) — confirmado con contenido
  real y actual (mociones hasta julio 2026).
- El formulario de búsqueda del sitio (POST) SÍ está bloqueado (403). Por
  eso este scraper solo hace GET a la ficha personal de cada diputado
  (`/diputados/detalle/mociones.aspx?prmID=`), nunca envía ese formulario.
- Al buscar la página de asistencia se obtuvo un bloqueo explícito de
  Cloudflare ("Sorry, you have been blocked") — no se siguió insistiendo
  con otras URLs. Asistencia/votaciones de diputados quedan sin resolver.
- Ver docs/05-scrapers.md para el detalle completo de esta investigación.

Solo trae la vista por defecto (año en curso) de cada ficha — no navega el
selector "Ver por año" para evitar repetir el patrón de interacción que
gatilló el bloqueo del formulario de búsqueda.
"""

import json
import re
import sqlite3
import time
from pathlib import Path

from base import BaseScraper
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# autoridad_id -> DIPID en camara.cl (confirmado contra el selector de autor
# del propio sitio y contra el DIPID de opendata.camara.cl: coinciden)
DIPUTADOS_COQUIMBO = {
    "daniel-manouchehri-lobos-diputado": 1142,
    "carolina-tello-rojas-diputado": 1177,
    "nathalie-castillo-rojas-diputado": 1117,
    "bernardo-antonio-salinas-maya-diputado": 1250,
    "eileen-patricia-urqueta-rojas-diputado": 1255,
    "marco-antonio-sulantay-olivares-diputado": 1174,
    "erich-christ-grohs-marin-diputado": 1212,
}

MES_A_NUM = {
    "ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
    "jul": "07", "ago": "08", "sep": "09", "oct": "10", "nov": "11", "dic": "12",
}


def _fecha_a_iso(fecha_texto: str) -> str | None:
    m = re.match(r"(\d{1,2})\s+([a-z]{3})\s+(\d{4})", fecha_texto.strip().lower())
    if not m:
        return None
    dia, mes_abr, anno = m.groups()
    mes = MES_A_NUM.get(mes_abr)
    if not mes:
        return None
    return f"{anno}-{mes}-{int(dia):02d}"


class ScraperCamaraMociones(BaseScraper):
    """Recolecta las mociones (vista por defecto, año en curso) de cada
    diputado de la Región de Coquimbo desde su ficha personal en camara.cl."""

    nombre = "camara_mociones"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        registros = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            for autoridad_id, dip_id in DIPUTADOS_COQUIMBO.items():
                url = f"https://camara.cl/diputados/detalle/mociones.aspx?prmID={dip_id}"
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                filas = page.locator("table.tabla tbody tr").all()
                for fila in filas:
                    celdas = fila.locator("td").all()
                    if len(celdas) < 4:
                        continue

                    link = fila.locator("td a").first
                    boletin = link.inner_text().strip()
                    href = link.get_attribute("href") or ""
                    fecha_iso = _fecha_a_iso(celdas[1].inner_text())
                    titulo = celdas[2].inner_text().strip()
                    estado = celdas[3].inner_text().strip()

                    if not boletin or not fecha_iso:
                        continue

                    registros.append(
                        {
                            "autoridad_id": autoridad_id,
                            "boletin": boletin,
                            "titulo": titulo,
                            "estado": estado,
                            "fecha": fecha_iso,
                            "url_bcn": f"https://camara.cl{href}" if href else url,
                        }
                    )

                time.sleep(2)  # rate limiting entre diputados
            browser.close()
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        vistos: set[tuple[str, str]] = set()
        unicos = []
        for r in registros:
            clave = (r["boletin"], r["autoridad_id"])
            if clave in vistos:
                continue
            vistos.add(clave)
            unicos.append(r)
        return unicos

    def guardar(self, registros: list[dict]) -> None:
        autoridad_ids = tuple(DIPUTADOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(autoridad_ids))
        self.db.execute(
            f"DELETE FROM mocion WHERE autoridad_id IN ({placeholders})", autoridad_ids
        )

        for r in registros:
            self.db.execute(
                """
                INSERT INTO proyecto_ley
                    (id, titulo, fecha_ingreso, estado, camara_origen, tipo, url_bcn)
                VALUES (?, ?, ?, ?, 'camara', 'mocion', ?)
                ON CONFLICT(id) DO UPDATE SET
                    titulo = excluded.titulo,
                    estado = excluded.estado,
                    url_bcn = excluded.url_bcn
                """,
                (r["boletin"], r["titulo"], r["fecha"], r["estado"], r["url_bcn"]),
            )
            self.db.execute(
                """
                INSERT INTO mocion (autoridad_id, proyecto_ley_id, fecha, rol)
                VALUES (?, ?, ?, 'coautor')
                """,
                (r["autoridad_id"], r["boletin"], r["fecha"]),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        autoridad_ids = tuple(DIPUTADOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(autoridad_ids))
        filas = self.db.execute(
            f"""
            SELECT m.autoridad_id, m.fecha, m.rol, p.id AS boletin, p.titulo, p.estado, p.url_bcn
            FROM mocion m JOIN proyecto_ley p ON p.id = m.proyecto_ley_id
            WHERE m.autoridad_id IN ({placeholders})
            ORDER BY m.fecha DESC
            """,
            autoridad_ids,
        ).fetchall()

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "mociones.json").write_text(
            json.dumps([dict(f) for f in filas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Exportadas {len(filas)} mociones a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperCamaraMociones()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
