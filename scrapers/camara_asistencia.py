"""Asistencia a sala de los diputados de la Región de Coquimbo, vía
quieneseljefe.cl (no camara.cl directo).

Reescrito el 2026-09-03. camara.cl directo se abandonó para esto: la
página de asistencia paginaba por controles __doPostBack (mismo patrón
que gatilló bloqueos en otros scrapers) y solo traíamos "sesiones
recientes", no el período completo. quieneseljefe.cl (ver
docs/06-bitacora.md, entrada del 2026-09-03) publica el registro
completo de sesiones de cada diputado en una sola página HTML estática
(`/diputado/{id}/{slug}`), fetcheable con curl_cffi impersonate="chrome"
sin necesidad de navegador — mismo ID numérico que camara.cl usa
internamente (`prmId`), así que `DIPUTADOS_COQUIMBO` no cambia.

El resumen del período (total, asistencias, ausencias) YA NO lo publica
la fuente calculado — camara.cl sí lo hacía. Se calcula acá mismo a
partir de las filas de sesión, filtrando desde el inicio real de la
legislatura (2026-03-11): quieneseljefe.cl incluye sesiones de enero
2026 (cola de la legislatura anterior) que no corresponden al período
que mostramos.

Pérdida real frente a la versión anterior: no hay detalle de si una
ausencia fue justificada o no (camara.cl sí lo publicaba) — se guarda
todo como "sin justificar" por defecto, columna `ausencias_justificadas`
queda en 0. Se documenta acá para no repetir la investigación.
"""

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from base import BaseScraper
from camara_mociones import DIPUTADOS_COQUIMBO

try:
    from curl_cffi import requests as cffi_requests
except ImportError:  # pragma: no cover
    import sys

    print("Falta curl_cffi: pip install curl_cffi", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

BASE_URL = "https://quieneseljefe.cl"
LEGISLATURA_INICIO = "2026-03-11"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
}


def _session():
    s = cffi_requests.Session(impersonate="chrome")
    s.headers.update(HEADERS)
    return s


class ScraperCamaraAsistencia(BaseScraper):
    """Recolecta el registro de sesiones de cada diputado regional desde
    quieneseljefe.cl y calcula el resumen del período (desde el inicio
    real de la legislatura, 2026-03-11) nosotros mismos."""

    nombre = "camara_asistencia"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        from bs4 import BeautifulSoup

        registros = []
        session = _session()
        for autoridad_id, dip_id in DIPUTADOS_COQUIMBO.items():
            # el slug del nombre no importa para el ruteo del sitio, pero
            # sin uno la página igual redirige/resuelve bien — se prueba
            # con un slug vacío para no depender de tenerlo bien escrito
            url = f"{BASE_URL}/diputado/{dip_id}/x"
            # se pide a quieneseljefe.cl (más liviano), pero lo que se
            # guarda y se muestra en el sitio es la URL oficial de
            # camara.cl — mismo id de diputado en ambos sitios
            url_oficial = f"https://www.camara.cl/diputados/detalle/asistencia_sala.aspx?prmId={dip_id}"
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                print(f"  {autoridad_id}: ERROR cargando página: {e}", flush=True)
                self.stats["errores"] += 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            filas = soup.select("#asi-view-list .dp-asi-row")
            if not filas:
                self.stats["errores"] += 1
                continue

            for fila in filas:
                estado_el = fila.select_one(".dp-asi-row-estado")
                clases = estado_el.get("class", []) if estado_el else []
                if any("upcoming" in c for c in clases):
                    continue  # sesión futura, todavía no ocurre
                fecha_el = fila.select_one(".dp-asi-row-date")
                num_el = fila.select_one(".dp-asi-row-num")
                if not (fecha_el and num_el):
                    continue
                fecha = fecha_el.get_text(strip=True)
                if fecha < LEGISLATURA_INICIO:
                    continue
                numero_sesion = re.sub(r"\D", "", num_el.get_text(strip=True))
                registros.append(
                    {
                        "autoridad_id": autoridad_id,
                        "fecha": fecha,
                        "numero_sesion": numero_sesion,
                        "presente": any("present" in c for c in clases),
                        "justificacion": "",
                        "fuente_url": url_oficial,
                    }
                )
            print(f"  {autoridad_id}: {len(filas)} filas ({len(registros)} acumuladas)", flush=True)
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        anno_actual = date.today().year
        por_autoridad: dict[str, list[dict]] = {}
        for r in registros:
            por_autoridad.setdefault(r["autoridad_id"], []).append(r)
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
                    r["autoridad_id"], r["fecha"], r["numero_sesion"], r["presente"],
                    r["justificacion"], r["fuente_url"],
                ),
            )
            self.stats["nuevos"] += 1

        for autoridad_id, filas in por_autoridad.items():
            total = len(filas)
            asistencias = sum(1 for f in filas if f["presente"])
            self.db.execute(
                """
                INSERT INTO asistencia_resumen
                    (autoridad_id, camara, anno, total_sesiones, sesiones_computables,
                     asistencias, ausencias_justificadas, ausencias_sin_justificar, fuente_url)
                VALUES (?, 'camara', ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(autoridad_id, camara, anno) DO UPDATE SET
                    total_sesiones = excluded.total_sesiones,
                    sesiones_computables = excluded.sesiones_computables,
                    asistencias = excluded.asistencias,
                    ausencias_justificadas = excluded.ausencias_justificadas,
                    ausencias_sin_justificar = excluded.ausencias_sin_justificar,
                    fuente_url = excluded.fuente_url
                """,
                (
                    autoridad_id, anno_actual, total, total, asistencias,
                    total - asistencias, filas[0]["fuente_url"],
                ),
            )
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        autoridad_ids = tuple(DIPUTADOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(autoridad_ids))

        resumen = self.db.execute(
            f"""
            SELECT autoridad_id, camara, anno, total_sesiones, sesiones_computables, asistencias,
                   ausencias_justificadas, ausencias_sin_justificar, fuente_url
            FROM asistencia_resumen
            WHERE camara = 'camara' AND autoridad_id IN ({placeholders})
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
