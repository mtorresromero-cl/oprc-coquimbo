"""Asistencia a sesiones de sala de los senadores de la Región de Coquimbo,
vía la API pública que usa senado.cl para su propia página de asistencia
(`/actividad-legislativa/sala/asistencia`).

Investigado el 2026-08-25, a partir de una pregunta directa: "¿los
senadores no tienen asistencia?". senado.py (votaciones) ya dejaba anotado
que `tramitacion.senado.cl/wspublico` no trae asistencia — cierto, pero esa
no es la única fuente de senado.cl. La página pública de asistencia sí
existe y trae una tabla completa (todos los senadores, período completo,
sin paginación), pero el HTML servido por el navegador sin JS no la
contiene: se carga vía fetch a una API JSON aparte
(`web-back.senado.cl/api/...`), encontrada inspeccionando las requests de
red reales de esa página, no adivinada. Esa API responde igual con un GET
simple (httpx, sin Playwright) — no tiene la protección de camara.cl.

Flujo:
1. `GET /api/legislatures?limit=1` → la legislatura vigente (primera de la
   lista, viene ordenada por más reciente).
2. `GET /api/sessions/attendance?id_legislatura=<ID>&limit=100` → asistencia
   de los ~50 senadores en esa legislatura completa (no parcial: la API no
   pagina esto, es una sola respuesta con todos).

Los nombres de la API (NOMBRE/APELLIDO_PATERNO/APELLIDO_MATERNO) no siempre
calzan con nuestro split nombre/apellido (mismo problema documentado para
diputados) — se matchea por tokens del nombre completo, no por string
exacto.
"""

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

API_BASE = "https://web-back.senado.cl/api"

SENADORES_COQUIMBO = (
    "sergio-alfredo-gahona-salazar-senador",
    "daniel-ignacio-nunez-arancibia-senador",
    "matias-walker-prieto-senador",
)


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _tokens(texto: str) -> frozenset[str]:
    return frozenset(_normalizar(texto).split())


def _es_la_misma_persona(tokens_a: frozenset[str], tokens_b: frozenset[str]) -> bool:
    menor, mayor = sorted([tokens_a, tokens_b], key=len)
    return len(menor) >= 2 and menor.issubset(mayor)


class ScraperSenadoAsistencia(BaseScraper):
    """Recolecta el resumen de asistencia de la legislatura vigente para
    los 3 senadores de la Región de Coquimbo, vía la API de senado.cl."""

    nombre = "senado_asistencia"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        r = self.client.get(f"{API_BASE}/legislatures", params={"limit": 1})
        r.raise_for_status()
        legislaturas = r.json()["data"]
        if not legislaturas:
            return []
        id_legislatura = legislaturas[0]["ID_LEGISLATURA"]
        numero_legislatura = legislaturas[0]["NUMERO"]

        r = self.client.get(
            f"{API_BASE}/sessions/attendance",
            params={"id_legislatura": id_legislatura, "limit": 100},
        )
        r.raise_for_status()
        datos = r.json()["data"]

        return [
            {**fila, "numero_legislatura": numero_legislatura}
            for fila in datos.get("DATA", [])
        ]

    def procesar(self, registros: list[dict]) -> list[dict]:
        tokens_autoridades = {
            autoridad_id: _tokens(self._nombre_completo(autoridad_id))
            for autoridad_id in SENADORES_COQUIMBO
        }

        procesados = []
        for r in registros:
            nombre_completo = f"{r['NOMBRE']} {r['APELLIDO_PATERNO']} {r['APELLIDO_MATERNO']}"
            tokens_fila = _tokens(nombre_completo)
            for autoridad_id, tokens_autoridad in tokens_autoridades.items():
                if _es_la_misma_persona(tokens_autoridad, tokens_fila):
                    procesados.append(
                        {
                            "autoridad_id": autoridad_id,
                            "anno": r["numero_legislatura"],
                            "total_sesiones": r["TOTAL_SESIONES_TOTAL"],
                            "sesiones_computables": r["TOTAL_SESIONES_TOTAL"],
                            "asistencias": r["ASISTIO_A"],
                            "ausencias_justificadas": r["JUSTIFICADO"],
                            "ausencias_sin_justificar": r["SIN_JUSTIFICAR"],
                            "fuente_url": "https://www.senado.cl/actividad-legislativa/sala/asistencia",
                        }
                    )
                    break
        return procesados

    def _nombre_completo(self, autoridad_id: str) -> str:
        fila = self.db.execute(
            "SELECT nombre_completo FROM autoridad WHERE id = ?", (autoridad_id,)
        ).fetchone()
        return fila[0] if fila else autoridad_id

    def guardar(self, registros: list[dict]) -> None:
        for r in registros:
            self.db.execute(
                """
                INSERT INTO asistencia_resumen
                    (autoridad_id, camara, anno, total_sesiones, sesiones_computables,
                     asistencias, ausencias_justificadas, ausencias_sin_justificar, fuente_url)
                VALUES (?, 'senado', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(autoridad_id, camara, anno) DO UPDATE SET
                    total_sesiones = excluded.total_sesiones,
                    sesiones_computables = excluded.sesiones_computables,
                    asistencias = excluded.asistencias,
                    ausencias_justificadas = excluded.ausencias_justificadas,
                    ausencias_sin_justificar = excluded.ausencias_sin_justificar,
                    fuente_url = excluded.fuente_url
                """,
                (
                    r["autoridad_id"],
                    r["anno"],
                    r["total_sesiones"],
                    r["sesiones_computables"],
                    r["asistencias"],
                    r["ausencias_justificadas"],
                    r["ausencias_sin_justificar"],
                    r["fuente_url"],
                ),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(SENADORES_COQUIMBO))
        resumen = self.db.execute(
            f"""
            SELECT autoridad_id, camara, anno, total_sesiones, sesiones_computables, asistencias,
                   ausencias_justificadas, ausencias_sin_justificar, fuente_url
            FROM asistencia_resumen
            WHERE camara = 'senado' AND autoridad_id IN ({placeholders})
            ORDER BY anno DESC
            """,
            SENADORES_COQUIMBO,
        ).fetchall()

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "asistencia-resumen-senadores.json").write_text(
            json.dumps([dict(f) for f in resumen], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportados {len(resumen)} resúmenes de asistencia de senadores a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperSenadoAsistencia()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
