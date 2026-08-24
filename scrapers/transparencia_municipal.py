"""Presupuesto municipal (balance de ejecución presupuestaria) vía
portaltransparencia.cl (portal central).

Antes usaba el subdominio propio de cada municipio (ej. transparencia.
laserena.cl) — funcionaba pero no generaliza bien a 15 comunas: cada
municipio tiene su propia plataforma/parámetros, hay que descubrirlos uno
por uno. El portal central usa la MISMA estructura general (categorías Ley
20.285) para cualquier organismo, solo cambia `org=MUxxx` — pero dentro de
"Balance de Ejecución Presupuestaria" cada comuna igual arma su propio
árbol de sub-navegación y su propio formato de PDF (confirmado
investigando La Serena, Ovalle y Coquimbo — las 3 son distintas entre sí:
ver docs/05-scrapers.md). Por eso:

- `NAVEGACION_EXTRA`: pasos adicionales (texto de links a clickear, en
  orden) que cada comuna necesita ANTES de llegar al selector de año. Se
  arma a mano por comuna, investigada una por una — no hay atajo genérico
  confiable para esto.
- La extracción de columnas del PDF es dinámica (por texto de cabecera,
  igual que scrapers/personal_municipal.py) en vez de índice fijo — cada
  municipio ordena/nombra las columnas distinto, y el código de cuenta
  puede tener uno o más segmentos de prefijo antes del patrón
  "NN-00-000-000-000" que marca el nivel más agregado de la jerarquía.

El PDF se descarga con el propio contexto de Playwright (`page.request`),
no con httpx suelto: los PDFs alojados directamente en
portaltransparencia.cl (a diferencia de los alojados en el dominio propio
de la municipalidad) están protegidos contra requests simples.
"""

import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pdfplumber
from base import BaseScraper
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# comuna_id -> código de organismo en portaltransparencia.cl
# (verificados el 2026-08-24: fetch directo a la ficha del organismo,
# confirmando el nombre de la municipalidad en la página)
MUNICIPIOS_COQUIMBO = {
    "la-serena": "MU126",
    "coquimbo": "MU067",
    "andacollo": "MU007",
    "la-higuera": "MU122",
    "paihuano": "MU195",
    "vicuna": "MU335",
    "ovalle": "MU192",
    "combarbala": "MU060",
    "monte-patria": "MU175",
    "punitaqui": "MU238",
    "rio-hurtado": "MU272",
    "illapel": "MU110",
    "canela": "MU026",
    "los-vilos": "MU157",
    "salamanca": "MU279",
}

# comuna_id -> lista de textos de link a clickear en orden, después de la
# categoría y antes del selector de año. Investigado a mano por comuna.
NAVEGACION_EXTRA: dict[str, list[str]] = {
    "coquimbo": ["Ingresos y Gastos"],  # el área "Municipal" la agrega el fallback genérico
}

# las etiquetas de categoría las escribe cada municipio a mano en el portal
# central: hay variantes con typos/acentos distintos (ej. Ovalle escribe
# "Ejecuciòn" con acento grave) — se matchea tolerando eso.
BALANCE_EJECUCION_RE = re.compile(r"Balances? de Ejecuci.n Presupuestaria", re.IGNORECASE)


def _es_codigo_nivel_top(codigo: str) -> bool:
    """'03-00-000-000-000' (La Serena) y '115-03-00-000-000-000' (Coquimbo,
    con prefijo de fondo) son ambos nivel top: los últimos 4 segmentos son
    00/000/000/000 y el segmento justo antes tiene 2 dígitos."""
    partes = codigo.strip().split("-")
    if len(partes) < 5:
        return False
    cola = partes[-4:] == ["00", "000", "000", "000"]
    return cola and len(partes[-5]) == 2 and partes[-5].isdigit()


def _monto_a_numero(texto: str) -> float | None:
    texto = (texto or "").strip().replace(".", "").replace(",", "")
    if not texto or texto in ("-",):
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _mapear_columnas_pdf(tabla: list[list], tipo: str) -> dict[str, int] | None:
    """El encabezado real puede venir repartido en 2-3 filas con celdas
    fusionadas (None) — se combina el texto de las primeras filas por
    columna antes de buscar las cabeceras que importan."""
    n_header = min(3, len(tabla))
    combinado = ["" for _ in range(len(tabla[0]))]
    for fila in tabla[:n_header]:
        for i, celda in enumerate(fila):
            if celda:
                combinado[i] = (combinado[i] + " " + celda).strip().upper()

    idx_monto = None
    for i, texto in enumerate(combinado):
        if tipo == "ingreso" and "PERCIBID" in texto:
            idx_monto = i
        elif tipo == "gasto" and ("OBLIGACION" in texto or "DEVENGAD" in texto):
            idx_monto = i
    if idx_monto is None:
        return None
    return {"codigo": 0, "denominacion": 1, "monto": idx_monto}


class ScraperTransparenciaMunicipal(BaseScraper):
    """Recolecta el balance de ejecución presupuestaria más reciente (con
    documento disponible) de cada municipalidad configurada."""

    nombre = "transparencia_municipal"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        registros = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            for comuna_id, org_code in MUNICIPIOS_COQUIMBO.items():
                try:
                    pdf_url, anno = self._encontrar_pdf_mas_reciente(page, comuna_id, org_code)
                    print(f"[{comuna_id}] pdf_url={pdf_url} anno={anno}")
                    if pdf_url:
                        nuevos = self._descargar_y_parsear(page, comuna_id, pdf_url, anno)
                        print(f"[{comuna_id}] {len(nuevos)} filas parseadas")
                        registros.extend(nuevos)
                except Exception as e:
                    print(f"[{comuna_id}] ERROR: {e}")
                    self.stats["errores"] += 1
                time.sleep(2)  # rate limiting entre comunas
            browser.close()
        return registros

    def _ir_a_categoria(self, page, comuna_id: str) -> None:
        page.locator("a", has_text=BALANCE_EJECUCION_RE).first.click()
        page.wait_for_timeout(1800)
        for paso in NAVEGACION_EXTRA.get(comuna_id, []):
            page.locator("a", has_text=re.compile(f"^{re.escape(paso)}$")).first.click()
            page.wait_for_timeout(1800)

        # varias comunas piden elegir área (Municipal/Educación/Salud) antes
        # de mostrar los años — si no hay años visibles todavía pero sí un
        # link "Municipal" exacto, se entra ahí por defecto (la gestión
        # municipal en sí, no sus corporaciones).
        hay_anno = page.locator("a", has_text=re.compile(r"^(Año )?\d{4}$")).count()
        if not hay_anno:
            municipal = page.locator("a", has_text=re.compile(r"^MUNICIPAL$", re.IGNORECASE))
            if municipal.count():
                municipal.first.click()
                page.wait_for_timeout(1800)

    def _encontrar_pdf_mas_reciente(
        self, page, comuna_id: str, org_code: str
    ) -> tuple[str | None, int | None]:
        url = (
            "https://www.portaltransparencia.cl/PortalPdT/directorio-de-organismos-regulados/"
            f"?org={org_code}"
        )
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        self._ir_a_categoria(page, comuna_id)

        annos_texto = [
            a.text_content().strip()
            for a in page.locator("a", has_text=re.compile(r"^(Año )?\d{4}$")).all()
        ]

        for texto_anno in annos_texto[:3]:  # más reciente primero; hasta 3 años atrás
            page.locator("a", has_text=texto_anno).first.click()
            page.wait_for_timeout(2000)

            # algunas comunas agregan un nivel extra de sub-tipo de reporte
            # antes de mostrar la tabla (ej. Ovalle: "Balances de Ejecución
            # Trimestral" vs "Balance de comprobación...").
            if not page.locator("table.table-responsive-lg tbody tr").count():
                sub = page.locator("a", has_text=re.compile("trimestral", re.IGNORECASE))
                if sub.count():
                    sub.first.click()
                    page.wait_for_timeout(2000)

            for fila in page.locator("table.table-responsive-lg tbody tr").all():
                link = fila.locator("a").first
                if link.count() and link.get_attribute("href"):
                    href = link.get_attribute("href")
                    pdf_url = (
                        href if href.startswith("http") else f"https://www.portaltransparencia.cl{href}"
                    )
                    anno = int(re.search(r"\d{4}", texto_anno).group())
                    return pdf_url, anno

            # sin documento disponible en este año: volver a mostrar la lista de años
            self._ir_a_categoria(page, comuna_id)

        return None, None

    def _descargar_y_parsear(self, page, comuna_id: str, pdf_url: str, anno: int) -> list[dict]:
        resp = page.request.get(pdf_url)
        if resp.status != 200:
            return []
        tmp_path = ROOT / "data" / "raw" / f"presupuesto_{comuna_id}_{anno}.pdf"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(resp.body())

        registros = []
        with pdfplumber.open(tmp_path) as pdf:
            tipo_actual = None
            for pagina in pdf.pages:
                texto = pagina.extract_text() or ""
                texto_up = texto.upper()
                if "INGRESOS DE" in texto or "BALANCE PRESUPUESTARIO DE INGRESOS" in texto_up:
                    tipo_actual = "ingreso"
                elif "GASTOS DE" in texto or "BALANCE PRESUPUESTARIO DE GASTOS" in texto_up:
                    tipo_actual = "gasto"
                if tipo_actual is None:
                    continue

                # no todas las comunas declaran los montos en miles de $ (ej.
                # La Serena sí, Coquimbo no) — se detecta por página en vez
                # de asumirlo fijo, para no inflar x1000 por error.
                multiplicador = 1000 if re.search(r"MILES\s*\$", texto_up) else 1

                tabla = pagina.extract_table()
                if not tabla:
                    continue
                columnas = _mapear_columnas_pdf(tabla, tipo_actual)
                if columnas is None:
                    continue

                for fila in tabla:
                    if not fila or not fila[columnas["codigo"]]:
                        continue
                    codigo = fila[columnas["codigo"]].strip()
                    if not _es_codigo_nivel_top(codigo):
                        continue
                    categoria = (fila[columnas["denominacion"]] or "").strip().replace("\n", " ")
                    monto = _monto_a_numero(fila[columnas["monto"]])
                    if not categoria or monto is None:
                        continue
                    registros.append(
                        {
                            "comuna_id": comuna_id,
                            "anno": anno,
                            "tipo": tipo_actual,
                            "categoria": categoria,
                            "subcategoria": codigo,
                            "monto": monto * multiplicador,
                            "fuente_url": pdf_url,
                        }
                    )
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        comunas = tuple(MUNICIPIOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(comunas))
        self.db.execute(
            f"DELETE FROM presupuesto_municipal WHERE comuna_id IN ({placeholders})", comunas
        )
        ahora = datetime.now().isoformat()
        for r in registros:
            self.db.execute(
                """
                INSERT INTO presupuesto_municipal
                    (comuna_id, anno, tipo, categoria, subcategoria, monto,
                     fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["comuna_id"],
                    r["anno"],
                    r["tipo"],
                    r["categoria"],
                    r["subcategoria"],
                    r["monto"],
                    r["fuente_url"],
                    ahora,
                ),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        comunas = tuple(MUNICIPIOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(comunas))
        filas = self.db.execute(
            f"""
            SELECT comuna_id, anno, tipo, categoria, subcategoria, monto, fuente_url
            FROM presupuesto_municipal
            WHERE comuna_id IN ({placeholders})
            ORDER BY comuna_id, anno DESC, tipo, monto DESC
            """,
            comunas,
        ).fetchall()

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "presupuesto-municipal.json").write_text(
            json.dumps([dict(f) for f in filas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Exportados {len(filas)} registros de presupuesto a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperTransparenciaMunicipal()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
