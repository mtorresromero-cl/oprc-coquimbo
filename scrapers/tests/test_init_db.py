import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from init_db import SCHEMA_PATH  # noqa: E402


def test_schema_creates_expected_tables(tmp_path):
    db_path = tmp_path / "test.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA_PATH.read_text())
    tables = {
        row[0]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    con.close()

    esperadas = {
        "autoridad",
        "comuna",
        "votacion_sesion",
        "voto",
        "asistencia",
        "proyecto_ley",
        "mocion",
        "declaracion_patrimonio",
        "presupuesto_municipal",
        "transparencia_cumplimiento",
        "resultado_electoral",
        "actualizacion_log",
    }
    assert esperadas.issubset(tables)
