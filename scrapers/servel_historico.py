"""Resultados electorales históricos (1989-2009) de la Región de Coquimbo, vía
historial.servel.cl — el sitio antiguo del "Sistema de Despliegue de
Cómputos" del Ministerio del Interior, reemplazado por Power BI para
elecciones desde 2012 en adelante (ver data/raw/elecciones/*.xlsx, provisto
directamente por el usuario, no scrapeado).

Este sitio no tiene archivos descargables ni una tabla HTML simple con
enlaces de navegación: la navegación real ocurría vía un mapa interactivo en
Flash (hoy completamente muerto, no funciona en ningún navegador) que
armaba las URLs a partir de códigos de zona/comuna. No hay ningún link en
el HTML que revele esos códigos — se determinaron a mano, con ayuda del
usuario, verificando cada uno contra nombres de comuna y candidatos reales
conocidos (confirmado cruzando contra datos ya scrapeados: "Juan Carlos
Alfaro Aravena, Alcalde 4 años" en Andacollo 2008 es la misma persona que
ya tenemos como alcalde actual de Andacollo).

Estructura de URL descubierta:
  paginas/{año}/{elección}/{zona}/{agrupación}/{sexo}/{código}.htm

- zona="comunas", agrupación="candidatos", sexo="total": resultado
  candidato por candidato en una comuna — lo que usa este scraper.
- Los códigos de comuna son estables entre años y tipos de elección
  (verificado): mismo código para 1989, 2005, 2009, alcaldes 2008, etc.
- Los códigos siguen un patrón real por provincia: "30xx" = provincia de
  Elqui, "31xx" = Limarí, "32xx" = Choapa (no es casualidad, corresponde a
  la agrupación provincial real).
"""

import json
import re
import time
from pathlib import Path

import httpx
from base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

BASE_URL = "https://historial.servel.cl/SitioHistorico"

# comuna_id -> código real en historial.servel.cl (verificado a mano por el
# usuario y cruzado contra nombres de comuna y candidatos conocidos).
COMUNAS_CODIGOS = {
    "la-serena": "3001",
    "la-higuera": "3002",
    "coquimbo": "3003",
    "andacollo": "3004",
    "vicuna": "3005",
    "paihuano": "3006",
    "ovalle": "3101",
    "rio-hurtado": "3102",
    "monte-patria": "3103",
    "combarbala": "3104",
    "punitaqui": "3105",
    "illapel": "3201",
    "salamanca": "3202",
    "los-vilos": "3203",
    "canela": "3204",
}

# (año, slug de la URL, eleccion_tipo normalizado, cargo por defecto). El
# listado completo de años/elecciones disponibles para 1989-2009 según el
# índice de historial.servel.cl (biblioteca-de-documentos/resultados-
# electorales-historicos). Senadores no se elegían en todas las regiones
# cada vez (mandato de 8 años, renovación por mitades) — se deja igual en
# la lista y el scraper simplemente registra 0 filas si no hubo elección
# ahí ese año, en vez de asumir que siempre hay datos.
ELECCIONES = [
    (2009, "presidencial1v", "presidencial_1v", "Presidente"),
    (2009, "presidencial2v", "presidencial_2v", "Presidente"),
    (2009, "senadores", "senadores", "Senador"),
    (2009, "diputados", "diputados", "Diputado"),
    (2008, "alcaldes", "municipal", "Alcalde"),
    (2008, "concejales", "municipal", "Concejal"),
    (2005, "presidencial1v", "presidencial_1v", "Presidente"),
    (2005, "presidencial2v", "presidencial_2v", "Presidente"),
    (2005, "senadores", "senadores", "Senador"),
    (2005, "diputados", "diputados", "Diputado"),
    (2004, "alcaldes", "municipal", "Alcalde"),
    (2004, "concejales", "municipal", "Concejal"),
    (2001, "senadores", "senadores", "Senador"),
    (2001, "diputados", "diputados", "Diputado"),
    (2000, "municipales", "municipal", "Concejal"),
    (1999, "presidencial1v", "presidencial_1v", "Presidente"),
    (1999, "presidencial2v", "presidencial_2v", "Presidente"),
    (1997, "senadores", "senadores", "Senador"),
    (1997, "diputados", "diputados", "Diputado"),
    (1996, "municipales", "municipal", "Concejal"),
    (1993, "presidencial1v", "presidencial_1v", "Presidente"),
    (1993, "senadores", "senadores", "Senador"),
    (1993, "diputados", "diputados", "Diputado"),
    (1992, "municipales", "municipal", "Concejal"),
    (1989, "presidencial1v", "presidencial_1v", "Presidente"),
    (1989, "senadores", "senadores", "Senador"),
    (1989, "diputados", "diputados", "Diputado"),
]


def _monto_a_numero(texto: str) -> int | None:
    texto = (texto or "").strip().replace(".", "")
    if not texto or texto in ("-",):
        return None
    try:
        return int(texto)
    except ValueError:
        return None


def _porcentaje_a_numero(texto: str) -> float | None:
    texto = (texto or "").strip().replace("%", "").replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _normaliza_cargo(texto_cargo: str, cargo_defecto: str) -> str:
    texto = (texto_cargo or "").strip()
    if not texto:
        return cargo_defecto
    for prefijo in ("Alcalde", "Concejal", "Diputado", "Senador", "Presidente"):
        if texto.startswith(prefijo):
            return prefijo
    return texto


class ScraperServelHistorico(BaseScraper):
    """Resultados electorales 1989-2009 de la Región de Coquimbo, a nivel
    comuna, candidato por candidato."""

    nombre = "servel_historico"
    frecuencia = "una_vez"  # datos históricos fijos, no cambian

    def recolectar(self) -> list[dict]:
        registros = []
        with httpx.Client(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as client:
            for anno, slug, eleccion_tipo, cargo_defecto in ELECCIONES:
                for comuna_id, codigo in COMUNAS_CODIGOS.items():
                    url = (
                        f"{BASE_URL}/paginas/{anno}/{slug}/comunas/candidatos/total/"
                        f"{codigo}.htm"
                    )
                    try:
                        filas = self._extraer_pagina(
                            client, url, anno, comuna_id, eleccion_tipo, cargo_defecto
                        )
                    except Exception as e:
                        print(f"[{anno}/{slug}/{comuna_id}] ERROR: {e}")
                        self.stats["errores"] += 1
                        continue
                    if filas:
                        print(f"[{anno}/{slug}/{comuna_id}] {len(filas)} candidatos")
                    registros.extend(filas)
                    time.sleep(0.3)  # rate limiting suave
        return registros

    def _extraer_pagina(
        self,
        client: httpx.Client,
        url: str,
        anno: int,
        comuna_id: str,
        eleccion_tipo: str,
        cargo_defecto: str,
    ) -> list[dict]:
        resp = client.get(url)
        if resp.status_code != 200:
            return []
        texto_html = resp.text

        # encabezado dinámico: presidencial no trae columna PARTIDO, el
        # resto sí — se detecta por texto en vez de asumir índice fijo.
        encabezados = re.findall(r'<TH[^>]*>([^<]*)</TH>', texto_html, re.IGNORECASE)
        encabezados = [h.strip().upper() for h in encabezados]
        if "NOMBRE" not in encabezados:
            return []
        idx_nombre = encabezados.index("NOMBRE")
        idx_partido = encabezados.index("PARTIDO") if "PARTIDO" in encabezados else None
        idx_votos = encabezados.index("VOTOS") if "VOTOS" in encabezados else None
        idx_pct = encabezados.index("PORCENTAJE") if "PORCENTAJE" in encabezados else None
        idx_cargo = encabezados.index("CARGO") if "CARGO" in encabezados else None
        if idx_votos is None or idx_pct is None:
            return []

        filas_html = re.findall(r"<TR>(<TD.*?)</TR>", texto_html, re.IGNORECASE | re.DOTALL)
        registros = []
        for fila in filas_html:
            celdas_crudas = re.findall(r"<TD[^>]*>(.*?)</TD>", fila, re.IGNORECASE | re.DOTALL)
            celdas = [
                re.sub(r"&[a-z]+;|&#\d+;", lambda m: _entidad(m.group(0)), c).strip()
                for c in celdas_crudas
            ]
            if len(celdas) <= max(idx_nombre, idx_votos, idx_pct):
                continue
            nombre = celdas[idx_nombre].strip()
            if not nombre or "Válidamente Emitidos" in nombre or "Válidamente" in nombre:
                continue
            votos = _monto_a_numero(celdas[idx_votos])
            porcentaje = _porcentaje_a_numero(celdas[idx_pct])
            if votos is None:
                continue
            hay_cargo = idx_cargo is not None and idx_cargo < len(celdas)
            texto_cargo = celdas[idx_cargo] if hay_cargo else ""
            texto_cargo = texto_cargo.replace("&nbsp;", "").strip()
            cargo = _normaliza_cargo(texto_cargo, cargo_defecto)
            hay_partido = idx_partido is not None and idx_partido < len(celdas)
            partido = celdas[idx_partido].strip() if hay_partido else None
            registros.append(
                {
                    "eleccion_tipo": eleccion_tipo,
                    "anno": anno,
                    "comuna_id": comuna_id,
                    "candidato": nombre,
                    "partido": partido or None,
                    "pacto": None,  # no disponible a nivel comuna en esta fuente
                    "votos": votos,
                    "porcentaje": porcentaje,
                    "electo": bool(texto_cargo),
                    "cargo": cargo,
                    "fuente_url": url,
                }
            )
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        # se borra y reinserta por (eleccion_tipo, anno): son datos
        # históricos fijos que no cambian entre corridas, así que no hace
        # falta upsert fila por fila — más simple reemplazar el bloque
        # completo de cada elección si se vuelve a correr.
        combinaciones = {(r["eleccion_tipo"], r["anno"]) for r in registros}
        for eleccion_tipo, anno in combinaciones:
            self.db.execute(
                "DELETE FROM resultado_electoral WHERE eleccion_tipo = ? AND anno = ?",
                (eleccion_tipo, anno),
            )
        for r in registros:
            self.db.execute(
                """
                INSERT INTO resultado_electoral
                    (eleccion_tipo, anno, comuna_id, candidato, partido, pacto,
                     votos, porcentaje, electo, cargo, fuente_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["eleccion_tipo"], r["anno"], r["comuna_id"], r["candidato"],
                    r["partido"], r["pacto"], r["votos"], r["porcentaje"],
                    r["electo"], r["cargo"], r["fuente_url"],
                ),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        import sqlite3

        self.db.row_factory = sqlite3.Row
        filas = self.db.execute(
            """
            SELECT eleccion_tipo, anno, comuna_id, candidato, partido, pacto,
                   votos, porcentaje, electo, cargo, fuente_url
            FROM resultado_electoral
            WHERE anno <= 2009
            ORDER BY anno DESC, eleccion_tipo, comuna_id, votos DESC
            """
        ).fetchall()

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "resultados-electorales-historicos.json").write_text(
            json.dumps([dict(f) for f in filas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Exportados {len(filas)} resultados electorales históricos a {PROCESSED_DIR}")


def _entidad(codigo: str) -> str:
    mapa = {
        "&aacute;": "á", "&eacute;": "é", "&iacute;": "í", "&oacute;": "ó", "&uacute;": "ú",
        "&ntilde;": "ñ", "&Aacute;": "Á", "&Eacute;": "É", "&Iacute;": "Í", "&Oacute;": "Ó",
        "&Uacute;": "Ú", "&Ntilde;": "Ñ", "&uuml;": "ü", "&amp;": "&", "&nbsp;": " ",
    }
    if codigo in mapa:
        return mapa[codigo]
    m = re.match(r"&#(\d+);", codigo)
    if m:
        return chr(int(m.group(1)))
    return codigo


if __name__ == "__main__":
    scraper = ScraperServelHistorico()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
