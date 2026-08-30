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
from personal_municipal import MES_NUM
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


CODIGO_AL_INICIO_RE = re.compile(r"^([\d-]{5,})\s+(.+)$", re.DOTALL)


def _separar_codigo_denominacion(celda: str) -> tuple[str, str] | None:
    """Algunas comunas (ej. Combarbalá, Monte Patria) no separan código y
    denominación en columnas distintas: vienen juntos en una sola celda
    ("115-00-00-000-000-000 DEUDORES PRESUPUESTARIOS", a veces con la
    denominación partida en varias líneas alrededor del código). Se
    intenta extraer el código del inicio del texto; si no calza, se
    prueba buscándolo en cualquier línea de la celda."""
    celda = (celda or "").strip()
    m = CODIGO_AL_INICIO_RE.match(celda)
    if m:
        return m.group(1), m.group(2).replace("\n", " ").strip()
    for linea in celda.split("\n"):
        linea = linea.strip()
        if re.fullmatch(r"[\d-]{5,}", linea):
            resto = celda.replace(linea, "", 1).replace("\n", " ").strip()
            return linea, resto
    return None


def _monto_a_numero(texto: str) -> float | None:
    # el propio texto extraído del PDF a veces trae un espacio suelto en
    # medio de un número (ej. "8 9.066.402" en vez de "89.066.402",
    # confirmado en el PDF de Coquimbo) — un artefacto real de extracción,
    # no un separador de miles: se remueven todos los espacios, no solo
    # los de los extremos.
    texto = re.sub(r"\s+", "", texto or "").replace(".", "").replace(",", "")
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
        elif tipo == "gasto" and any(k in texto for k in ("OBLIGACION", "DEVENGAD", "OBLIGADO")):
            idx_monto = i
    if idx_monto is None:
        return None
    return {"codigo": 0, "denominacion": 1, "monto": idx_monto}


def _parsear_pdf(
    tmp_path: Path, comuna_id: str, anno: int, tipo_forzado: str | None, fuente_url: str
) -> list[dict]:
    """Separada de _descargar_y_parsear (que además navega y descarga) para
    poder re-parsear un PDF ya guardado en disco sin necesitar una página
    de Playwright viva — útil para depurar o re-procesar una comuna
    puntual sin repetir la navegación de las otras 14."""
    registros: list[dict] = []
    with pdfplumber.open(tmp_path) as pdf:
        # tipo_actual y columnas_actual se mantienen entre páginas que no
        # repiten el encabezado (tablas de varias páginas, ej. Coquimbo: la
        # sección de ingresos por sí sola ocupa 2 páginas) — antes esto
        # solo se hacía para tipo_actual, así que cualquier página de
        # continuación sin encabezado propio se descartaba entera
        # (columnas=None), perdiendo categorías completas como el Fondo
        # Común Municipal. columnas_actual solo se reinicia cuando una
        # página nueva declara explícitamente una sección distinta a la
        # anterior — arrastrarla entre ingresos y gastos sería un bug
        # real, ya que cada sección usa una columna de monto distinta
        # (PERCIBIDO vs DEVENGADO/PAGADO).
        tipo_actual = tipo_forzado
        columnas_actual = None
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            texto_up = texto.upper()
            tabla = pagina.extract_table()
            if not tabla:
                continue

            # si el árbol de navegación ya separó ingresos de gastos (ej.
            # Vicuña), el PDF trae un solo tipo y se respeta tipo_forzado
            # aunque el texto de alguna página mencione la palabra
            # "gastos" de pasada (ej. en un total).
            if not tipo_forzado:
                tipo_anterior = tipo_actual
                if "INGRESOS DE" in texto or "BALANCE PRESUPUESTARIO DE INGRESOS" in texto_up:
                    tipo_actual = "ingreso"
                elif "GASTOS DE" in texto or "BALANCE PRESUPUESTARIO DE GASTOS" in texto_up:
                    tipo_actual = "gasto"
                else:
                    # el título de la sección no siempre dice
                    # "ingresos"/"gastos" explícito (ej. Combarbalá:
                    # "Informe General Presupuestario" combinado) — el
                    # primer dígito del código de cuenta sí es universal
                    # en el clasificador presupuestario chileno: 1xx =
                    # ingresos, 2xx = gastos.
                    primeros_digitos = [
                        fila[0].strip()[0]
                        for fila in tabla
                        if fila and fila[0] and fila[0].strip()[:1].isdigit()
                    ]
                    if primeros_digitos:
                        mas_comun = max(set(primeros_digitos), key=primeros_digitos.count)
                        if mas_comun == "1":
                            tipo_actual = "ingreso"
                        elif mas_comun == "2":
                            tipo_actual = "gasto"
                if tipo_actual != tipo_anterior:
                    columnas_actual = None
            if tipo_actual is None:
                continue

            # no todas las comunas declaran los montos en miles de $ (ej.
            # La Serena sí, Coquimbo no) — se detecta por página en vez de
            # asumirlo fijo, para no inflar x1000 por error.
            multiplicador = 1000 if re.search(r"MILES\s*\$", texto_up) else 1

            columnas = _mapear_columnas_pdf(tabla, tipo_actual)
            if columnas is not None:
                columnas_actual = columnas
            elif columnas_actual is not None:
                columnas = columnas_actual
            else:
                continue

            for fila in tabla:
                if not fila or not fila[columnas["codigo"]]:
                    continue
                codigo = fila[columnas["codigo"]].strip()
                categoria = (fila[columnas["denominacion"]] or "").strip().replace("\n", " ")
                if not _es_codigo_nivel_top(codigo):
                    # código y denominación pueden venir juntos en una sola
                    # celda (Combarbalá, Monte Patria) en vez de en
                    # columnas separadas.
                    separado = _separar_codigo_denominacion(fila[columnas["codigo"]])
                    if not separado or not _es_codigo_nivel_top(separado[0]):
                        continue
                    codigo, categoria = separado
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
                        "fuente_url": fuente_url,
                    }
                )
    return registros


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
                    pdfs = self._encontrar_pdfs(page, comuna_id, org_code)
                    print(f"[{comuna_id}] pdfs={pdfs}")
                    for pdf_url, anno, tipo_forzado in pdfs:
                        nuevos = self._descargar_y_parsear(
                            page, comuna_id, pdf_url, anno, tipo_forzado
                        )
                        print(f"[{comuna_id}] {len(nuevos)} filas parseadas de {pdf_url}")
                        registros.extend(nuevos)
                except Exception as e:
                    print(f"[{comuna_id}] ERROR: {e}")
                    self.stats["errores"] += 1
                time.sleep(2)  # rate limiting entre comunas
            browser.close()
        return registros

    def _ir_a_categoria(self, page, comuna_id: str, url: str | None = None) -> None:
        # se navega siempre desde una carga fresca de la página (en vez de
        # asumir que el link de categoría sigue disponible en el DOM
        # actual): tras bajar varios niveles en el árbol de navegación
        # AJAX, ese link puede quedar fuera del DOM renderizado y el click
        # queda esperando indefinidamente.
        if url:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        page.locator("a", has_text=BALANCE_EJECUCION_RE).first.click()
        page.wait_for_timeout(2500)
        for paso in NAVEGACION_EXTRA.get(comuna_id, []):
            page.locator("a", has_text=re.compile(f"^{re.escape(paso)}$")).first.click()
            page.wait_for_timeout(2500)

        # algunas comunas (ej. Vicuña) repiten el link de "Balance de
        # Ejecución Presupuestaria" una vez más antes de mostrar cualquier
        # otra opción — sin ese segundo click no aparecen ni años ni área.
        hay_anno = page.locator("a", has_text=re.compile(r"^(Año )?\d{4}$")).count()
        area_re = re.compile(r"^MUNICIPAL(IDAD)?$", re.IGNORECASE)
        hay_area = page.locator("a", has_text=area_re).count()
        if not hay_anno and not hay_area:
            repetido = page.locator("a", has_text=BALANCE_EJECUCION_RE)
            if repetido.count():
                repetido.last.click()
                page.wait_for_timeout(2500)

        # varias comunas piden elegir área (Municipal/Educación/Salud) antes
        # de mostrar los años — si no hay años visibles todavía pero sí un
        # link "Municipal" exacto, se entra ahí por defecto (la gestión
        # municipal en sí, no sus corporaciones).
        hay_anno = page.locator("a", has_text=re.compile(r"^(Año )?\d{4}$")).count()
        if not hay_anno:
            municipal = page.locator("a", has_text=re.compile(r"^MUNICIPAL(IDAD)?$", re.IGNORECASE))
            if municipal.count():
                municipal.first.click()
                page.wait_for_timeout(2500)

    def _profundizar_hasta_tabla(self, page, max_pasos: int = 5) -> bool:
        """Tras elegir un año, algunas comunas piden 1-2 clicks más antes de
        mostrar la tabla con los documentos: un sub-tipo "Balances de
        Ejecución Trimestral" (Ovalle), un link "BEP - Municipal" (Río
        Hurtado, o el que sigue después del trimestral en Ovalle), el
        área "Municipal/Municipalidad" si no se eligió antes del año
        (Combarbalá, Salamanca), o directamente un mes (Combarbalá publica
        el balance mensual, como el personal municipal, no trimestral).
        Prueba estas opciones en orden de prioridad, una por pasada, sin
        repetir el mismo texto ya clickeado (para no quedar en loop si el
        link persiste en el breadcrumb)."""
        if page.locator("table.table-responsive-lg tbody tr").count():
            return True
        meses_regex = re.compile(
            r"\b(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto"
            r"|Septiembre|Octubre|Noviembre|Diciembre)\b",
            re.IGNORECASE,
        )
        candidatos = [
            re.compile(r"^Municipal(idad)?$", re.IGNORECASE),
            re.compile(r"^BEP\s*-\s*Municipal", re.IGNORECASE),
            re.compile(r"Trimestral", re.IGNORECASE),
        ]
        ya_clickeados: set[str] = set()
        for _ in range(max_pasos):
            avanzo = False

            # los meses no se eligen por posición en el DOM (algunas
            # comunas los listan de más antiguo a más reciente, otras al
            # revés — mismo problema ya visto en personal_municipal.py):
            # se elige por el número de mes más alto.
            meses = [
                m
                for m in page.locator("a", has_text=meses_regex).all()
                if "histórico" not in (m.inner_text() or "").lower()
            ]
            if meses:

                def _numero_mes(m):
                    match = meses_regex.search(m.inner_text() or "")
                    return MES_NUM.get(match.group(1).lower(), 0) if match else 0

                mes_mas_reciente = max(meses, key=_numero_mes)
                texto_mes = (mes_mas_reciente.inner_text() or "").strip()
                if texto_mes not in ya_clickeados:
                    ya_clickeados.add(texto_mes)
                    mes_mas_reciente.click()
                    page.wait_for_timeout(2200)
                    avanzo = True

            if not avanzo:
                for patron in candidatos:
                    loc = page.locator("a", has_text=patron)
                    if not loc.count():
                        continue
                    elemento = loc.last
                    texto = (elemento.inner_text() or "").strip()
                    if not texto or texto in ya_clickeados:
                        continue
                    ya_clickeados.add(texto)
                    elemento.click()
                    page.wait_for_timeout(2200)
                    avanzo = True
                    break

            # algunas comunas (ej. Combarbalá) no muestran una tabla con el
            # documento: el link del mes navega directamente al archivo,
            # alojado fuera del portal (Dropbox, Drive, dominio propio).
            if "portaltransparencia.cl" not in page.url:
                return True
            if page.locator("table.table-responsive-lg tbody tr").count():
                return True
            if not avanzo:
                return False
        return False

    def _pdf_de_fila_mas_reciente(self, page) -> str | None:
        """Algunas comunas (ej. Ovalle) listan varios períodos en la misma
        tabla, varios de ellos "No-Bep.pdf" (placeholder sin datos reales
        para ese mes) — se descarta ese nombre de archivo y se toma la
        primera fila real."""
        for fila in page.locator("table.table-responsive-lg tbody tr").all():
            link = fila.locator("a").first
            if not link.count() or not link.get_attribute("href"):
                continue
            href = link.get_attribute("href")
            if re.search(r"no.?bep", href, re.IGNORECASE):
                continue
            return href if href.startswith("http") else f"https://www.portaltransparencia.cl{href}"
        return None

    def _pdf_en_anno_actual(self, page) -> str | None:
        if not page.locator("table.table-responsive-lg tbody tr").count():
            if not self._profundizar_hasta_tabla(page):
                return None
        # el drilling puede haber terminado navegando directamente al
        # archivo (fuera del portal) en vez de mostrar una tabla.
        if "portaltransparencia.cl" not in page.url:
            return page.url
        return self._pdf_de_fila_mas_reciente(page)

    def _encontrar_pdfs(
        self, page, comuna_id: str, org_code: str
    ) -> list[tuple[str, int, str | None]]:
        """Devuelve [(pdf_url, año, tipo_forzado)]. tipo_forzado es None
        cuando el PDF trae ingresos y gastos juntos (se detecta por texto
        al parsear) — algunas comunas (ej. Vicuña) separan Ingresos y
        Gastos en dos árboles de navegación independientes, cada uno con
        su propio PDF de un solo tipo; ahí sí se fuerza el tipo porque el
        PDF no trae ambas secciones."""
        url = (
            "https://www.portaltransparencia.cl/PortalPdT/directorio-de-organismos-regulados/"
            f"?org={org_code}"
        )
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        self._ir_a_categoria(page, comuna_id)

        ingresos_link = page.locator("a", has_text=re.compile(r"^Ingresos$", re.IGNORECASE))
        gastos_link = page.locator("a", has_text=re.compile(r"^Gastos$", re.IGNORECASE))
        if ingresos_link.count() and gastos_link.count():
            resultado = []
            for tipo, patron in (("ingreso", r"^Ingresos$"), ("gasto", r"^Gastos$")):
                # se reinicia la navegación en cada rama: tras recorrer
                # Ingresos hasta el PDF, la página quedó varios niveles
                # abajo de ese árbol y el link "Gastos" (hermano, al mismo
                # nivel que Ingresos) ya no está visible desde ahí.
                self._ir_a_categoria(page, comuna_id, url)
                rama = page.locator("a", has_text=re.compile(patron, re.IGNORECASE))
                rama.last.click()
                page.wait_for_timeout(2200)
                annos_texto = [
                    a.text_content().strip()
                    for a in page.locator("a", has_text=re.compile(r"^(Año )?\d{4}$")).all()
                ]
                for texto_anno in annos_texto[:3]:
                    page.locator("a", has_text=texto_anno).first.click()
                    page.wait_for_timeout(2000)
                    pdf_url = self._pdf_en_anno_actual(page)
                    if pdf_url:
                        anno = int(re.search(r"\d{4}", texto_anno).group())
                        resultado.append((pdf_url, anno, tipo))
                        break
                    self._ir_a_categoria(page, comuna_id, url)
                    rama = page.locator("a", has_text=re.compile(patron, re.IGNORECASE))
                    rama.last.click()
                    page.wait_for_timeout(2200)
            return resultado

        annos_texto = [
            a.text_content().strip()
            for a in page.locator("a", has_text=re.compile(r"^(Año )?\d{4}$")).all()
        ]

        for texto_anno in annos_texto[:6]:  # más reciente primero; hasta 6 años atrás
            page.locator("a", has_text=texto_anno).first.click()
            page.wait_for_timeout(2000)

            pdf_url = self._pdf_en_anno_actual(page)
            if pdf_url:
                anno = int(re.search(r"\d{4}", texto_anno).group())
                return [(pdf_url, anno, None)]

            # sin documento disponible en este año: volver a mostrar la lista de años
            self._ir_a_categoria(page, comuna_id, url)

        return []

    def _descargar_y_parsear(
        self, page, comuna_id: str, pdf_url: str, anno: int, tipo_forzado: str | None = None
    ) -> list[dict]:
        # algunas comunas alojan el PDF fuera del portal, en un link de
        # vista en vez del archivo directo (Vicuña: Google Drive;
        # Combarbalá: Dropbox) — se convierte al endpoint de descarga
        # directa para el fetch, pero se guarda la URL de vista original
        # como fuente_url (la de descarga directa no sirve para que una
        # persona la abra a mano).
        fuente_url = pdf_url
        drive_id = re.search(r"drive\.google\.com/file/d/([^/]+)", pdf_url)
        if drive_id:
            descarga_url = f"https://drive.google.com/uc?export=download&id={drive_id.group(1)}"
        elif "dropbox.com" in pdf_url:
            descarga_url = re.sub(r"dl=0\b", "dl=1", pdf_url)
            if "dl=1" not in descarga_url:
                sep = "&" if "?" in descarga_url else "?"
                descarga_url = f"{descarga_url}{sep}dl=1"
        else:
            descarga_url = pdf_url

        resp = page.request.get(descarga_url)
        if resp.status != 200:
            return []
        sufijo = f"_{tipo_forzado}" if tipo_forzado else ""
        tmp_path = ROOT / "data" / "raw" / f"presupuesto_{comuna_id}_{anno}{sufijo}.pdf"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(resp.body())

        return _parsear_pdf(tmp_path, comuna_id, anno, tipo_forzado, fuente_url)

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        # upsert por período real (comuna+año+tipo+categoría+subcategoría),
        # no borrado-y-reinserción en bloque: el PDF es anual, así que años
        # ya guardados deben quedar intactos aunque esta corrida solo haya
        # encontrado el año más reciente para algunas comunas (o ninguno,
        # por una falla de red puntual).
        ahora = datetime.now().isoformat()
        for r in registros:
            self.db.execute(
                """
                INSERT INTO presupuesto_municipal
                    (comuna_id, anno, tipo, categoria, subcategoria, monto,
                     fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(comuna_id, anno, tipo, categoria, subcategoria) DO UPDATE SET
                    monto = excluded.monto,
                    fuente_url = excluded.fuente_url,
                    actualizado_en = excluded.actualizado_en
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
