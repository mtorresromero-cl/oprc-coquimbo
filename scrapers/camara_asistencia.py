"""Asistencia a sala de los diputados de la Región de Coquimbo, vía
camara.cl (ficha personal de cada diputado).

Investigado y verificado manualmente el 2026-08-25:
- La ficha de asistencia (`/diputados/detalle/asistencia_sala.aspx?prmId=`)
  responde sin bloqueo con GET simple, igual que la de mociones.
- La página trae dos cosas: (1) un resumen del período ya calculado por
  camara.cl (total de sesiones, asistencias, ausencias justificadas y sin
  justificar) — esto SÍ es el dato completo y oficial; y (2) un detalle de
  sesiones recientes paginado por controles __doPostBack (10 sesiones por
  página, hasta 7+ páginas). No navegamos esa paginación — mismo criterio
  que con mociones: no repetir el patrón de interacción que gatilló el
  bloqueo del formulario de búsqueda. El detalle que guardamos es entonces
  parcial (las sesiones más recientes de cada corrida semanal), pero el
  resumen del período sí es completo y se guarda tal cual lo publica la
  fuente.
- Ver docs/05-scrapers.md para el detalle completo de esta investigación.
"""

import json
import re
import sqlite3
import time
from datetime import date
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
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05", "junio": "06",
    "julio": "07", "agosto": "08", "septiembre": "09", "octubre": "10", "noviembre": "11",
    "diciembre": "12",
}


def _sesion_a_partes(texto: str) -> dict | None:
    # "Sesión 60ª, Legislatura 374ª, 19 Agosto 2026 - de 10:04 a 14:06"
    m = re.match(
        r"Sesión\s+(\d+)ª,\s+Legislatura\s+(\d+)ª,\s+(\d{1,2})\s+([A-Za-zÁ-ú]+)\s+(\d{4})",
        texto.strip(),
    )
    if not m:
        return None
    numero_sesion, _legislatura, dia, mes_nombre, anno = m.groups()
    mes = MES_A_NUM.get(mes_nombre.lower())
    if not mes:
        return None
    return {
        "numero_sesion": numero_sesion,
        "fecha": f"{anno}-{mes}-{int(dia):02d}",
    }


class ScraperCamaraAsistencia(BaseScraper):
    """Recolecta el resumen de asistencia del período y el detalle de
    sesiones recientes de cada diputado de la Región de Coquimbo."""

    nombre = "camara_asistencia"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        registros = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for autoridad_id, dip_id in DIPUTADOS_COQUIMBO.items():
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                url = f"https://camara.cl/diputados/detalle/asistencia_sala.aspx?prmId={dip_id}"
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                tablas = page.locator("table.tabla").all()
                if len(tablas) < 2:
                    self.stats["errores"] += 1
                    context.close()
                    time.sleep(5)
                    continue

                resumen_celdas = tablas[0].locator("tbody tr td").all()
                if len(resumen_celdas) >= 6:
                    resumen = {
                        "tipo": "resumen",
                        "autoridad_id": autoridad_id,
                        "total_sesiones": int(resumen_celdas[0].inner_text().strip()),
                        "sesiones_computables": int(resumen_celdas[1].inner_text().strip()),
                        "asistencias": int(resumen_celdas[2].inner_text().strip()),
                        "ausencias_justif_no_afecta": int(resumen_celdas[3].inner_text().strip()),
                        "ausencias_justif_si_afecta": int(resumen_celdas[4].inner_text().strip()),
                        "ausencias_sin_justificar": int(resumen_celdas[5].inner_text().strip()),
                        "fuente_url": url,
                    }
                    registros.append(resumen)

                filas = tablas[1].locator("tbody tr").all()
                for fila in filas:
                    celdas = fila.locator("td").all()
                    if len(celdas) < 3:
                        continue
                    partes = _sesion_a_partes(celdas[0].inner_text())
                    if not partes:
                        continue
                    registros.append(
                        {
                            "tipo": "sesion",
                            "autoridad_id": autoridad_id,
                            "numero_sesion": partes["numero_sesion"],
                            "fecha": partes["fecha"],
                            "presente": celdas[2].inner_text().strip().lower() == "asiste",
                            "justificacion": (
                                celdas[3].inner_text().strip() if len(celdas) > 3 else ""
                            ),
                            "fuente_url": url,
                        }
                    )

                context.close()
                time.sleep(5)
            browser.close()
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        anno_actual = date.today().year
        for r in registros:
            if r["tipo"] == "resumen":
                self.db.execute(
                    """
                    INSERT INTO asistencia_resumen_diputado
                        (autoridad_id, anno, total_sesiones, sesiones_computables,
                         asistencias, ausencias_justif_no_afecta,
                         ausencias_justif_si_afecta, ausencias_sin_justificar, fuente_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(autoridad_id, anno) DO UPDATE SET
                        total_sesiones = excluded.total_sesiones,
                        sesiones_computables = excluded.sesiones_computables,
                        asistencias = excluded.asistencias,
                        ausencias_justif_no_afecta = excluded.ausencias_justif_no_afecta,
                        ausencias_justif_si_afecta = excluded.ausencias_justif_si_afecta,
                        ausencias_sin_justificar = excluded.ausencias_sin_justificar,
                        fuente_url = excluded.fuente_url
                    """,
                    (
                        r["autoridad_id"],
                        anno_actual,
                        r["total_sesiones"],
                        r["sesiones_computables"],
                        r["asistencias"],
                        r["ausencias_justif_no_afecta"],
                        r["ausencias_justif_si_afecta"],
                        r["ausencias_sin_justificar"],
                        r["fuente_url"],
                    ),
                )
            else:
                self.db.execute(
                    """
                    INSERT INTO asistencia
                        (autoridad_id, camara, fecha, numero_sesion, presente, justificacion,
                         fuente_url)
                    VALUES (?, 'camara', ?, ?, ?, ?, ?)
                    ON CONFLICT(autoridad_id, camara, fecha, numero_sesion) DO UPDATE SET
                        presente = excluded.presente,
                        justificacion = excluded.justificacion,
                        fuente_url = excluded.fuente_url
                    """,
                    (
                        r["autoridad_id"],
                        r["fecha"],
                        r["numero_sesion"],
                        r["presente"],
                        r["justificacion"],
                        r["fuente_url"],
                    ),
                )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        autoridad_ids = tuple(DIPUTADOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(autoridad_ids))

        resumen = self.db.execute(
            f"""
            SELECT autoridad_id, anno, total_sesiones, sesiones_computables, asistencias,
                   ausencias_justif_no_afecta, ausencias_justif_si_afecta,
                   ausencias_sin_justificar, fuente_url
            FROM asistencia_resumen_diputado
            WHERE autoridad_id IN ({placeholders})
            ORDER BY anno DESC
            """,
            autoridad_ids,
        ).fetchall()

        detalle = self.db.execute(
            f"""
            SELECT autoridad_id, fecha, numero_sesion, presente, justificacion, fuente_url
            FROM asistencia
            WHERE autoridad_id IN ({placeholders}) AND camara = 'camara'
            ORDER BY fecha DESC
            """,
            autoridad_ids,
        ).fetchall()

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "asistencia-resumen-diputados.json").write_text(
            json.dumps([dict(f) for f in resumen], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (PROCESSED_DIR / "asistencia-diputados.json").write_text(
            json.dumps([dict(f) for f in detalle], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportados {len(resumen)} resúmenes y {len(detalle)} sesiones a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperCamaraAsistencia()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
