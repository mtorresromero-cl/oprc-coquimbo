"""Mociones parlamentarias de los diputados de la Región de Coquimbo, vía el
endpoint SPARQL de datos abiertos enlazados de la BCN (datos.bcn.cl/sparql).

No sustituye a las votaciones/asistencia (BCN no las tiene, ver
docs/05-scrapers.md) pero sí tiene mociones como datos estructurados.

BCN no enlaza semánticamente cada moción con sus autores individuales (solo
texto libre en el label, ej. "de los diputados señores Manouchehri, Tello...").
Por eso se busca por apellido paterno con regex. Alcance: legislaturas 373
(2025-2026) y 374 (2026-2030 en curso) — cubre a los diputados reelectos y
evita falsos positivos históricos con apellidos comunes de otras épocas.

Verificado manualmente 2026-08-24 antes de automatizar: los matches de
"Castillo" (apellido común, riesgo de ambigüedad) se corresponden de forma
consistente con el mismo grupo de co-firmantes en cada moción, incluyendo una
moción específica de la Región de Coquimbo (aeropuerto de La Serena) cofirmada
junto a Manouchehri, Sulantay y Tello — confirma que es Nathalie Castillo
Rojas y no otra diputada de apellido Castillo.
"""

import json
import re
import sqlite3
from pathlib import Path

from base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
SPARQL_URL = "https://datos.bcn.cl/sparql"
LEGISLATURAS = ["373", "374"]

# apellido paterno -> autoridad_id (ver docstring: matching por texto libre,
# no hay enlace semántico autor-documento en BCN para mociones)
DIPUTADOS_COQUIMBO = {
    "Manouchehri": "daniel-manouchehri-lobos-diputado",
    "Tello": "carolina-tello-rojas-diputado",
    "Castillo": "nathalie-castillo-rojas-diputado",
    "Salinas": "bernardo-antonio-salinas-maya-diputado",
    "Urqueta": "eileen-patricia-urqueta-rojas-diputado",
    "Sulantay": "marco-antonio-sulantay-olivares-diputado",
    "Grohs": "erich-christ-grohs-marin-diputado",
}

QUERY = """
PREFIX bcnres: <http://datos.bcn.cl/ontologies/bcn-resources#>
PREFIX bcncong: <http://datos.bcn.cl/ontologies/bcn-congress#>
SELECT ?doc ?label ?fecha WHERE {{
  ?doc a bcnres:MocionParlamentaria .
  ?doc rdfs:label ?label .
  ?doc dc:date ?fecha .
  ?doc bcncong:perteneceA <http://datos.bcn.cl/recurso/cl/legislatura/{legislatura}> .
}} ORDER BY ?fecha
"""

BOLETIN_RE = re.compile(r"Bolet[ií]n\s*N[°º]?\s*([\d.]+-\d+)", re.IGNORECASE)
TITULO_RE = re.compile(r"\bque\s+(.+?)\.\s*Bolet[ií]n", re.IGNORECASE | re.DOTALL)


class ScraperBcnMociones(BaseScraper):
    """Recolecta mociones parlamentarias de BCN para los diputados de Coquimbo."""

    nombre = "bcn_mociones"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        docs = []
        for legislatura in LEGISLATURAS:
            resp = self.client.get(
                SPARQL_URL,
                params={"query": QUERY.format(legislatura=legislatura)},
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
            docs.extend(resp.json()["results"]["bindings"])
        return docs

    def procesar(self, docs: list[dict]) -> list[dict]:
        registros = []
        vistos: set[tuple[str, str]] = set()  # (boletin, autoridad_id), evita duplicados

        for doc in docs:
            label = doc["label"]["value"]
            fecha = doc["fecha"]["value"]
            doc_id = doc["doc"]["value"]

            boletin_m = BOLETIN_RE.search(label)
            if not boletin_m:
                continue
            boletin = boletin_m.group(1).replace(".", "")

            titulo_m = TITULO_RE.search(label)
            titulo = titulo_m.group(1).strip() if titulo_m else label[:200]

            for apellido, autoridad_id in DIPUTADOS_COQUIMBO.items():
                if not re.search(rf"\b{re.escape(apellido)}\b", label):
                    continue
                clave = (boletin, autoridad_id)
                if clave in vistos:
                    continue
                vistos.add(clave)
                registros.append(
                    {
                        "autoridad_id": autoridad_id,
                        "boletin": boletin,
                        "titulo": titulo,
                        "fecha": fecha,
                        "url_bcn": doc_id,
                    }
                )
        return registros

    def guardar(self, registros: list[dict]) -> None:
        autoridad_ids = tuple(DIPUTADOS_COQUIMBO.values())
        placeholders = ",".join("?" * len(autoridad_ids))
        self.db.execute(
            f"DELETE FROM mocion WHERE autoridad_id IN ({placeholders})", autoridad_ids
        )

        for r in registros:
            self.db.execute(
                """
                INSERT INTO proyecto_ley (id, titulo, fecha_ingreso, camara_origen, tipo, url_bcn)
                VALUES (?, ?, ?, 'camara', 'mocion', ?)
                ON CONFLICT(id) DO UPDATE SET
                    titulo = excluded.titulo, url_bcn = excluded.url_bcn
                """,
                (r["boletin"], r["titulo"], r["fecha"], r["url_bcn"]),
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
        autoridad_ids = tuple(DIPUTADOS_COQUIMBO.values())
        placeholders = ",".join("?" * len(autoridad_ids))
        filas = self.db.execute(
            f"""
            SELECT m.autoridad_id, m.fecha, m.rol, p.id AS boletin, p.titulo, p.url_bcn
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
    scraper = ScraperBcnMociones()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
