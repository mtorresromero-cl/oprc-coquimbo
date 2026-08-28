"""Dotación y remuneraciones de personal municipal, vía portaltransparencia.cl
(portal central, no el subdominio propio del municipio — ese último resultó
estar desactualizado 3+ años en La Serena, ver docs/05-scrapers.md).

No replica el detalle persona por persona (ya es público ahí mismo, y son
cientos de filas por comuna): guarda **totales agregados** por
comuna/año/mes/área (Municipal, Salud)/tipo de contrato (planta, contrata,
honorarios) — pensado para comparar y graficar entre las 15 comunas más
adelante. La única excepción con nombre individual es el alcalde/alcaldesa
(autoridad electa, ya está en el catálogo) — decisión explícita del usuario
de no exponer sueldo individual del resto del personal.

Requiere Playwright: el listado carga vía AJAX (JSF/PrimeFaces, Liferay
portlet), no hay URL GET directa por mes. La paginación (ui-paginator-page)
es el mismo mecanismo AJAX que la navegación por acordeón — no es un POST
de formulario tipo camara.cl, no hay indicios de bloqueo por esto.
"""

import json
import re
import sqlite3
import time
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

# las etiquetas de categoría las escribe cada municipio a mano en el portal
# (mismo problema que en transparencia_municipal.py: typos/mayúsculas
# distintas) — se matchea tolerando eso.
CATEGORIAS = {
    "planta": re.compile(r"Personal de Planta", re.IGNORECASE),
    "contrata": re.compile(r"Personal a Contrata", re.IGNORECASE),
    "honorarios": re.compile(r"Personas naturales contratadas a honorarios", re.IGNORECASE),
}
AREAS_RE = re.compile(r"^Municipal(idad)?$", re.IGNORECASE)
SALUD_RE = re.compile(r"^Salud$", re.IGNORECASE)
AREAS = [("municipal", AREAS_RE), ("salud", SALUD_RE)]

MES_NUM = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}


def _monto_a_numero(texto: str) -> float:
    texto = re.sub(r"[^\d]", "", texto or "")
    return float(texto) if texto else 0.0


class ScraperPersonalMunicipal(BaseScraper):
    """Recolecta totales de dotación/remuneraciones por comuna, área y tipo
    de contrato (mes más reciente disponible), más el sueldo individual del
    alcalde/alcaldesa cuando aparece en el listado de planta."""

    nombre = "personal_municipal"
    frecuencia = "semanal"

    def recolectar(self) -> dict:
        resultado = {"agregados": [], "autoridad": []}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for comuna_id, org_code in MUNICIPIOS_COQUIMBO.items():
                # contexto (no solo página) nuevo por comuna: reusar el
                # mismo browser.new_page() deja todas las comunas
                # compartiendo cookies/sesión del contexto por defecto. Se
                # observó que dentro de una misma corrida La Serena/Coquimbo
                # y el grupo {andacollo, la-higuera, paihuano, ovalle,
                # rio-hurtado} fallan de forma excluyente entre sí (uno u
                # otro grupo, nunca ambos) — compatible con el portal
                # repartiendo la sesión a distintos backends con datos
                # desincronizados y la sesión pegándose al primero que
                # respondió. Un contexto (y por lo tanto sesión) nuevo por
                # comuna evita ese arrastre entre comunas de una misma
                # corrida.
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                url = f"https://www.portaltransparencia.cl/PortalPdT/directorio-de-organismos-regulados/?org={org_code}"

                for tipo_contrato, categoria_re in CATEGORIAS.items():
                    for area_nombre, area_re in AREAS:
                        try:
                            filas = self._extraer_categoria(page, url, categoria_re, area_re)
                        except Exception as e:
                            print(f"[{comuna_id}] {tipo_contrato}/{area_nombre} ERROR: {e}")
                            self.stats["errores"] += 1
                            continue
                        print(f"[{comuna_id}] {tipo_contrato}/{area_nombre}: {len(filas)} filas")
                        if not filas:
                            continue

                        anno = filas[0]["anno"]
                        mes = filas[0]["mes"]
                        resultado["agregados"].append(
                            {
                                "comuna_id": comuna_id,
                                "anno": anno,
                                "mes": mes,
                                "area": area_nombre,
                                "tipo_contrato": tipo_contrato,
                                "dotacion": len(filas),
                                "remuneracion_total": sum(f["remuneracion_bruta"] for f in filas),
                                "fuente_url": url,
                            }
                        )

                        if tipo_contrato == "planta" and area_nombre == "municipal":
                            for f in filas:
                                if "ALCALDE" in f["cargo"].upper():
                                    resultado["autoridad"].append(
                                        {
                                            "comuna_id": comuna_id,
                                            "anno": anno,
                                            "mes": mes,
                                            "cargo": f["cargo"],
                                            "remuneracion_bruta": f["remuneracion_bruta"],
                                            "fuente_url": url,
                                        }
                                    )
                        time.sleep(1)  # rate limiting entre categoría/área
                context.close()
                time.sleep(1)  # rate limiting entre comunas
            browser.close()
        return resultado

    def _extraer_categoria(self, page, url_base, categoria_re, area_re):
        # timeouts más generosos que en transparencia_municipal.py: La
        # Serena/Coquimbo (miles de filas de personal) tardan bastante más
        # en resolver el AJAX de PrimeFaces que el resto de las comunas, y
        # con los timeouts originales (30s goto, ~2.2s por paso) fallaban de
        # forma intermitente incluso reintentando varias veces.
        page.goto(url_base, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.locator("a", has_text=categoria_re).first.click()
        page.wait_for_timeout(3500)

        # algunas comunas no separan por área (van directo a los años, como
        # La Serena en presupuesto) — solo se clickea el área si existe.
        area_link = page.locator("a", has_text=area_re)
        if area_link.count():
            area_link.first.click()
            page.wait_for_timeout(3500)

        # el año puede venir solo ("2026"), con prefijo ("Año 2026") o con el
        # área pegada (Ovalle: "MUNICIPAL 2026") — se matchea por el final.
        annos = page.locator("a", has_text=re.compile(r"(19|20)\d{2}$")).all()

        # algunas comunas (ej. Monte Patria en honorarios) repiten el link de
        # la categoría una vez más tras elegir el área — sin ese segundo
        # click no aparecen los años. Se detecta por ausencia de años y se
        # reintenta clickeando el link de categoría otra vez. Se usa .last
        # porque categoria_re también matchea el breadcrumb superior ("04.
        # Personal y remuneraciones: <categoría>"), que contiene el mismo
        # texto como substring — el link que realmente hay que clickear es
        # el más profundo (el último en aparecer en el DOM).
        if not annos:
            repetido = page.locator("a", has_text=categoria_re)
            if repetido.count():
                repetido.last.click()
                page.wait_for_timeout(3500)
                annos = page.locator("a", has_text=re.compile(r"(19|20)\d{2}$")).all()

        if not annos:
            return []
        annos[0].click()
        page.wait_for_timeout(3500)

        # el mes puede venir solo ("Julio") o con más texto alrededor
        # (Ovalle: "Sueldos Municipal - Julio 2026") — se matchea por
        # palabra completa, no por texto exacto del link.
        meses_regex = re.compile(
            r"\b(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto"
            r"|Septiembre|Octubre|Noviembre|Diciembre)\b",
            re.IGNORECASE,
        )

        def _filtrar_meses(locator):
            # La Serena antepone un enlace "Histórico (Enero 2009 a Marzo
            # 2023)" que matchea meses_regex por contener "Enero" como
            # palabra completa, pero no es un mes real — lleva a un
            # listado con otra estructura y hace que la extracción
            # devuelva 0 filas en silencio. Se descarta explícitamente.
            return [m for m in locator.all() if "histórico" not in (m.inner_text() or "").lower()]

        meses = _filtrar_meses(page.locator("a", has_text=meses_regex))

        # algunas comunas (ej. La Higuera) piden el área DESPUÉS del año, no
        # antes — si no aparecieron meses todavía, se prueba el área acá.
        if not meses:
            area_link = page.locator("a", has_text=area_re)
            if area_link.count():
                area_link.first.click()
                page.wait_for_timeout(3500)
                meses = _filtrar_meses(page.locator("a", has_text=meses_regex))

        if not meses:
            return []
        # no asumir que el DOM lista los meses de más reciente a más
        # antiguo: la mayoría de las comunas sí (Julio primero), pero
        # Andacollo, La Higuera y Río Hurtado los listan al revés (Enero
        # primero) — meses[0] agarraba el mes equivocado en esas tres.
        # Se elige por el número real del mes, no por posición.
        def _numero_mes(m):
            match = meses_regex.search(m.inner_text() or "")
            return MES_NUM.get(match.group(1).lower(), 0) if match else 0

        mes_mas_reciente = max(meses, key=_numero_mes)
        mes_mas_reciente.click()
        page.wait_for_timeout(3500)

        return self._extraer_todas_las_paginas(page)

    def _extraer_todas_las_paginas(self, page) -> list[dict]:
        columnas = self._mapear_columnas(page)
        if columnas is None:
            return []

        filas_totales: list[dict] = []
        pagina_actual = 1
        while True:
            filas_totales.extend(self._extraer_filas_pagina_actual(page, columnas))

            botones = page.locator("a.ui-paginator-page").all()
            siguiente = None
            for b in botones:
                if (b.text_content() or "").strip() == str(pagina_actual + 1):
                    siguiente = b
                    break
            if siguiente is None:
                break
            siguiente.click()
            page.wait_for_timeout(2000)
            pagina_actual += 1
            time.sleep(1)  # rate limiting entre páginas
        return filas_totales

    def _mapear_columnas(self, page) -> dict[str, int] | None:
        """Cada tipo de contrato (planta/contrata/honorarios) trae un orden de
        columnas distinto — se detecta por texto de cabecera en vez de asumir
        un índice fijo."""
        headers = page.locator("table.table-responsive-lg thead th").all()
        indices = {"nombre": None, "cargo": None, "monto": None}
        for i, h in enumerate(headers):
            texto = h.inner_text().strip()
            if texto == "Nombre completo":
                indices["nombre"] = i
            elif texto in ("Cargo o función", "Descripción de la función"):
                indices["cargo"] = i
            elif "Remuneración bruta" in texto or "Honorario Total Bruto" in texto:
                indices["monto"] = i
        if any(v is None for v in indices.values()):
            return None
        return indices

    def _extraer_filas_pagina_actual(self, page, columnas: dict[str, int]) -> list[dict]:
        filas = []
        for tr in page.locator("table.table-responsive-lg tbody tr").all():
            celdas = tr.locator("td").all()
            if len(celdas) <= max(columnas.values()):
                continue
            anno_txt = celdas[0].inner_text().strip()
            mes_txt = celdas[1].inner_text().strip().lower()
            if not anno_txt.isdigit() or mes_txt not in MES_NUM:
                continue
            filas.append(
                {
                    "anno": int(anno_txt),
                    "mes": MES_NUM[mes_txt],
                    "nombre": celdas[columnas["nombre"]].inner_text().strip(),
                    "cargo": celdas[columnas["cargo"]].inner_text().strip(),
                    "remuneracion_bruta": _monto_a_numero(celdas[columnas["monto"]].inner_text()),
                }
            )
        return filas

    def procesar(self, datos: dict) -> dict:
        return datos

    def guardar(self, datos: dict) -> None:
        # upsert por período real (comuna+año+mes+área+tipo_contrato), no
        # borrado-y-reinserción: el portal solo expone "el mes más
        # reciente disponible", así que cada semana que ese mes cambia se
        # agrega un período nuevo sin pisar los meses ya guardados — antes
        # borrar por comuna destruía la historia de meses anteriores en
        # cada corrida.
        ahora = datetime.now().isoformat()

        for a in datos["agregados"]:
            self.db.execute(
                """
                INSERT INTO personal_municipal
                    (comuna_id, anno, mes, area, tipo_contrato, dotacion,
                     remuneracion_total, fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(comuna_id, anno, mes, area, tipo_contrato) DO UPDATE SET
                    dotacion = excluded.dotacion,
                    remuneracion_total = excluded.remuneracion_total,
                    fuente_url = excluded.fuente_url,
                    actualizado_en = excluded.actualizado_en
                """,
                (
                    a["comuna_id"], a["anno"], a["mes"], a["area"], a["tipo_contrato"],
                    a["dotacion"], a["remuneracion_total"], a["fuente_url"], ahora,
                ),
            )
            self.stats["nuevos"] += 1

        for r in datos["autoridad"]:
            self.db.execute(
                """
                INSERT INTO remuneracion_autoridad
                    (comuna_id, anno, mes, cargo, remuneracion_bruta, fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(comuna_id, anno, mes, cargo) DO UPDATE SET
                    remuneracion_bruta = excluded.remuneracion_bruta,
                    fuente_url = excluded.fuente_url,
                    actualizado_en = excluded.actualizado_en
                """,
                (
                    r["comuna_id"], r["anno"], r["mes"], r["cargo"],
                    r["remuneracion_bruta"], r["fuente_url"], ahora,
                ),
            )
            self.stats["nuevos"] += 1

        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        comunas = tuple(MUNICIPIOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(comunas))

        agregados = self.db.execute(
            f"""
            SELECT comuna_id, anno, mes, area, tipo_contrato, dotacion,
                   remuneracion_total, fuente_url
            FROM personal_municipal WHERE comuna_id IN ({placeholders})
            ORDER BY comuna_id, anno DESC, mes DESC, area, tipo_contrato
            """,
            comunas,
        ).fetchall()
        (PROCESSED_DIR / "personal-municipal.json").write_text(
            json.dumps([dict(f) for f in agregados], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        autoridad = self.db.execute(
            f"""
            SELECT comuna_id, anno, mes, cargo, remuneracion_bruta, fuente_url
            FROM remuneracion_autoridad WHERE comuna_id IN ({placeholders})
            ORDER BY comuna_id, anno DESC, mes DESC
            """,
            comunas,
        ).fetchall()
        (PROCESSED_DIR / "remuneracion-autoridad.json").write_text(
            json.dumps([dict(f) for f in autoridad], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(
            f"Exportados {len(agregados)} agregados de personal y "
            f"{len(autoridad)} remuneraciones de autoridad a {PROCESSED_DIR}"
        )


if __name__ == "__main__":
    scraper = ScraperPersonalMunicipal()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
