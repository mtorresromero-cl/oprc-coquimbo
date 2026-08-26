"""Mociones parlamentarias de los senadores de la Región de Coquimbo, vía
tramitacion.senado.cl (buscador de "Autores" del sitio de tramitación).

Investigado el 2026-08-25, a partir de una pregunta directa: "¿los
senadores no tienen mociones?". La ficha personal de cada senador en
senado.cl no las muestra, pero el buscador de tramitación sí — se
encontró navegando manualmente Autores → filtrar por "Senador" → abrir un
autor, e inspeccionando la request real que dispara esa acción (no
adivinada): el listado de un autor se carga con

    GET https://tramitacion.senado.cl/appsenado/index.php
        ?mo=tramitacion&ac=mociones_parlamentario&parlids=<IDs>

`parlids` es una lista separada por comas con TODOS los IDs de
parlamentario que ha tenido esa persona a lo largo de su carrera (ej.
Gahona: "1331,1138" — 1331 como senador, 1138 de cuando fue diputado).
Responde con GET simple (httpx, sin Playwright, sin bloqueo aparente) y
trae una tabla HTML con el historial COMPLETO de mociones desde que esa
persona empezó a legislar, en 2014 en los tres casos de la región — no
solo el período vigente.

Para que el conteo sea comparable con diputados (que solo cuentan
mociones del año en curso, ver camara_mociones.py), acá también se
filtra a mociones con fecha del año en curso. Se guarda en las mismas
tablas `proyecto_ley`/`mocion` que usa camara_mociones.py (esas tablas
ya son agnósticas de cámara — `camara_origen` en proyecto_ley distingue
'camara' de 'senado').
"""

import json
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path

from base import BaseScraper
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

API_URL = "https://tramitacion.senado.cl/appsenado/index.php"

# autoridad_id -> IDs de parlamentario (todos los períodos, separados por
# coma) — confirmados el 2026-08-25 navegando el buscador de Autores del
# sitio, filtrado por "Senador".
SENADORES_COQUIMBO = {
    "sergio-alfredo-gahona-salazar-senador": "1331,1138",
    "daniel-ignacio-nunez-arancibia-senador": "1336,1146",
    "matias-walker-prieto-senador": "1061,1344",
}


class ScraperSenadoMociones(BaseScraper):
    """Recolecta las mociones del año en curso de los 3 senadores de la
    Región de Coquimbo, vía el buscador de tramitación del Senado."""

    nombre = "senado_mociones"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        anno_actual = date.today().year
        registros = []
        for autoridad_id, parlids in SENADORES_COQUIMBO.items():
            resp = self.client.get(
                API_URL,
                params={
                    "mo": "tramitacion",
                    "ac": "mociones_parlamentario",
                    "parlids": parlids,
                    "titulo": "",
                },
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            tabla = soup.find("table", id="grid_nivel2")
            if not tabla:
                self.stats["errores"] += 1
                continue

            filas = tabla.find_all("tr")[1:]  # la primera es el encabezado
            for fila in filas:
                celdas = [c.get_text(strip=True) for c in fila.find_all("td")]
                if len(celdas) < 4:
                    continue
                fecha_raw, boletin, titulo, estado = celdas[0], celdas[1], celdas[2], celdas[3]
                try:
                    fecha = datetime.strptime(fecha_raw, "%d/%m/%Y")
                except ValueError:
                    continue
                if fecha.year != anno_actual or not boletin:
                    continue

                registros.append(
                    {
                        "autoridad_id": autoridad_id,
                        "boletin": boletin,
                        "titulo": titulo,
                        "estado": estado,
                        "fecha": fecha.strftime("%Y-%m-%d"),
                        "fuente_url": "https://tramitacion.senado.cl/appsenado/templates/tramitacion/",
                    }
                )
            time.sleep(1)  # rate limiting, mismo criterio que senado.py
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
        # mismo criterio que camara_mociones.py: mocion no tiene una
        # dimensión de "período" que preservar (siempre es "año en
        # curso"), así que se reemplaza completo por autoridad en cada
        # corrida en vez de upsert.
        autoridad_ids = tuple(SENADORES_COQUIMBO.keys())
        placeholders = ",".join("?" * len(autoridad_ids))
        self.db.execute(f"DELETE FROM mocion WHERE autoridad_id IN ({placeholders})", autoridad_ids)

        for r in registros:
            self.db.execute(
                """
                INSERT INTO proyecto_ley
                    (id, titulo, fecha_ingreso, estado, camara_origen, tipo, url_bcn)
                VALUES (?, ?, ?, ?, 'senado', 'mocion', ?)
                ON CONFLICT(id) DO UPDATE SET
                    titulo = excluded.titulo,
                    estado = excluded.estado,
                    url_bcn = excluded.url_bcn
                """,
                (r["boletin"], r["titulo"], r["fecha"], r["estado"], r["fuente_url"]),
            )
            self.db.execute(
                """
                INSERT INTO mocion (autoridad_id, proyecto_ley_id, fecha, rol)
                VALUES (?, ?, ?, 'autor')
                """,
                (r["autoridad_id"], r["boletin"], r["fecha"]),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        autoridad_ids = tuple(SENADORES_COQUIMBO.keys())
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
        (PROCESSED_DIR / "mociones-senadores.json").write_text(
            json.dumps([dict(f) for f in filas], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportadas {len(filas)} mociones de senadores a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperSenadoMociones()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
