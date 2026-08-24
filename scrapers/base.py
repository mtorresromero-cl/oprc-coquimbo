"""Clase base para todos los scrapers del observatorio."""

import sqlite3
from datetime import datetime
from pathlib import Path

import httpx

DB_PATH_DEFAULT = str(Path(__file__).resolve().parent.parent / "data" / "db" / "oprc.sqlite")


class BaseScraper:
    """Clase base para todos los scrapers.

    Cada scraper concreto implementa recolectar(), procesar(), guardar()
    y exportar_json(); ejecutar() orquesta el ciclo completo y deja
    registro en la tabla actualizacion_log.
    """

    nombre: str = "base"
    frecuencia: str = "semanal"  # diaria | semanal | mensual

    def __init__(self, db_path: str = DB_PATH_DEFAULT):
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.client = httpx.Client(
            timeout=30,
            headers={"User-Agent": "OPRC-Bot/1.0 (+https://oprcoquimbo.cl)"},
        )
        self.stats = {"nuevos": 0, "actualizados": 0, "errores": 0}

    def ejecutar(self) -> None:
        """Método principal. Llama a recolectar(), procesar(), guardar()."""
        self.log_inicio()
        try:
            datos_raw = self.recolectar()
            datos_procesados = self.procesar(datos_raw)
            self.guardar(datos_procesados)
            self.exportar_json()
            self.log_fin("ok")
        except Exception as e:
            self.log_fin("error", str(e))
            raise
        finally:
            self.client.close()
            self.db.close()

    def recolectar(self):
        """Override: obtener datos de la fuente."""
        raise NotImplementedError

    def procesar(self, datos_raw):
        """Override: limpiar y normalizar."""
        raise NotImplementedError

    def guardar(self, datos) -> None:
        """Override: insertar/actualizar en BD."""
        raise NotImplementedError

    def exportar_json(self) -> None:
        """Override: generar archivos JSON para el sitio."""
        raise NotImplementedError

    def log_inicio(self) -> None:
        self.db.execute(
            "INSERT INTO actualizacion_log (scraper, inicio) VALUES (?, ?)",
            (self.nombre, datetime.now().isoformat()),
        )
        self.db.commit()

    def log_fin(self, estado: str, error: str | None = None) -> None:
        self.db.execute(
            """
            UPDATE actualizacion_log
            SET fin = ?, estado = ?, registros_nuevos = ?,
                registros_actualizados = ?, error_mensaje = ?
            WHERE scraper = ? AND fin IS NULL
            """,
            (
                datetime.now().isoformat(),
                estado,
                self.stats["nuevos"],
                self.stats["actualizados"],
                error,
                self.nombre,
            ),
        )
        self.db.commit()
