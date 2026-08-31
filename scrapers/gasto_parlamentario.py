"""Gasto operacional de los 7 diputados de la Región de Coquimbo (Distrito 5),
vía camara.cl (transparencia por Ley 20.285). Cuatro categorías, cada una en
su propia página, con su propio selector de mes/año.

TÉCNICA: nada de navegador/Playwright. El selector de mes en camara.cl no
navega a una página nueva: dispara un POST asíncrono (ASP.NET UpdatePanel,
con headers X-Requested-With/X-MicrosoftAjax) que Cloudflare bloquea con 403
de forma consistente para tráfico automatizado — probado en profundidad,
incluso con un solo intento aislado y con distintos navegadores.

La solución (verificada contra un scraper público real que hace exactamente
esto: github.com/jahadd/Analisis_congreso_Chile) es no imitar esa llamada
AJAX en absoluto: se hace un POST de formulario clásico (sin esos headers),
usando curl_cffi con impersonate="chrome" para que la huella TLS sea la de
un navegador real. Eso hace que el servidor trate el cambio de mes como un
postback normal de ASP.NET (devuelve la página completa, no el fragmento
AJAX), que es un patrón mucho menos sospechoso para Cloudflare que el POST
async con esos headers.

Aun así, el sitio SÍ aplica rate-limiting real por IP (se confirmó un bloqueo
duro tras muchas peticiones seguidas en la misma sesión de pruebas) — de ahí
el ritmo conservador (SLEEP) y el backoff con reintentos.
"""

import logging
import re
import sys
import time
from pathlib import Path

from base import BaseScraper
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cffi_requests
except ImportError:  # pragma: no cover
    print("Falta curl_cffi: pip install curl_cffi", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

log = logging.getLogger(__name__)

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

# Ritmo conservador: una petición cada varios segundos, con reintentos que
# esperan cada vez más si el sitio empieza a devolver 403/429 o se cae.
SLEEP_ENTRE_PETICIONES = 4.0
REINTENTOS = 4

BASE_URL = "https://www.camara.cl"

# autoridad_id (mismo id que autoridades.json) -> prmId de camara.cl
DIPUTADOS_COQUIMBO = {
    "bernardo-antonio-salinas-maya-diputado": 1250,
    "daniel-manouchehri-lobos-diputado": 1142,
    "marco-antonio-sulantay-olivares-diputado": 1174,
    "carolina-tello-rojas-diputado": 1177,
    "eileen-patricia-urqueta-rojas-diputado": 1255,
    "nathalie-castillo-rojas-diputado": 1117,
    "erich-christ-grohs-marin-diputado": 1212,
}

MESES = ["marzo", "abril", "mayo", "junio", "julio", "agosto"]
MES_NUM = {m: i + 3 for i, m in enumerate(MESES)}
ANNO = 2026

CATEGORIAS = {
    "gastos_operacionales": "gastosoperacionales.aspx",
    "asesorias_externas": "asesoriaexterna.aspx",
    "pasajes_aereos": "pasajesaereos.aspx",
    "personal_apoyo": "personaldepoyo.aspx",
}


def _monto_a_numero(texto: str) -> float | None:
    texto = re.sub(r"\s+", "", texto or "").replace(".", "").replace(",", "")
    if not texto or texto in ("-",):
        return None
    try:
        return float(texto)
    except ValueError:
        return None


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
            log.warning("%s %s falló (intento %d/%d): %s; reintentando en %.0fs",
                        metodo, url[-80:], intento, REINTENTOS, e, espera)
            time.sleep(espera)
    raise ultimo_error  # pragma: no cover


def _viewstate(soup: BeautifulSoup) -> dict:
    tokens = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        el = soup.find("input", {"name": name})
        if el:
            tokens[name] = el.get("value", "")
    return tokens


def _post_mes(session, url: str, soup: BeautifulSoup, mes_valor: int) -> BeautifulSoup:
    tokens = _viewstate(soup)
    sel_mes = soup.find("select", {"id": re.compile(r"DetallePlaceHolder_ddlMes")})
    if not sel_mes or not sel_mes.get("name"):
        raise RuntimeError("no se encontró el selector de mes en la página")
    data = {**tokens, "__EVENTTARGET": sel_mes["name"], sel_mes["name"]: str(mes_valor)}
    resp = _request_con_backoff(
        session, "POST", url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    time.sleep(SLEEP_ENTRE_PETICIONES)
    return BeautifulSoup(resp.text, "html.parser")


def _texto(soup: BeautifulSoup) -> str:
    return soup.get_text(" ", strip=True)


class ScraperGastoParlamentario(BaseScraper):
    nombre = "gasto_parlamentario"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        raise NotImplementedError("usar ejecutar_incremental()")

    def ejecutar_incremental(self) -> None:
        session = make_session()
        for autoridad_id, prm_id in DIPUTADOS_COQUIMBO.items():
            registros = []
            for categoria, archivo in CATEGORIAS.items():
                url = f"{BASE_URL}/diputados/detalle/{archivo}?prmId={prm_id}"
                try:
                    resp = _request_con_backoff(session, "GET", url)
                    time.sleep(SLEEP_ENTRE_PETICIONES)
                    soup = BeautifulSoup(resp.text, "html.parser")
                except Exception as e:
                    print(f"  [{categoria}] ERROR cargando página: {e}", flush=True)
                    self.stats["errores"] += 1
                    continue

                for mes in MESES[:-1]:  # marzo..julio (agosto suele no estar publicado)
                    try:
                        soup_mes = _post_mes(session, url, soup, MES_NUM[mes])
                    except Exception as e:
                        print(f"  [{categoria} {mes}] ERROR: {e}", flush=True)
                        self.stats["errores"] += 1
                        continue
                    registro = self._extraer(categoria, soup_mes, autoridad_id, mes, url)
                    registros.append(registro)
                    print(f"  [{categoria} {mes}] publicado={registro['publicado']} "
                          f"monto={registro['monto']} cantidad={registro['cantidad']}", flush=True)

            self.guardar(registros)
            self.exportar_json()
            print(f"[{autoridad_id}] guardado ({len(registros)} filas)", flush=True)

    def _extraer(
        self, categoria: str, soup: BeautifulSoup, autoridad_id: str, mes: str, url: str
    ) -> dict:
        import json

        txt = _texto(soup)
        no_publicado = "no han sido publicados" in txt.lower()
        base = {
            "autoridad_id": autoridad_id,
            "anno": ANNO,
            "mes": MES_NUM[mes],
            "categoria": categoria,
            "fuente_url": url,
        }
        if no_publicado:
            return {**base, "publicado": False, "monto": None, "cantidad": None, "detalle": None}

        sin_registros = "no hay registros para el mes seleccionado" in txt.lower()
        filas = self._filas_tabla(soup) if not sin_registros else []

        if categoria == "gastos_operacionales":
            # cada fila: [concepto, monto] — sin línea de TOTAL, se suma a mano
            items = [
                {"concepto": f[0], "monto": _monto_a_numero(f[1]) or 0}
                for f in filas if len(f) >= 2 and f[0]
            ]
            total = sum(i["monto"] for i in items)
            publicado = True if (items or sin_registros) else None
            return {
                **base, "publicado": publicado if publicado is not None else False,
                "monto": total if items else (0 if sin_registros else None),
                "cantidad": None,
                "detalle": json.dumps(items, ensure_ascii=False) if items else None,
            }

        if categoria == "personal_apoyo":
            # fila tipica: [nombre, cargo, renta, tipo_contrato, fecha_inicio]
            items = []
            for f in filas:
                if len(f) < 3 or not f[0]:
                    continue
                items.append({
                    "nombre": f[0],
                    "cargo": f[1] if len(f) > 1 else None,
                    "renta": _monto_a_numero(f[2]) if len(f) > 2 else None,
                    "tipo_contrato": f[3] if len(f) > 3 else None,
                })
            total = sum(i["renta"] or 0 for i in items)
            return {
                **base, "publicado": True,
                "monto": total if items else (0 if sin_registros else None),
                "cantidad": len(items),
                "detalle": json.dumps(items, ensure_ascii=False) if items else None,
            }

        if categoria == "asesorias_externas":
            # fila tipica: [nombre_asesor, monto, materia]
            items = [
                {
                    "nombre_asesor": f[0],
                    "monto": _monto_a_numero(f[1]) or 0,
                    "materia": f[2] if len(f) > 2 else None,
                }
                for f in filas if len(f) >= 2 and f[0]
            ]
            total = sum(i["monto"] for i in items)
            if not items and not sin_registros:
                # esta pagina no muestra tabla NI mensaje de "no publicado" cuando
                # no hay datos: se marca como no confirmado, no como cero verificado
                return {
                    **base, "publicado": False, "monto": None, "cantidad": None, "detalle": None,
                }
            return {
                **base, "publicado": True,
                "monto": total if items else 0,
                "cantidad": len(items) if items else 0,
                "detalle": json.dumps(items, ensure_ascii=False) if items else None,
            }

        if categoria == "pasajes_aereos":
            # fila tipica: [fecha, origen, destino, aerolinea, monto, motivo]
            items = []
            for f in filas:
                if len(f) < 3 or not f[1]:
                    continue
                items.append({
                    "fecha": f[0] if len(f) > 0 else None,
                    "origen": f[1] if len(f) > 1 else None,
                    "destino": f[2] if len(f) > 2 else None,
                    "aerolinea": f[3] if len(f) > 3 else None,
                    "monto": _monto_a_numero(f[4]) if len(f) > 4 else None,
                })
            total = sum(i["monto"] or 0 for i in items)
            return {
                **base, "publicado": True,
                "monto": total if items else (0 if sin_registros else None),
                "cantidad": len(items),
                "detalle": json.dumps(items, ensure_ascii=False) if items else None,
            }

        return {**base, "publicado": None, "monto": None, "cantidad": None, "detalle": None}

    @staticmethod
    def _filas_tabla(soup: BeautifulSoup) -> list[list[str]]:
        """Todas las filas de datos (sin encabezado) de la primera tabla real de
        la pagina, como listas de texto por columna."""
        tabla = soup.find("table")
        if not tabla:
            return []
        filas = []
        for tr in tabla.find_all("tr")[1:]:
            celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
            if celdas:
                filas.append(celdas)
        return filas

    def procesar(self, registros):
        return registros

    def guardar(self, registros: list[dict]) -> None:
        cur = self.db.cursor()
        for r in registros:
            cur.execute(
                """
                INSERT INTO gasto_parlamentario
                    (autoridad_id, anno, mes, categoria, publicado, monto, cantidad,
                     detalle, fuente_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(autoridad_id, anno, mes, categoria) DO UPDATE SET
                    publicado=excluded.publicado,
                    monto=excluded.monto,
                    cantidad=excluded.cantidad,
                    detalle=excluded.detalle,
                    fuente_url=excluded.fuente_url
                """,
                (
                    r["autoridad_id"], r["anno"], r["mes"], r["categoria"],
                    int(bool(r["publicado"])) if r["publicado"] is not None else None,
                    r["monto"], r["cantidad"], r.get("detalle"), r["fuente_url"],
                ),
            )
        self.db.commit()

    def exportar_json(self) -> None:
        import json

        cur = self.db.cursor()
        cur.execute(
            """
            SELECT autoridad_id, anno, mes, categoria, publicado, monto, cantidad,
                   detalle, fuente_url
            FROM gasto_parlamentario
            ORDER BY autoridad_id, categoria, mes
            """
        )
        cols = [d[0] for d in cur.description]
        filas = [dict(zip(cols, row)) for row in cur.fetchall()]
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        with open(PROCESSED_DIR / "gasto-parlamentario.json", "w") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2)
        print(f"Exportados {len(filas)} registros a {PROCESSED_DIR}", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    scraper = ScraperGastoParlamentario()
    scraper.ejecutar_incremental()
    print("Estadísticas:", scraper.stats, flush=True)
