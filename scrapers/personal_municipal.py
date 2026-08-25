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
                # página nueva por comuna: reusar una sola página para las 15
                # comunas x 6 combinaciones resultó menos confiable (más
                # timeouts/filas vacías) que abrir una fresca cada vez.
                page = browser.new_page(user_agent=USER_AGENT)
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
                page.close()
                time.sleep(1)  # rate limiting entre comunas
            browser.close()
        return resultado

    def _extraer_categoria(self, page, url_base, categoria_re, area_re):
        page.goto(url_base, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.locator("a", has_text=categoria_re).first.click()
        page.wait_for_timeout(2200)

        # algunas comunas no separan por área (van directo a los años, como
        # La Serena en presupuesto) — solo se clickea el área si existe.
        area_link = page.locator("a", has_text=area_re)
        if area_link.count():
            area_link.first.click()
            page.wait_for_timeout(2200)

        annos = page.locator("a", has_text=re.compile(r"^(Año )?\d{4}$")).all()
        if not annos:
            return []
        annos[0].click()
        page.wait_for_timeout(2200)

        meses_regex = re.compile(
            r"^(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto"
            r"|Septiembre|Octubre|Noviembre|Diciembre)$"
        )
        meses = page.locator("a", has_text=meses_regex).all()
        if not meses:
            return []
        meses[0].click()
        page.wait_for_timeout(2500)

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
        comunas = tuple(MUNICIPIOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(comunas))
        ahora = datetime.now().isoformat()

        self.db.execute(
            f"DELETE FROM personal_municipal WHERE comuna_id IN ({placeholders})", comunas
        )
        for a in datos["agregados"]:
            self.db.execute(
                """
                INSERT INTO personal_municipal
                    (comuna_id, anno, mes, area, tipo_contrato, dotacion,
                     remuneracion_total, fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    a["comuna_id"], a["anno"], a["mes"], a["area"], a["tipo_contrato"],
                    a["dotacion"], a["remuneracion_total"], a["fuente_url"], ahora,
                ),
            )
            self.stats["nuevos"] += 1

        self.db.execute(
            f"DELETE FROM remuneracion_autoridad WHERE comuna_id IN ({placeholders})", comunas
        )
        for r in datos["autoridad"]:
            self.db.execute(
                """
                INSERT INTO remuneracion_autoridad
                    (comuna_id, anno, mes, cargo, remuneracion_bruta, fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
