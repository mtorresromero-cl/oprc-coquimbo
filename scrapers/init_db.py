"""Inicializa la base de datos SQLite a partir de data/db/schema.sql."""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "data" / "db" / "schema.sql"
DB_PATH = ROOT / "data" / "db" / "oprc.sqlite"


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text()
    con = sqlite3.connect(DB_PATH)
    con.executescript(schema)
    con.commit()
    con.close()
    print(f"BD inicializada en {DB_PATH}")


if __name__ == "__main__":
    main()
