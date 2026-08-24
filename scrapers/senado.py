"""Scraper de votaciones del Senado para los 3 senadores de la Región de Coquimbo.

Fuente: tramitacion.senado.cl/wspublico (servicio público del Senado, XML,
sin autenticación). No confundir con opendata.camara.cl: ese servicio expone
el catálogo de diputados/sesiones pero sus endpoints de votaciones/asistencia
están vacíos (ver docs/05-scrapers.md, sección "Estado conocido").

Asistencia a sesiones NO está disponible por este medio (sesiones.php solo
trae metadata de la sesión, no presencia por parlamentario) — se deja fuera
de este scraper a propósito, no se infiere desde ausencias en votaciones.
"""

import json
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

# Mapea autoridad_id -> nombre tal como aparece en <PARLAMENTARIO> de votaciones.php
# (formato "ApellidoPaterno InicialApellidoMaterno., Nombre", confirmado contra
# senadores_vigentes.php y una votación real el 2026-08-24).
SENADORES_COQUIMBO = {
    "sergio-alfredo-gahona-salazar-senador": "Gahona S., Sergio",
    "daniel-ignacio-nunez-arancibia-senador": "Núñez A., Daniel",
    "matias-walker-prieto-senador": "Walker P., Matías",
}

SELECCION_A_VOTO = {
    "Si": "favor",
    "Sí": "favor",
    "No": "contra",
    "Abstención": "abstencion",
    "Abstencion": "abstencion",
    "Pareo": "pareo",
}


def _fecha_a_iso(fecha_ddmmyyyy: str) -> str:
    return datetime.strptime(fecha_ddmmyyyy.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")


class ScraperSenado(BaseScraper):
    """Recolecta votaciones recientes del Senado y extrae los votos de los
    3 senadores de la Región de Coquimbo."""

    nombre = "senado_votaciones"
    frecuencia = "semanal"
    base_url = "https://tramitacion.senado.cl/wspublico"

    def recolectar(self) -> list[tuple[str, bytes]]:
        fecha_desde = (datetime.now() - timedelta(days=7)).strftime("%d/%m/%Y")
        resp = self.client.get(f"{self.base_url}/tramitacion.php", params={"fecha": fecha_desde})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        boletines = sorted({el.text for el in root.findall(".//boletin") if el.text})

        votaciones_xml = []
        for boletin_completo in boletines:
            numero = boletin_completo.split("-")[0]
            time.sleep(1)  # rate limiting: máx 1 req/s
            try:
                r = self.client.get(f"{self.base_url}/votaciones.php", params={"boletin": numero})
                r.raise_for_status()
                if b"<votaciones" in r.content:
                    votaciones_xml.append((boletin_completo, r.content))
            except Exception:
                self.stats["errores"] += 1
        return votaciones_xml

    def procesar(self, votaciones_xml: list[tuple[str, bytes]]) -> list[dict]:
        registros = []
        for boletin, xml_bytes in votaciones_xml:
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError:
                self.stats["errores"] += 1
                continue

            for votacion in root.findall("votacion"):
                fecha_raw = votacion.findtext("FECHA", "")
                if not fecha_raw:
                    continue
                fecha_iso = _fecha_a_iso(fecha_raw)
                sesion = votacion.findtext("SESION", "").replace("/", "-")
                boletin_num = boletin.split("-")[0]
                sesion_id = f"senado-{boletin_num}-{sesion}-{fecha_iso}"

                votos = []
                for voto_el in votacion.findall("DETALLE_VOTACION/VOTO"):
                    parlamentario = (voto_el.findtext("PARLAMENTARIO") or "").strip()
                    for autoridad_id, nombre_votacion in SENADORES_COQUIMBO.items():
                        if parlamentario == nombre_votacion:
                            seleccion = (voto_el.findtext("SELECCION") or "").strip()
                            votos.append(
                                {
                                    "autoridad_id": autoridad_id,
                                    "voto": SELECCION_A_VOTO.get(seleccion, seleccion.lower()),
                                }
                            )

                if not votos:
                    continue  # ninguno de nuestros 3 senadores votó en esta votación

                si = int(votacion.findtext("SI") or 0)
                no = int(votacion.findtext("NO") or 0)
                tema = re.sub(r"\s+", " ", votacion.findtext("TEMA", "")).strip()

                registros.append(
                    {
                        "sesion_id": sesion_id,
                        "boletin": boletin,
                        "fecha": fecha_iso,
                        "numero_sesion": votacion.findtext("SESION", ""),
                        "descripcion": tema[:500],
                        "resultado": "aprobado" if si > no else "rechazado",
                        "votos_favor": si,
                        "votos_contra": no,
                        "abstenciones": int(votacion.findtext("ABSTENCION") or 0),
                        "fuente_url": f"{self.base_url}/votaciones.php?boletin={boletin_num}",
                        "votos": votos,
                    }
                )
        return registros

    def guardar(self, registros: list[dict]) -> None:
        for r in registros:
            self.db.execute(
                """
                INSERT INTO votacion_sesion
                    (id, camara, fecha, numero_sesion, descripcion, resultado,
                     votos_favor, votos_contra, abstenciones, fuente_url)
                VALUES (?, 'senado', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    descripcion = excluded.descripcion,
                    resultado = excluded.resultado,
                    votos_favor = excluded.votos_favor,
                    votos_contra = excluded.votos_contra,
                    abstenciones = excluded.abstenciones
                """,
                (
                    r["sesion_id"],
                    r["fecha"],
                    r["numero_sesion"],
                    r["descripcion"],
                    r["resultado"],
                    r["votos_favor"],
                    r["votos_contra"],
                    r["abstenciones"],
                    r["fuente_url"],
                ),
            )
            for v in r["votos"]:
                self.db.execute(
                    """
                    INSERT INTO voto (autoridad_id, sesion_id, voto, fecha)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(autoridad_id, sesion_id) DO UPDATE SET voto = excluded.voto
                    """,
                    (v["autoridad_id"], r["sesion_id"], v["voto"], r["fecha"]),
                )
                self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        sesiones = self.db.execute(
            "SELECT * FROM votacion_sesion WHERE camara = 'senado' ORDER BY fecha DESC"
        ).fetchall()

        salida = []
        for s in sesiones:
            votos = self.db.execute(
                "SELECT autoridad_id, voto FROM voto WHERE sesion_id = ?", (s["id"],)
            ).fetchall()
            salida.append({**dict(s), "votos": [dict(v) for v in votos]})

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "votaciones.json").write_text(
            json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (PROCESSED_DIR / "votaciones-recientes.json").write_text(
            json.dumps(salida[:50], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportadas {len(salida)} votaciones a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperSenado()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
