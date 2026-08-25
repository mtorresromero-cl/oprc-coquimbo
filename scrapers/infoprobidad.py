"""Declaraciones de patrimonio e intereses, vía infoprobidad.cl (iniciativa
del Consejo para la Transparencia y la Contraloría General de la República).

El dataset masivo de "Datos Abiertos" (datos.cplt.cl, CSV/JSON/SPARQL) está
bloqueado a nivel de infraestructura (403 de un Azure Application Gateway en
TODAS las rutas, incluso navegando con un browser real) — no se intenta
evadir ese bloqueo. En su lugar se usa el buscador propio del sitio
(www.infoprobidad.cl), que sí responde con normalidad.

Solo se guarda el **resumen agregado** de la declaración vigente (cantidad
de bienes inmuebles, vehículos, sociedades, monto de valores, si tiene
pasivos y su monto) — el mismo criterio que personal_municipal.py: totales
comparables entre autoridades, no el detalle línea por línea de cada bien.

Búsqueda: el listado (/Home/Listado) se filtra por Apellido Materno (la
grilla es Kendo UI — icono de filtro por columna, no una URL con query
params). Se busca por apellido materno porque en un nombre chileno es
inequívocamente la última palabra, a diferencia del apellido paterno o el
nombre de pila (pueden ser compuestos, ej. "Juan Carlos"). Entre los
resultados se toma la primera fila cuyas palabras (nombres + paterno +
materno) coincidan con nombre_completo — la grilla ya viene ordenada por
fecha de declaración descendente, así que es la más reciente de esa
persona.
"""

import json
import re
import sqlite3
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from base import BaseScraper
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

LISTADO_URL = "https://www.infoprobidad.cl/Home/Listado"


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.upper().strip()


_TILDES = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")


def _para_busqueda(texto: str) -> str:
    # el buscador del sitio exige la "ñ" tal cual (buscar "NUNEZ" sin ñ da 0
    # resultados) pero es inconsistente con los acentos de vocales — el
    # mismo apellido aparece con y sin tilde según el año de la declaración
    # (ej. "NÚÑEZ" en 2021, "NUÑEZ" desde 2022) — así que se buscan sin
    # acento en la vocal pero conservando la ñ.
    return (texto or "").translate(_TILDES).upper().strip()


def _monto(texto: str) -> float:
    texto = re.sub(r"[^\d]", "", texto or "")
    return float(texto) if texto else 0.0


# a veces la misma persona tiene varias declaraciones con la misma fecha,
# vigentes por distintos motivos (ej. un senador que también es dirigente
# de partido) — se prefiere la fila cuyo cargo coincide con el cargo real
# de la autoridad en nuestro catálogo, para no quedarnos con la del rol
# secundario por simple orden de aparición.
CARGO_PALABRA_CLAVE = {
    "alcalde": "ALCALDE",
    "concejal": "CONCEJAL",
    "core": "CONSEJERO REGIONAL",
    "diputado": "DIPUTADO",
    "senador": "SENADOR",
    "gobernador": "GOBERNADOR",
}


class ScraperInfoProbidad(BaseScraper):
    """Resumen de declaraciones de patrimonio de las autoridades del catálogo."""

    nombre = "infoprobidad"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        autoridades = self.db.execute(
            "SELECT id, nombre_completo, cargo FROM autoridad WHERE activo = 1"
        ).fetchall()

        resultado = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for autoridad_id, nombre_completo, cargo in autoridades:
                try:
                    fila = self._buscar(browser, nombre_completo, cargo)
                except Exception as e:
                    print(f"[{autoridad_id}] ERROR búsqueda: {e}")
                    self.stats["errores"] += 1
                    continue

                if fila is None:
                    print(f"[{autoridad_id}] sin declaración encontrada")
                    continue

                try:
                    resumen = self._extraer_resumen(browser, fila["url"], fila["cargo_grilla"])
                except Exception as e:
                    print(f"[{autoridad_id}] ERROR ficha: {e}")
                    self.stats["errores"] += 1
                    continue

                resumen["autoridad_id"] = autoridad_id
                resumen["fuente_url"] = fila["url"]
                resultado.append(resumen)
                print(
                    f"[{autoridad_id}] {resumen['fecha_declaracion']} "
                    f"inmuebles={resumen['bienes_inmuebles_n']} "
                    f"vehiculos={resumen['vehiculos_n']} "
                    f"pasivos={resumen['pasivos_monto']}"
                )
                time.sleep(1)
            browser.close()
        return resultado

    def _buscar(self, browser, nombre_completo: str, cargo: str | None = None) -> dict | None:
        # en un nombre chileno "Nombre(s) ApellidoPaterno ApellidoMaterno", el
        # paterno y materno son siempre las últimas palabras — a diferencia
        # del nombre de pila, que puede ser compuesto (ej. "Juan Carlos").
        # El materno también puede ser compuesto con preposición (ej. "De
        # La Vega", "de la Rivera") — se detecta por las palabras previas a
        # la última siendo "de"/"del"/"la"/etc. Filtrar solo por materno
        # deja miles de resultados paginados (no alcanza con leer la
        # primera página); combinando paterno + materno la grilla queda
        # acotada a una sola página.
        palabras = nombre_completo.strip().split()
        preposiciones = {"de", "del", "la", "las", "los"}
        idx_materno = len(palabras) - 1
        while idx_materno > 1 and palabras[idx_materno - 1].lower() in preposiciones:
            idx_materno -= 1
        apellido_materno_palabras = palabras[idx_materno:]
        apellido_paterno_palabra = palabras[idx_materno - 1] if idx_materno > 0 else ""

        apellido_materno = _para_busqueda(" ".join(apellido_materno_palabras))
        apellido_paterno = _para_busqueda(apellido_paterno_palabra)
        apellido_materno_norm = _normalizar(" ".join(apellido_materno_palabras))
        apellido_paterno_norm = _normalizar(apellido_paterno_palabra)
        # el primer nombre de pila es lo único razonablemente estable: los
        # nombres compuestos (ej. "Daniel Ignacio") a veces figuran
        # completos y a veces solo con el primero, según el año de la
        # declaración — exigir el nombre completo deja fuera declaraciones
        # reales.
        nombres_palabras = palabras[: max(idx_materno - 1, 0)]
        primer_nombre = _normalizar(nombres_palabras[0]) if nombres_palabras else None

        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(LISTADO_URL, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        self._filtrar_columna(page, "Apellido Paterno", apellido_paterno)
        self._filtrar_columna(page, "Apellido Materno", apellido_materno)

        filas = page.locator("table tbody tr").all()
        coincidencias = []
        for fila in filas:
            celdas = fila.locator("td").all()
            if len(celdas) < 7:
                continue
            nombres_fila = _normalizar(celdas[2].inner_text())
            paterno_fila = _normalizar(celdas[3].inner_text())
            materno_fila = _normalizar(celdas[4].inner_text())
            coincide = (
                paterno_fila == apellido_paterno_norm
                and materno_fila == apellido_materno_norm
                and (primer_nombre is None or primer_nombre in nombres_fila.split())
            )
            if coincide:
                href = fila.locator("a").first.get_attribute("href")
                if href:
                    cargo_grilla = celdas[5].inner_text().strip()
                    servicio_grilla = celdas[6].inner_text().strip()
                    coincidencias.append(
                        {
                            "url": "https://www.infoprobidad.cl" + href.replace("..", ""),
                            "texto_cargo": _normalizar(cargo_grilla + " " + servicio_grilla),
                            "cargo_grilla": cargo_grilla,
                            "servicio_grilla": servicio_grilla,
                        }
                    )

        page.close()
        if not coincidencias:
            return None

        palabra_clave = CARGO_PALABRA_CLAVE.get(cargo or "")
        if palabra_clave:
            for c in coincidencias:
                if palabra_clave in c["texto_cargo"]:
                    return c
        return coincidencias[0]

    def _filtrar_columna(self, page, columna: str, valor: str) -> None:
        page.locator("th", has_text=columna).locator("a, i, button").first.click()
        page.wait_for_timeout(500)
        page.locator("input[type=text]").last.fill(valor)
        page.get_by_role("button", name="Filtrar").click()
        page.wait_for_timeout(1800)

    def _extraer_resumen(self, browser, url: str, cargo_grilla: str | None = None) -> dict:
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        texto = page.locator("body").inner_text()
        page.close()

        # la fecha aparece como DD-MM-YYYY en la ficha; se guarda en ISO
        # (YYYY-MM-DD) porque un TEXT en formato DD-MM-YYYY no ordena
        # cronológicamente como string (ej. "25-01-2026" > "17-03-2026").
        fecha_m = re.search(r"(\d{2})-(\d{2})-(\d{4})\s+(.+)", texto)
        fecha_declaracion = (
            f"{fecha_m.group(3)}-{fecha_m.group(2)}-{fecha_m.group(1)}" if fecha_m else None
        )
        tipo_declaracion = fecha_m.group(4).strip() if fecha_m else None

        organismo_m = re.search(r"Organismo:\s*(.+)", texto)
        organismo = organismo_m.group(1).strip() if organismo_m else None

        # la sección "Cargo" de la ficha lista TODOS los cargos históricos
        # de la persona, no solo el de esta declaración — se usa el cargo
        # tal como aparece en la fila de la grilla de búsqueda, que sí es
        # específico de esta declaración.
        cargo_declarado = cargo_grilla

        def _total_seccion(patron_total: str) -> float:
            m = re.search(patron_total, texto)
            return _monto(m.group(1)) if m else 0.0

        sociedades_m = re.search(r"Total (\d+) Comunidades, sociedades, empresas declaradas", texto)
        inmuebles_m = re.search(r"Total (\d+) del declarante", texto)
        vehiculos_m = re.search(r"Total (\d+) Bien Mueble declarado", texto)
        valores_monto = _total_seccion(r"Total CLP \$ ([\d.]+)")
        pasivos_tiene = "Pasivos\nSi posee" in texto
        pasivos_monto = _total_seccion(r"Pasivos\n(?:Si|No) posee\n\nTotal \$ ([\d.]+)")

        return {
            "fecha_declaracion": fecha_declaracion,
            "tipo_declaracion": tipo_declaracion,
            "cargo_declarado": cargo_declarado,
            "organismo": organismo,
            "bienes_inmuebles_n": int(inmuebles_m.group(1)) if inmuebles_m else 0,
            "vehiculos_n": int(vehiculos_m.group(1)) if vehiculos_m else 0,
            "sociedades_n": int(sociedades_m.group(1)) if sociedades_m else 0,
            "valores_monto": valores_monto,
            "pasivos_tiene": pasivos_tiene,
            "pasivos_monto": pasivos_monto,
        }

    def procesar(self, datos: list[dict]) -> list[dict]:
        return datos

    def guardar(self, datos: list[dict]) -> None:
        # upsert por (autoridad_id, fecha_declaracion): cada declaración es
        # un evento propio en el tiempo, no un estado que se reemplaza —
        # borrar antes de insertar destruía declaraciones anteriores de la
        # misma autoridad e impedía comparar cómo cambió su patrimonio.
        ahora = datetime.now().isoformat()

        for d in datos:
            self.db.execute(
                """
                INSERT INTO declaracion_patrimonio
                    (autoridad_id, fecha_declaracion, tipo_declaracion, cargo_declarado,
                     organismo, bienes_inmuebles_n, vehiculos_n, sociedades_n,
                     valores_monto, pasivos_tiene, pasivos_monto, fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(autoridad_id, fecha_declaracion) DO UPDATE SET
                    tipo_declaracion = excluded.tipo_declaracion,
                    cargo_declarado = excluded.cargo_declarado,
                    organismo = excluded.organismo,
                    bienes_inmuebles_n = excluded.bienes_inmuebles_n,
                    vehiculos_n = excluded.vehiculos_n,
                    sociedades_n = excluded.sociedades_n,
                    valores_monto = excluded.valores_monto,
                    pasivos_tiene = excluded.pasivos_tiene,
                    pasivos_monto = excluded.pasivos_monto,
                    fuente_url = excluded.fuente_url,
                    actualizado_en = excluded.actualizado_en
                """,
                (
                    d["autoridad_id"], d["fecha_declaracion"], d["tipo_declaracion"],
                    d["cargo_declarado"], d["organismo"], d["bienes_inmuebles_n"],
                    d["vehiculos_n"], d["sociedades_n"], d["valores_monto"],
                    int(d["pasivos_tiene"]), d["pasivos_monto"], d["fuente_url"], ahora,
                ),
            )
            self.stats["nuevos"] += 1

        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        filas = self.db.execute(
            """
            SELECT autoridad_id, fecha_declaracion, tipo_declaracion, cargo_declarado,
                   organismo, bienes_inmuebles_n, vehiculos_n, sociedades_n,
                   valores_monto, pasivos_tiene, pasivos_monto, fuente_url
            FROM declaracion_patrimonio
            ORDER BY autoridad_id, fecha_declaracion DESC
            """
        ).fetchall()
        (PROCESSED_DIR / "declaracion-patrimonio.json").write_text(
            json.dumps([dict(f) for f in filas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Exportadas {len(filas)} declaraciones de patrimonio a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperInfoProbidad()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
