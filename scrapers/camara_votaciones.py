"""Votaciones de sala de los diputados de la Región de Coquimbo, vía
camara.cl — resultado oficial completo de la Cámara (155 integrantes),
no solo el voto individual de cada diputado regional.

Corregido el 2026-09-02: la ficha `votaciones_sala.aspx?prmId=` no lista
todo el historial en una sola carga — filtra por año (`ddlAnnos`, un
`<select>` que dispara `__doPostBack`, año actual seleccionado por
defecto) y pagina el resto (`div.paginacion`, también por
`__doPostBack`). La versión anterior solo leía la página 1 del año por
defecto sin recorrer esas páginas, así que únicamente traía las
votaciones más recientes (en la práctica, solo agosto 2026) en vez de
todo el período desde que comenzó la legislatura el 11 de marzo de
2026. Ahora recorre explícitamente el/los año(s) de la legislatura
actual y todas sus páginas antes de extraer los `prmIdVotacion`.

Investigado y verificado manualmente el 2026-08-25:
- La ficha personal de cada diputado (`votaciones_sala.aspx?prmId=`) solo
  trae su voto propio, sin el resultado de la sesión — insuficiente para
  calcular participación/alineamiento como se hace con Senado/CORE (que sí
  tienen el resultado agregado real). Cada fila de esa ficha tiene un link
  "ver" hacia `/legislacion/sala_sesiones/votacion_detalle.aspx?prmIdVotacion=`,
  que SÍ trae el resultado oficial completo: conteo de A Favor/En
  Contra/Abstención/Dispensados/Pareos y el listado nominal completo de la
  Cámara por categoría — de ahí se puede extraer el voto real de cada uno
  de los 7 diputados regionales por nombre.
- Ese descubrimiento reemplaza el diseño anterior (tabla `voto_diputado`,
  historial personal sin resultado agregado): ahora se guarda igual que
  Senado/CORE, en `votacion_sesion`/`voto`, habilitando el mismo índice de
  participación/alineamiento para diputados.
- Confirmado con pruebas directas que reutilizar la misma sesión de
  navegador entre distintas páginas `votacion_detalle.aspx` (para IDs de
  votación distintos) SÍ dispara el mismo bloqueo de Cloudflare que
  combinar mociones/votaciones/asistencia de un mismo diputado — y que
  abrir un contexto de navegador nuevo por cada ID de votación (igual
  patrón que en el resto de este scraper y en camara_mociones.py) lo
  evita por completo. Confirmado con 5 IDs consecutivos sin bloqueo.
- Ver docs/05-scrapers.md para el detalle completo de esta investigación.
"""

import json
import re
import sqlite3
import time
import unicodedata
from datetime import date
from pathlib import Path

from base import BaseScraper
from camara_mociones import DIPUTADOS_COQUIMBO
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

# la legislatura actual comenzó el 2026-03-11; se recorren todos los años
# desde entonces (no solo el actual) para no perder votaciones si algún
# año corre incompleto por una falla de red a mitad de recorrido
LEGISLATURA_INICIO_ANNO = 2026

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MES_A_NUM = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05", "junio": "06",
    "julio": "07", "agosto": "08", "septiembre": "09", "octubre": "10", "noviembre": "11",
    "diciembre": "12",
}

SECCIONES_JS = """
el => {
    const secs = Array.from(el.querySelectorAll('section.section.group'));
    return secs.map(s => {
        const h3 = s.querySelector('h3.colTitle');
        const div = h3 ? h3.nextElementSibling : null;
        const lis = div ? Array.from(div.querySelectorAll('li')) : [];
        const titulo = h3 ? h3.textContent.trim() : '';
        return { titulo, nombres: lis.map(li => li.textContent.trim()) };
    });
}
"""


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _tokens(texto: str) -> frozenset[str]:
    return frozenset(_normalizar(texto).replace(",", "").split())


def _es_la_misma_persona(tokens_a: frozenset[str], tokens_b: frozenset[str]) -> bool:
    # nombre/apellido en nuestra BD a veces separa mal nombres compuestos
    # (ej. "Bernardo" / "Antonio Salinas Maya" en vez de "Bernardo Antonio"
    # / "Salinas Maya") — comparar por el set de tokens de nombre_completo
    # contra el set de camara.cl evita depender de ese split. Coinciden si
    # el conjunto más chico es subconjunto del más grande (permite que uno
    # de los dos omita un segundo nombre) y comparten al menos 2 tokens.
    menor, mayor = sorted([tokens_a, tokens_b], key=len)
    return len(menor) >= 2 and menor.issubset(mayor)


def _fecha_iso(texto: str) -> str | None:
    m = re.search(r"(\d{1,2}) ([a-záéíóúñ]+) (\d{4})", texto.lower())
    if not m:
        return None
    dia, mes_nombre, anno = m.groups()
    mes = MES_A_NUM.get(_normalizar(mes_nombre))
    if not mes:
        return None
    return f"{anno}-{mes}-{int(dia):02d}"


def _etiqueta_seccion(titulo: str) -> str:
    if titulo == "A Favor":
        return "favor"
    if titulo == "En Contra":
        return "contra"
    if titulo.startswith("Abstenci"):
        return "abstencion"
    if titulo == "Pareos":
        return "pareo"
    return "dispensado"  # el título real es el artículo legal que lo justifica


class ScraperCamaraVotaciones(BaseScraper):
    """Descubre IDs de votación recientes desde la ficha de cada diputado
    regional y trae el resultado oficial completo de cada una."""

    nombre = "camara_votaciones"
    frecuencia = "semanal"

    def _tokens_diputados_regionales(self) -> dict[str, frozenset[str]]:
        placeholders = ",".join("?" * len(DIPUTADOS_COQUIMBO))
        filas = self.db.execute(
            f"SELECT id, nombre_completo FROM autoridad WHERE id IN ({placeholders})",
            tuple(DIPUTADOS_COQUIMBO.keys()),
        ).fetchall()
        return {fila[0]: _tokens(fila[1]) for fila in filas}

    def _parsear_detalle(self, page, url: str) -> dict | None:
        txt = page.locator("body").inner_text()

        boletin_m = re.search(r"Proyecto De Ley:\n([\d]{4,6}-\d{1,2})", txt)
        fecha_m = re.search(r"Fecha:\n(.+)", txt)
        materia_m = re.search(r"Materia:\n(.+?)\nArtículo:", txt, re.DOTALL)
        sesion_m = re.search(r"Sesión:\n.*?Sesión n[°º](\d+)", txt, re.DOTALL)
        resultado_m = re.search(r"Resultado\n(Aprobado|Rechazado)", txt)
        tally_m = re.search(
            r"A Favor\tEn Contra\tAbstenci[oó]n\tDispensados\n(\d+)\t(\d+)\t(\d+)\t(\d+)", txt
        )
        if not (boletin_m and fecha_m and resultado_m and tally_m):
            return None
        fecha = _fecha_iso(fecha_m.group(1))
        if not fecha:
            return None

        votos_favor, votos_contra, abstenciones, _dispensados = (int(x) for x in tally_m.groups())

        secciones = page.locator("body").evaluate(SECCIONES_JS)
        votos_nombres: list[tuple[frozenset[str], str]] = []
        for sec in secciones:
            etiqueta = _etiqueta_seccion(sec["titulo"])
            for nombre_bruto in sec["nombres"]:
                if etiqueta == "pareo":
                    for parte in re.split(r"\s+con\s+", _normalizar(nombre_bruto)):
                        votos_nombres.append((_tokens(parte), etiqueta))
                else:
                    votos_nombres.append((_tokens(nombre_bruto), etiqueta))

        id_votacion = re.search(r"prmIdVotacion=(\d+)", url).group(1)
        return {
            "id": f"camara-{id_votacion}",
            "boletin": boletin_m.group(1),
            "titulo": materia_m.group(1).strip() if materia_m else "",
            "fecha": fecha,
            "numero_sesion": sesion_m.group(1) if sesion_m else None,
            "resultado": resultado_m.group(1).lower(),
            "votos_favor": votos_favor,
            "votos_contra": votos_contra,
            "abstenciones": abstenciones,
            "fuente_url": url,
            "votos_nombres": votos_nombres,
        }

    def _seleccionar_anno(self, page, anno: int) -> None:
        # el filtro "Ver por año" (ddlAnnos) es un <select> que dispara un
        # postback AJAX (UpdatePanel, no navegación real) — cambiarlo
        # actualiza la tabla y el paginador en el mismo DOM
        select = page.locator("select[id$='ddlAnnos']")
        if select.count() == 0:
            return
        opciones = select.locator("option").evaluate_all("els => els.map(e => e.value)")
        if str(anno) not in opciones or select.input_value() == str(anno):
            return
        select.select_option(str(anno))
        page.wait_for_timeout(1500)

    def _recolectar_ids_de_pagina(self, page, votacion_ids: set[str]) -> None:
        hrefs = page.locator("table.tabla a").evaluate_all(
            "els => els.map(e => e.getAttribute('href'))"
        )
        for href in hrefs:
            if href and "prmIdVotacion" in href:
                m = re.search(r"prmIdVotacion=(\d+)", href)
                if m:
                    votacion_ids.add(m.group(1))

    def _pagina_actual(self, page) -> int:
        span = page.locator("div.paginacion span.actual")
        if span.count() == 0:
            return 1
        return int(span.first.inner_text().strip())

    def _avanzar_pagina(self, page) -> bool:
        # el paginador (también un postback AJAX vía UpdatePanel) muestra
        # como mucho 10 números de página a la vez más un link "..." para
        # cargar la siguiente ventana — probar ambos hasta que no quede
        # ninguno es lo que permite recorrer el historial completo del año
        actual = self._pagina_actual(page)
        siguiente = page.locator("div.paginacion a", has_text=re.compile(rf"^{actual + 1}$"))
        if siguiente.count() == 0:
            siguiente = page.locator("div.paginacion a", has_text="...")
        if siguiente.count() == 0:
            return False
        siguiente.first.click()
        page.wait_for_timeout(1500)
        return True

    def recolectar(self) -> list[dict]:
        votacion_ids: set[str] = set()
        annos = list(range(LEGISLATURA_INICIO_ANNO, date.today().year + 1))
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for _autoridad_id, dip_id in DIPUTADOS_COQUIMBO.items():
                for anno in annos:
                    context = browser.new_context(user_agent=USER_AGENT)
                    page = context.new_page()
                    url = f"https://camara.cl/diputados/detalle/votaciones_sala.aspx?prmId={dip_id}"
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)
                    self._seleccionar_anno(page, anno)
                    self._recolectar_ids_de_pagina(page, votacion_ids)
                    paginas = 1
                    while self._avanzar_pagina(page):
                        self._recolectar_ids_de_pagina(page, votacion_ids)
                        paginas += 1
                    print(
                        f"  diputado {dip_id}, año {anno}: {paginas} página(s), "
                        f"{len(votacion_ids)} votaciones acumuladas",
                        flush=True,
                    )
                    context.close()
                    time.sleep(5)

            registros = []
            for vid in sorted(votacion_ids):
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                url = f"https://camara.cl/legislacion/sala_sesiones/votacion_detalle.aspx?prmIdVotacion={vid}"
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)

                # además de proyectos de ley, camara.cl vota resoluciones,
                # proyectos de acuerdo y otros tipos sin boletín — no
                # encajan en nuestro modelo (proyecto_ley/voto asume un
                # boletín) y se omiten sin contar como error: es un tipo de
                # votación que deliberadamente no intentamos modelar, no
                # una falla de scraping.
                tipo_m = re.search(r"Tipo de Votación\n(.+)", page.locator("body").inner_text())
                if not tipo_m or tipo_m.group(1).strip() != "Proyecto De Ley":
                    context.close()
                    time.sleep(5)
                    continue

                registro = self._parsear_detalle(page, url)
                if registro:
                    registros.append(registro)
                else:
                    self.stats["errores"] += 1
                context.close()
                time.sleep(5)

            browser.close()
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        tokens_diputados = self._tokens_diputados_regionales()
        for r in registros:
            votos: dict[str, str] = {}
            for autoridad_id, tokens_autoridad in tokens_diputados.items():
                for tokens_nombre, etiqueta in r["votos_nombres"]:
                    if _es_la_misma_persona(tokens_autoridad, tokens_nombre):
                        votos[autoridad_id] = etiqueta
                        break
            r["votos"] = votos
        return registros

    def guardar(self, registros: list[dict]) -> None:
        for r in registros:
            self.db.execute(
                """
                INSERT INTO proyecto_ley (id, titulo, fecha_ingreso, camara_origen, url_bcn)
                VALUES (?, ?, ?, 'camara', ?)
                ON CONFLICT(id) DO UPDATE SET
                    titulo = CASE
                        WHEN excluded.titulo != '' THEN excluded.titulo
                        ELSE proyecto_ley.titulo
                    END
                """,
                (
                    r["boletin"], r["titulo"] or f"Boletín N° {r['boletin']}",
                    r["fecha"], r["fuente_url"],
                ),
            )
            self.db.execute(
                """
                INSERT INTO votacion_sesion
                    (id, camara, fecha, numero_sesion, proyecto_ley_id, descripcion, resultado,
                     votos_favor, votos_contra, abstenciones, fuente_url)
                VALUES (?, 'camara', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    resultado = excluded.resultado,
                    votos_favor = excluded.votos_favor,
                    votos_contra = excluded.votos_contra,
                    abstenciones = excluded.abstenciones,
                    fuente_url = excluded.fuente_url
                """,
                (
                    r["id"], r["fecha"], r["numero_sesion"], r["boletin"], r["titulo"],
                    r["resultado"], r["votos_favor"], r["votos_contra"],
                    r["abstenciones"], r["fuente_url"],
                ),
            )
            for autoridad_id, voto in r["votos"].items():
                self.db.execute(
                    """
                    INSERT INTO voto (autoridad_id, sesion_id, voto, fecha)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(autoridad_id, sesion_id) DO UPDATE SET voto = excluded.voto
                    """,
                    (autoridad_id, r["id"], voto, r["fecha"]),
                )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        sesiones = self.db.execute(
            "SELECT * FROM votacion_sesion WHERE camara = 'camara' ORDER BY fecha DESC"
        ).fetchall()

        salida = []
        for s in sesiones:
            votos = self.db.execute(
                "SELECT autoridad_id, voto FROM voto WHERE sesion_id = ?", (s["id"],)
            ).fetchall()
            salida.append({**dict(s), "votos": [dict(v) for v in votos]})

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "votaciones-camara.json").write_text(
            json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Exportadas {len(salida)} votaciones de la Cámara a {PROCESSED_DIR}")


if __name__ == "__main__":
    scraper = ScraperCamaraVotaciones()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
