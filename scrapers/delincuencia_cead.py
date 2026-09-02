"""Delincuencia — casos policiales por comuna, mensuales, vía CEAD (Centro
de Estudio y Análisis del Delito, del Ministerio del Interior y Seguridad
Pública). Cada cifra es la suma de denuncias formales más detenciones en
flagrancia reportadas por Carabineros y la PDI, según la propia definición
del CEAD.

Fuente de los datos (2026-09-02): el sitio en vivo de CEAD
(`cead.minsegpublica.gob.cl`) devuelve 403 "Maximum request file upload"
para TODO tipo de request — incluso un GET simple a la portada, incluso
con Playwright (Chromium real, no una librería). No es el mismo problema
que se investigó ese mismo día con camara.cl (que sí se resolvió, era un
dominio roto) — este es un caso distinto, sin resolver, y no vale la pena
seguir insistiendo sin poder probar desde otra red. Ver docs/06-bitacora.md.

Mientras tanto, se importan los datos desde el dataset ya público y
limpio que mantiene Bastián Olea Herrera (sociólogo, proyecto
bastianolea/delincuencia_chile en GitHub), quien sí logró scrapear CEAD
directamente — su README documenta la técnica exacta (POST a
`get_estadisticas_delictuales.php`, con los códigos de familia/grupo/
subgrupo de delito) por si en el futuro se quiere reemplazar esto por un
scraping propio en vez de depender de su snapshot.

Cobertura: 2010-01 a 2025-12, las 15 comunas de la Región de Coquimbo,
~29 tipos de delito. Se re-descarga el parquet completo en cada corrida
(pesa ~2MB) en vez de intentar un incremental — es la forma más simple de
quedar sincronizado con las actualizaciones de su repositorio.
"""

import json
import sqlite3
from datetime import datetime
from io import BytesIO
from pathlib import Path

from base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

PARQUET_URL = (
    "https://github.com/bastianolea/delincuencia_chile/raw/main/"
    "datos/procesados/cead_delincuencia_chile.parquet"
)

# CUT (código único territorial) -> id interno de la comuna en este proyecto
CUT_A_COMUNA = {
    4101: "la-serena", 4102: "coquimbo", 4103: "andacollo", 4104: "la-higuera",
    4105: "paihuano", 4106: "vicuna", 4201: "illapel", 4202: "canela",
    4203: "los-vilos", 4204: "salamanca", 4301: "ovalle", 4302: "combarbala",
    4303: "monte-patria", 4304: "punitaqui", 4305: "rio-hurtado",
}


class ScraperDelincuenciaCead(BaseScraper):
    nombre = "delincuencia_cead"
    frecuencia = "mensual"  # CEAD publica con retraso; no tiene sentido revisar más seguido

    def recolectar(self) -> list[dict]:
        import pandas as pd

        resp = self.client.get(PARQUET_URL, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        df = pd.read_parquet(BytesIO(resp.content))

        df = df[df["cut_comuna"].notna()].copy()
        df["cut_comuna"] = df["cut_comuna"].astype(int)
        df = df[df["cut_comuna"].isin(CUT_A_COMUNA)]

        registros = []
        for fila in df.itertuples(index=False):
            registros.append({
                "comuna_id": CUT_A_COMUNA[int(fila.cut_comuna)],
                "anno": fila.fecha.year,
                "mes": fila.fecha.month,
                "delito": fila.delito,
                "cantidad": int(fila.delito_n),
            })
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        ahora = datetime.now().isoformat()
        for r in registros:
            self.db.execute(
                """
                INSERT INTO delincuencia_cead
                    (comuna_id, anno, mes, delito, cantidad, fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(comuna_id, anno, mes, delito) DO UPDATE SET
                    cantidad = excluded.cantidad,
                    actualizado_en = excluded.actualizado_en
                """,
                (
                    r["comuna_id"], r["anno"], r["mes"], r["delito"], r["cantidad"],
                    PARQUET_URL, ahora,
                ),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        filas = self.db.execute(
            """
            SELECT comuna_id, anno, mes, delito, cantidad
            FROM delincuencia_cead
            ORDER BY comuna_id, anno, mes, delito
            """
        ).fetchall()
        salida = [dict(f) for f in filas]

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "delincuencia.json").write_text(
            json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportados {len(salida)} registros de delincuencia a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperDelincuenciaCead()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
