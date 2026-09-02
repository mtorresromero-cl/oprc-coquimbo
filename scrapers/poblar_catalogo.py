"""Puebla la BD con el catálogo maestro de comunas y autoridades (data/catalogo/*.csv)
y exporta los JSON que consume el sitio (data/processed/).

Uso: python scrapers/poblar_catalogo.py
"""

import csv
import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "db" / "oprc.sqlite"
CATALOGO_DIR = ROOT / "data" / "catalogo"
PROCESSED_DIR = ROOT / "data" / "processed"


def slugificar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "-", texto).strip("-")
    return texto


def cargar_comunas(con: sqlite3.Connection) -> None:
    ahora = datetime.now().isoformat()
    with open(CATALOGO_DIR / "comunas.csv", newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            con.execute(
                """
                INSERT INTO comuna (id, nombre, provincia, poblacion, actualizado_en)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nombre = excluded.nombre,
                    provincia = excluded.provincia,
                    poblacion = excluded.poblacion,
                    actualizado_en = excluded.actualizado_en
                """,
                (
                    fila["id"], fila["nombre"], fila["provincia"],
                    int(fila["poblacion"]) if fila.get("poblacion") else None,
                    ahora,
                ),
            )
    con.commit()


def cargar_autoridades(con: sqlite3.Connection) -> None:
    ahora = datetime.now().isoformat()
    contador_slug: dict[str, int] = {}

    with open(CATALOGO_DIR / "autoridades.csv", newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            nombre_completo = fila["nombre_completo"].strip()
            partes = nombre_completo.split()
            nombre = partes[0] if partes else ""
            apellido = " ".join(partes[1:]) if len(partes) > 1 else ""

            base_slug = slugificar(f"{nombre_completo}-{fila['cargo']}")
            contador_slug[base_slug] = contador_slug.get(base_slug, 0) + 1
            n = contador_slug[base_slug]
            slug = base_slug if n == 1 else f"{base_slug}-{n}"

            con.execute(
                """
                INSERT INTO autoridad (
                    id, nombre, apellido, nombre_completo, cargo, partido, pacto,
                    comuna, distrito, circunscripcion, periodo_inicio, periodo_fin,
                    foto_url, email, activo, fuente, actualizado_en
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nombre = excluded.nombre,
                    apellido = excluded.apellido,
                    nombre_completo = excluded.nombre_completo,
                    cargo = excluded.cargo,
                    partido = excluded.partido,
                    pacto = excluded.pacto,
                    comuna = excluded.comuna,
                    distrito = excluded.distrito,
                    circunscripcion = excluded.circunscripcion,
                    periodo_inicio = excluded.periodo_inicio,
                    periodo_fin = excluded.periodo_fin,
                    foto_url = excluded.foto_url,
                    email = excluded.email,
                    fuente = excluded.fuente,
                    actualizado_en = excluded.actualizado_en
                """,
                (
                    slug,
                    nombre,
                    apellido,
                    nombre_completo,
                    fila["cargo"],
                    fila.get("partido") or None,
                    fila.get("pacto") or None,
                    fila.get("comuna") or None,
                    fila.get("distrito") or None,
                    fila.get("circunscripcion") or None,
                    fila.get("periodo_inicio") or None,
                    fila.get("periodo_fin") or None,
                    fila.get("foto_url") or None,
                    fila.get("email") or None,
                    fila.get("fuente") or None,
                    ahora,
                ),
            )
    con.commit()


def exportar_json(con: sqlite3.Connection) -> None:
    con.row_factory = sqlite3.Row
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "autoridades").mkdir(exist_ok=True)

    comunas = [dict(r) for r in con.execute("SELECT * FROM comuna ORDER BY nombre")]
    (PROCESSED_DIR / "comunas.json").write_text(
        json.dumps(comunas, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    autoridades = [
        dict(r)
        for r in con.execute("SELECT * FROM autoridad ORDER BY cargo, comuna, apellido")
    ]
    (PROCESSED_DIR / "autoridades.json").write_text(
        json.dumps(autoridades, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for autoridad in autoridades:
        (PROCESSED_DIR / "autoridades" / f"{autoridad['id']}.json").write_text(
            json.dumps(autoridad, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"Exportados {len(comunas)} comunas y {len(autoridades)} autoridades a {PROCESSED_DIR}")


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cargar_comunas(con)
    cargar_autoridades(con)
    exportar_json(con)
    con.close()


if __name__ == "__main__":
    main()
