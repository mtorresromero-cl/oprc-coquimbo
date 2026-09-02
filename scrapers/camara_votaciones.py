"""Votaciones de sala de los diputados de la Región de Coquimbo, vía
camara.cl — resultado oficial completo de la Cámara (155 integrantes),
no solo el voto individual de cada diputado regional.

Reescrito el 2026-09-02 para dejar de usar Playwright por completo. La
misma técnica que se documentó y probó en `gasto_parlamentario.py`
(commit `68f22d8`, 2026-08-31) aplica acá: Playwright dispara un bloqueo
por IP en camara.cl con suficiente uso — confirmado esa vez y de nuevo
hoy. La solución (confirmada contra un scraper público real que hace
esto mismo: github.com/jahadd/Analisis_congreso_Chile) es no usar
navegador en absoluto: `curl_cffi` con `impersonate="chrome"` da una
huella TLS de navegador real, y los selectores de año/paginador de
camara.cl son controles ASP.NET (`__doPostBack`) que se pueden simular
con un POST de formulario clásico (VIEWSTATE + EVENTTARGET), sin
necesidad de ejecutar JS. Mismo ritmo conservador que gasto_parlamentario.py
(SLEEP + backoff), porque el sitio también aplica rate-limiting real por
IP aparte del bloqueo por huella TLS.

Corregido el 2026-09-02 (antes de este reescrito, ver docs/06-bitacora.md):
la ficha `votaciones_sala.aspx?prmId=` no lista todo el historial en una
sola carga — filtra por año (`ddlAnnos`) y pagina el resto
(`div.paginacion`), ambos vía `__doPostBack`. La versión original solo
leía la página 1 del año por defecto, así que únicamente traía las
votaciones más recientes (en la práctica, solo agosto 2026) en vez de
todo el período desde que comenzó la legislatura el 11 de marzo de 2026.
Ahora recorre explícitamente el/los año(s) de la legislatura actual y
todas sus páginas antes de extraer los `prmIdVotacion`.

Investigado y verificado manualmente el 2026-08-25 (con Playwright, antes
del reescrito a curl_cffi — la estructura del DOM que describen estos
hallazgos no cambia por el cambio de técnica HTTP):
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
- Ver docs/05-scrapers.md y docs/06-bitacora.md para el detalle completo.
"""

import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

from base import BaseScraper
from bs4 import BeautifulSoup
from camara_mociones import DIPUTADOS_COQUIMBO

try:
    from curl_cffi import requests as cffi_requests
except ImportError:  # pragma: no cover
    print("Falta curl_cffi: pip install curl_cffi", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

BASE_URL = "https://www.camara.cl"

# la legislatura actual comenzó el 2026-03-11; se recorren todos los años
# desde entonces (no solo el actual) para no perder votaciones si algún
# año corre incompleto por una falla de red a mitad de recorrido
LEGISLATURA_INICIO_ANNO = 2026

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}

# ritmo conservador: una petición cada varios segundos, con reintentos que
# esperan cada vez más si el sitio empieza a devolver 403/429 — mismo
# criterio que gasto_parlamentario.py, que confirmó rate-limiting real
# por IP en este sitio
SLEEP_ENTRE_PETICIONES = 4.0
REINTENTOS = 4

MES_A_NUM = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05", "junio": "06",
    "julio": "07", "agosto": "08", "septiembre": "09", "octubre": "10", "noviembre": "11",
    "diciembre": "12",
}


def make_session():
    session = cffi_requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)
    return session


def _request_con_backoff(session, metodo: str, url: str, **kwargs):
    ultimo_error = None
    for intento in range(1, REINTENTOS + 1):
        try:
            resp = session.request(metodo, url, timeout=kwargs.pop("timeout", 30), **kwargs)
            if resp.status_code in (403, 429):
                raise RuntimeError(f"bloqueado (status {resp.status_code})")
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001 - re-lanzamos tras agotar reintentos
            ultimo_error = e
            if intento >= REINTENTOS:
                raise
            espera = SLEEP_ENTRE_PETICIONES * (intento + 2) * 3
            print(
                f"  {metodo} {url[-80:]} falló (intento {intento}/{REINTENTOS}): {e}; "
                f"reintentando en {espera:.0f}s",
                flush=True,
            )
            time.sleep(espera)
    raise ultimo_error  # pragma: no cover


def _estado_formulario(soup: BeautifulSoup) -> dict:
    # replica lo que un navegador real reenviaría en un postback ASP.NET:
    # los tokens VIEWSTATE más el valor actual de cada <select> — sin esto
    # el servidor puede resetear controles que no se tocan en este POST
    # (ej. el selector de año, si el postback es del paginador)
    data = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        el = soup.find("input", {"name": name})
        if el:
            data[name] = el.get("value", "")
    for select in soup.find_all("select"):
        name = select.get("name")
        if not name:
            continue
        seleccionada = select.find("option", selected=True)
        opcion = seleccionada or select.find("option")
        data[name] = opcion.get("value", "") if opcion else ""
    return data


def _postback(
    session, url: str, soup: BeautifulSoup, target: str, argument: str = ""
) -> BeautifulSoup:
    data = _estado_formulario(soup)
    data["__EVENTTARGET"] = target
    data["__EVENTARGUMENT"] = argument
    resp = _request_con_backoff(
        session, "POST", url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    time.sleep(SLEEP_ENTRE_PETICIONES)
    return BeautifulSoup(resp.text, "html.parser")


def _seleccionar_anno(session, url: str, soup: BeautifulSoup, anno: int) -> BeautifulSoup:
    # el filtro "Ver por año" (ddlAnnos) es un <select> que dispara un
    # postback ASP.NET — cambiarlo actualiza la tabla y el paginador
    select = soup.find("select", id=re.compile(r"ddlAnnos$"))
    if select is None:
        return soup
    opciones = [o.get("value") for o in select.find_all("option")]
    if str(anno) not in opciones:
        return soup
    seleccionada = select.find("option", selected=True)
    valor_actual = (
        seleccionada.get("value") if seleccionada else (opciones[-1] if opciones else None)
    )
    if valor_actual == str(anno):
        return soup
    data = _estado_formulario(soup)
    data[select.get("name")] = str(anno)
    data["__EVENTTARGET"] = select.get("name")
    data["__EVENTARGUMENT"] = ""
    resp = _request_con_backoff(
        session, "POST", url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    time.sleep(SLEEP_ENTRE_PETICIONES)
    return BeautifulSoup(resp.text, "html.parser")


def _pagina_actual(soup: BeautifulSoup) -> int:
    span = soup.select_one("div.paginacion span.actual")
    if span is None:
        return 1
    try:
        return int(span.get_text(strip=True))
    except ValueError:
        return 1


def _avanzar_pagina(session, url: str, soup: BeautifulSoup) -> BeautifulSoup | None:
    # el paginador (también un postback ASP.NET) muestra como mucho 10
    # números de página a la vez más un link "..." para cargar la
    # siguiente ventana — probar ambos hasta que no quede ninguno es lo
    # que permite recorrer el historial completo del año
    pager = soup.select_one("div.paginacion")
    if pager is None:
        return None
    actual = _pagina_actual(soup)
    siguiente_link = None
    for a in pager.find_all("a"):
        if a.get_text(strip=True) == str(actual + 1):
            siguiente_link = a
            break
    if siguiente_link is None:
        for a in pager.find_all("a"):
            if a.get_text(strip=True) == "...":
                siguiente_link = a
                break
    if siguiente_link is None:
        return None
    m = re.search(r"__doPostBack\('([^']+)','([^']*)'\)", siguiente_link.get("href", ""))
    if not m:
        return None
    target, argument = m.groups()
    return _postback(session, url, soup, target, argument)


def _recolectar_ids_de_pagina(soup: BeautifulSoup, votacion_ids: set[str]) -> None:
    tabla = soup.select_one("table.tabla")
    if tabla is None:
        return
    for a in tabla.find_all("a", href=True):
        m = re.search(r"prmIdVotacion=(\d+)", a["href"])
        if m:
            votacion_ids.add(m.group(1))


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


def _texto(soup: BeautifulSoup) -> str:
    # get_text("\n", ...) inserta un salto de línea entre bloques, igual
    # que hacía innerText() del navegador con Playwright — las mismas
    # expresiones regulares que se validaron manualmente el 2026-08-25
    # siguen aplicando sobre este texto
    return soup.get_text("\n", strip=True)


def _tally(soup: BeautifulSoup) -> tuple[int, int, int] | None:
    # tabla con las columnas "A Favor / En Contra / Abstención /
    # Dispensados" en la fila de encabezado y los conteos en la fila
    # siguiente — se lee por celda (td), no por texto plano, porque el
    # separador entre celdas no está garantizado al parsear HTML crudo
    for th in soup.find_all(["th", "td"]):
        if _normalizar(th.get_text(strip=True)) == "a favor":
            fila = th.find_parent("tr")
            fila_datos = fila.find_next_sibling("tr") if fila else None
            if fila_datos is None:
                return None
            celdas = fila_datos.find_all("td")
            if len(celdas) < 3:
                return None
            try:
                favor, contra, abstencion = (int(c.get_text(strip=True)) for c in celdas[:3])
            except ValueError:
                return None
            return favor, contra, abstencion
    return None


def _secciones(soup: BeautifulSoup) -> list[dict]:
    secciones = []
    for sec in soup.select("section.section.group"):
        h3 = sec.select_one("h3.colTitle")
        titulo = h3.get_text(strip=True) if h3 else ""
        div = h3.find_next_sibling("div") if h3 else None
        nombres = [li.get_text(strip=True) for li in div.find_all("li")] if div else []
        secciones.append({"titulo": titulo, "nombres": nombres})
    return secciones


def _parsear_detalle(soup: BeautifulSoup, url: str) -> dict | None:
    txt = _texto(soup)

    boletin_m = re.search(r"Proyecto De Ley:\n([\d]{4,6}-\d{1,2})", txt)
    fecha_m = re.search(r"Fecha:\n(.+)", txt)
    materia_m = re.search(r"Materia:\n(.+?)\nArtículo:", txt, re.DOTALL)
    sesion_m = re.search(r"Sesión:\n.*?Sesión n[°º](\d+)", txt, re.DOTALL)
    resultado_m = re.search(r"Resultado\n(Aprobado|Rechazado)", txt)
    tally = _tally(soup)

    if not (boletin_m and fecha_m and resultado_m and tally):
        return None
    fecha = _fecha_iso(fecha_m.group(1))
    if not fecha:
        return None

    votos_favor, votos_contra, abstenciones = tally

    votos_nombres: list[tuple[frozenset[str], str]] = []
    for sec in _secciones(soup):
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


class ScraperCamaraVotaciones(BaseScraper):
    """Descubre IDs de votación desde la ficha de cada diputado regional
    (todo el período de la legislatura actual) y trae el resultado
    oficial completo de cada una."""

    nombre = "camara_votaciones"
    frecuencia = "semanal"

    def _tokens_diputados_regionales(self) -> dict[str, frozenset[str]]:
        placeholders = ",".join("?" * len(DIPUTADOS_COQUIMBO))
        filas = self.db.execute(
            f"SELECT id, nombre_completo FROM autoridad WHERE id IN ({placeholders})",
            tuple(DIPUTADOS_COQUIMBO.keys()),
        ).fetchall()
        return {fila[0]: _tokens(fila[1]) for fila in filas}

    def recolectar(self) -> list[dict]:
        votacion_ids: set[str] = set()
        annos = list(range(LEGISLATURA_INICIO_ANNO, date.today().year + 1))
        session = make_session()

        for _autoridad_id, dip_id in DIPUTADOS_COQUIMBO.items():
            for anno in annos:
                url = f"{BASE_URL}/diputados/detalle/votaciones_sala.aspx?prmId={dip_id}"
                try:
                    resp = _request_con_backoff(session, "GET", url)
                    time.sleep(SLEEP_ENTRE_PETICIONES)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    soup = _seleccionar_anno(session, url, soup, anno)
                except Exception as e:
                    print(
                        f"  diputado {dip_id}, año {anno}: ERROR cargando página: {e}",
                        flush=True,
                    )
                    self.stats["errores"] += 1
                    continue

                _recolectar_ids_de_pagina(soup, votacion_ids)
                paginas = 1
                while True:
                    siguiente = _avanzar_pagina(session, url, soup)
                    if siguiente is None:
                        break
                    soup = siguiente
                    _recolectar_ids_de_pagina(soup, votacion_ids)
                    paginas += 1
                print(
                    f"  diputado {dip_id}, año {anno}: {paginas} página(s), "
                    f"{len(votacion_ids)} votaciones acumuladas",
                    flush=True,
                )

        registros = []
        for vid in sorted(votacion_ids):
            url = f"{BASE_URL}/legislacion/sala_sesiones/votacion_detalle.aspx?prmIdVotacion={vid}"
            try:
                resp = _request_con_backoff(session, "GET", url)
                time.sleep(SLEEP_ENTRE_PETICIONES)
            except Exception as e:
                print(f"  votación {vid}: ERROR cargando página: {e}", flush=True)
                self.stats["errores"] += 1
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            # además de proyectos de ley, camara.cl vota resoluciones,
            # proyectos de acuerdo y otros tipos sin boletín — no encajan
            # en nuestro modelo (proyecto_ley/voto asume un boletín) y se
            # omiten sin contar como error: es un tipo de votación que
            # deliberadamente no intentamos modelar, no una falla de
            # scraping.
            tipo_m = re.search(r"Tipo de Votación\n(.+)", _texto(soup))
            if not tipo_m or tipo_m.group(1).strip() != "Proyecto De Ley":
                continue

            registro = _parsear_detalle(soup, url)
            if registro:
                registros.append(registro)
            else:
                self.stats["errores"] += 1
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
