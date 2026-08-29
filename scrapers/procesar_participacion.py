"""Participación electoral (inscritos, votantes, % participación) por comuna
2012-2025, a partir de los csv que el usuario descargó de SERVEL
(extras/participación/, no versionado en git por tamaño — ver .gitignore).

A diferencia de resultado_electoral (candidato por candidato), estos csv
traen un solo registro por comuna por jornada de votación. Una "jornada"
puede agrupar varias elecciones simultáneas (ej. mayo 2021: municipales +
gobernador 1ª vuelta + convención constituyente, todas el mismo día con la
misma participación) — jornada identifica ese día de votación, no un
eleccion_tipo de resultado_electoral. tipos_relacionados guarda a qué
eleccion_tipo corresponde esa jornada para poder enlazar participación con
resultados.

Los csv vienen en dos formatos según el año: unos traen Nro.Región/Región
(nacional, hay que filtrar a Coquimbo) y otros no (aparentemente ya vienen
sin esa columna pero igual son nacionales — se filtra igual por nombre de
comuna, que en Chile es único a nivel nacional). El nombre de la columna
con el conteo de votantes también varía entre archivos (Votantes/Votación/
Votos) — se detecta por descarte, no por nombre fijo.

Dos jornadas de 2023 existieron (Consejo Constitucional en mayo, Plebiscito
Constitucional en diciembre) pero el usuario solo proveyó un csv para ese
año sin indicar cuál. Se identificó por contraste con cifras reales
publicadas (Andacollo 88.13% de participación coincide exactamente con lo
reportado para el plebiscito de diciembre 2023, no hay cifra pública
equivalente para mayo) — es la jornada de diciembre.
"""

import csv
import json
import sqlite3
from pathlib import Path

from base import BaseScraper
from procesar_elecciones_recientes import COMUNAS_NOMBRE

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
RAW_DIR = ROOT / "extras" / "participación"

# (archivo, jornada, año, etiqueta, tipos_relacionados en resultado_electoral)
JORNADAS = [
    ("participacion_2012_comunal.csv", "municipal_2012", 2012, "Municipales 2012", ["municipal"]),
    (
        "participacion_2013_comunal.csv",
        "parlamentaria_presidencial_2013",
        2013,
        "Parlamentarias, presidencial (1ª vuelta) y CORE 2013",
        ["diputados", "senadores", "presidencial_1v", "consejeros_regionales"],
    ),
    ("participacion_2016_comunal.csv", "municipal_2016", 2016, "Municipales 2016", ["municipal"]),
    (
        "participacion_2017_comunal.csv",
        "parlamentaria_presidencial_2017",
        2017,
        "Parlamentarias y presidencial (1ª vuelta) 2017",
        ["diputados", "senadores", "presidencial_1v", "consejeros_regionales"],
    ),
    (
        "participacion_2020_comunal.csv",
        "plebiscito_2020",
        2020,
        "Plebiscito Nacional 2020",
        ["plebiscito_constitucion", "plebiscito_tipo_organo"],
    ),
    (
        "participacion_2021_m_comunal.csv",
        "megaeleccion_2021",
        2021,
        "Municipales, gobernador (1ª vuelta) y Convención Constituyente 2021",
        [
            "municipal",
            "gobernador_1v",
            "convencional_constituyente",
            "convencional_constituyente_indigena",
        ],
    ),
    (
        "participacion_2021_p_comunal.csv",
        "parlamentaria_presidencial_2021",
        2021,
        "Parlamentarias, presidencial (1ª vuelta) y CORE 2021",
        ["diputados", "senadores", "presidencial_1v", "consejeros_regionales"],
    ),
    (
        "participacion_2022_comunal.csv",
        "plebiscito_2022",
        2022,
        "Plebiscito Constitucional (salida) 2022",
        ["plebiscito_constitucional"],
    ),
    (
        "participacion_2023_comunal.csv",
        "plebiscito_2023",
        2023,
        "Plebiscito Constitucional (salida) 2023",
        ["plebiscito_constitucional"],
    ),
    (
        "participacion_2024_comunal.csv",
        "municipal_2024",
        2024,
        "Municipales, gobernador (1ª vuelta) y CORE 2024",
        ["municipal", "gobernador_1v", "consejeros_regionales"],
    ),
    (
        "participacion_2025_comunal.csv",
        "parlamentaria_presidencial_2025",
        2025,
        "Parlamentarias y presidencial (1ª vuelta) 2025",
        ["diputados", "presidencial_1v"],
    ),
]

# columnas que nunca son el conteo de votantes, para detectarla por descarte
COLUMNAS_CONOCIDAS = {"nro.región", "región", "comuna", "inscritos"}


class ProcesadorParticipacion(BaseScraper):
    """No es un scraper web: lee los csv de participación que el usuario ya
    descargó de SERVEL (extras/participación/) y los normaliza a
    participacion_electoral. Se ejecuta una sola vez por archivo nuevo."""

    nombre = "procesar_participacion"
    frecuencia = "una_vez"

    def recolectar(self) -> list[dict]:
        registros = []
        for archivo, jornada, anno, etiqueta, tipos in JORNADAS:
            ruta = RAW_DIR / archivo
            if not ruta.exists():
                print(f"[{archivo}] no encontrado, se omite")
                continue
            try:
                filas = self._procesar_archivo(ruta, jornada, anno, etiqueta, tipos)
            except Exception as e:
                print(f"[{archivo}] ERROR: {e}")
                self.stats["errores"] += 1
                continue
            print(f"[{archivo}] {len(filas)} comunas de Coquimbo")
            registros.extend(filas)
        return registros

    def _procesar_archivo(
        self, ruta: Path, jornada: str, anno: int, etiqueta: str, tipos: list[str]
    ) -> list[dict]:
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            encabezados = lector.fieldnames or []

            idx_region = next((h for h in encabezados if h.lower() in ("región", "region")), None)
            col_votantes = next(
                (
                    h
                    for h in encabezados
                    if h.lower() not in COLUMNAS_CONOCIDAS and "particip" not in h.lower()
                ),
                None,
            )
            col_pct = next((h for h in encabezados if "particip" in h.lower()), None)
            if col_votantes is None or col_pct is None:
                return []

            registros = []
            for fila in lector:
                if idx_region is not None and "COQUIMBO" not in fila[idx_region].strip().upper():
                    continue
                comuna_txt = (fila.get("Comuna") or "").strip().upper()
                comuna_id = COMUNAS_NOMBRE.get(comuna_txt)
                if comuna_id is None:
                    continue

                try:
                    inscritos = int(float(fila["Inscritos"]))
                    votantes = int(float(fila[col_votantes]))
                    pct = round(float(fila[col_pct]), 2)
                except (ValueError, KeyError):
                    continue

                registros.append(
                    {
                        "jornada": jornada,
                        "anno": anno,
                        "etiqueta": etiqueta,
                        "tipos_relacionados": ",".join(tipos),
                        "comuna_id": comuna_id,
                        "inscritos": inscritos,
                        "votantes": votantes,
                        "participacion_pct": pct,
                    }
                )
            return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        jornadas = {r["jornada"] for r in registros}
        for jornada in jornadas:
            self.db.execute("DELETE FROM participacion_electoral WHERE jornada = ?", (jornada,))
        for r in registros:
            self.db.execute(
                """
                INSERT INTO participacion_electoral
                    (jornada, anno, etiqueta, tipos_relacionados, comuna_id,
                     inscritos, votantes, participacion_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["jornada"], r["anno"], r["etiqueta"], r["tipos_relacionados"],
                    r["comuna_id"], r["inscritos"], r["votantes"], r["participacion_pct"],
                ),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        filas = self.db.execute(
            """
            SELECT jornada, anno, etiqueta, tipos_relacionados, comuna_id,
                   inscritos, votantes, participacion_pct
            FROM participacion_electoral
            ORDER BY anno DESC, jornada, comuna_id
            """
        ).fetchall()

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "participacion-electoral.json").write_text(
            json.dumps([dict(f) for f in filas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Exportados {len(filas)} registros de participación a {PROCESSED_DIR}")


if __name__ == "__main__":
    proc = ProcesadorParticipacion()
    proc.ejecutar()
    print("Estadísticas:", proc.stats)
