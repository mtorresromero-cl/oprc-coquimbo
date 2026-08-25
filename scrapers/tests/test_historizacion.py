"""Verifica que guardar() acumule histórico por período real en vez de
borrar-y-reemplazar: guardar dos veces el mismo período actualiza en el
lugar (sin duplicar), y guardar un período distinto se suma sin borrar
los anteriores.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infoprobidad import ScraperInfoProbidad  # noqa: E402
from init_db import SCHEMA_PATH  # noqa: E402
from personal_municipal import ScraperPersonalMunicipal  # noqa: E402
from transparencia_municipal import ScraperTransparenciaMunicipal  # noqa: E402


def _db_de_prueba(tmp_path) -> str:
    db_path = tmp_path / "test.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA_PATH.read_text())
    con.execute(
        "INSERT INTO comuna (id, nombre, provincia) VALUES ('la-serena', 'La Serena', 'Elqui')"
    )
    con.execute(
        "INSERT INTO autoridad (id, nombre, apellido, nombre_completo, cargo, activo) "
        "VALUES ('juan-perez-senador', 'Juan', 'Pérez', 'Juan Pérez', 'senador', 1)"
    )
    con.commit()
    con.close()
    return str(db_path)


def test_personal_municipal_acumula_meses_distintos(tmp_path):
    scraper = ScraperPersonalMunicipal(db_path=_db_de_prueba(tmp_path))
    fila_julio = {
        "comuna_id": "la-serena", "anno": 2026, "mes": 7, "area": "municipal",
        "tipo_contrato": "planta", "dotacion": 100, "remuneracion_total": 1000.0,
        "fuente_url": "https://example.cl",
    }
    fila_agosto = {**fila_julio, "mes": 8, "dotacion": 105}

    scraper.guardar({"agregados": [fila_julio], "autoridad": []})
    scraper.guardar({"agregados": [fila_agosto], "autoridad": []})

    filas = scraper.db.execute(
        "SELECT anno, mes, dotacion FROM personal_municipal ORDER BY mes"
    ).fetchall()
    assert filas == [(2026, 7, 100), (2026, 8, 105)]


def test_personal_municipal_actualiza_mismo_mes_sin_duplicar(tmp_path):
    scraper = ScraperPersonalMunicipal(db_path=_db_de_prueba(tmp_path))
    fila = {
        "comuna_id": "la-serena", "anno": 2026, "mes": 7, "area": "municipal",
        "tipo_contrato": "planta", "dotacion": 100, "remuneracion_total": 1000.0,
        "fuente_url": "https://example.cl",
    }
    scraper.guardar({"agregados": [fila], "autoridad": []})
    scraper.guardar({"agregados": [{**fila, "dotacion": 110}], "autoridad": []})

    filas = scraper.db.execute("SELECT dotacion FROM personal_municipal").fetchall()
    assert filas == [(110,)]


def test_presupuesto_municipal_acumula_annos_distintos(tmp_path):
    scraper = ScraperTransparenciaMunicipal(db_path=_db_de_prueba(tmp_path))
    fila_2025 = {
        "comuna_id": "la-serena", "anno": 2025, "tipo": "ingreso",
        "categoria": "Impuestos", "subcategoria": "01-00-000-000-000",
        "monto": 500.0, "fuente_url": "https://example.cl",
    }
    fila_2026 = {**fila_2025, "anno": 2026, "monto": 600.0}

    scraper.guardar([fila_2025])
    scraper.guardar([fila_2026])

    filas = scraper.db.execute(
        "SELECT anno, monto FROM presupuesto_municipal ORDER BY anno"
    ).fetchall()
    assert filas == [(2025, 500.0), (2026, 600.0)]


def test_declaracion_patrimonio_acumula_fechas_distintas(tmp_path):
    scraper = ScraperInfoProbidad(db_path=_db_de_prueba(tmp_path))
    declaracion_2025 = {
        "autoridad_id": "juan-perez-senador", "fecha_declaracion": "2025-03-30",
        "tipo_declaracion": "Actualización Periódica (Marzo)", "cargo_declarado": "SENADOR(A)",
        "organismo": "Senado", "bienes_inmuebles_n": 2, "vehiculos_n": 1, "sociedades_n": 0,
        "valores_monto": 0.0, "pasivos_tiene": False, "pasivos_monto": 0.0,
        "fuente_url": "https://infoprobidad.cl/x",
    }
    declaracion_2026 = {
        **declaracion_2025, "fecha_declaracion": "2026-03-17", "bienes_inmuebles_n": 3
    }

    scraper.guardar([declaracion_2025])
    scraper.guardar([declaracion_2026])

    filas = scraper.db.execute(
        "SELECT fecha_declaracion, bienes_inmuebles_n FROM declaracion_patrimonio "
        "ORDER BY fecha_declaracion"
    ).fetchall()
    assert filas == [("2025-03-30", 2), ("2026-03-17", 3)]
