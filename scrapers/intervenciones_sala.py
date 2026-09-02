"""Intervenciones en sala de los 7 diputados de la Región de Coquimbo, vía
camara.cl (Legislatura 374, 2026-2030), para análisis de texto: palabras más
usadas, tendencias en el tiempo, coocurrencia.

Dos fuentes por sesión, mismo mecanismo de sesión ASP.NET que gasto_parlamentario.py
(GET a sesiones_sala.aspx, POST del <select> de sesión con curl_cffi/impersonate
chrome — no la petición AJAX que Cloudflare bloquea, ver gasto_parlamentario.py):

1. intervenciones.aspx — tabla estructurada real (no requiere parsear PDF):
   diputado/a, bancada, tipo de intervención, ítem, duración. Se lee
   reusando la sesión (cookies) tras el POST del <select> de sesión.
2. El boletín de la sesión (PDF, texto completo de la sala) se descarga
   directo por id de sesión: verdoc.aspx?prmid={id}&prmtipo=TEXTOSESION&
   prmtipodoc=83 — sin necesitar el flujo de sesión/cookies, confirmado con
   una petición completamente aislada.

El texto del boletín usa el patrón real "El señor/La señora APELLIDO(S).-
[texto]" para cada intervención. Los apellidos son ambiguos por sí solos
(hay ~155 diputados, apellidos como "Castillo" o "Rojas" se repiten) — por
eso NUNCA se acepta un match solo por apellido en el PDF: se exige que ese
apellido aparezca en la tabla de intervenciones.aspx de la MISMA sesión
como uno de nuestros 7 diputados antes de aceptar el bloque de texto.
"""

import json
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

SLEEP_ENTRE_PETICIONES = 3.0
MAX_LARGO_TEXTO = 4500  # ver nota en extraer_discursos
REINTENTOS = 4

BASE_URL = "https://www.camara.cl"
SESIONES_URL = f"{BASE_URL}/legislacion/sesiones_sala/sesiones_sala.aspx"
INTERVENCIONES_URL = f"{BASE_URL}/legislacion/sesiones_sala/intervenciones.aspx"

# apellido paterno real (el que usan las transcripciones de sala) -> autoridad_id
APELLIDO_A_AUTORIDAD = {
    "SALINAS": "bernardo-antonio-salinas-maya-diputado",
    "SULANTAY": "marco-antonio-sulantay-olivares-diputado",
    "CASTILLO": "nathalie-castillo-rojas-diputado",
    "GROHS": "erich-christ-grohs-marin-diputado",
    "MANOUCHEHRI": "daniel-manouchehri-lobos-diputado",
    "URQUETA": "eileen-patricia-urqueta-rojas-diputado",
    "TELLO": "carolina-tello-rojas-diputado",
}

# primer nombre real (el que camara.cl usa en la lista de diputados), para
# confirmar la fila correcta en intervenciones.aspx cuando el apellido por
# sí solo es ambiguo a nivel nacional (ver APELLIDOS_AMBIGUOS más abajo) —
# "Castillo" existe dos veces en el Congreso actual (Nathalie, Distrito 5,
# PC — la nuestra — y Priscilla, Distrito 17, DC, sin relación).
PRIMER_NOMBRE = {
    "SALINAS": "BERNARDO",
    "SULANTAY": "MARCO",
    "CASTILLO": "NATHALIE",
    "GROHS": "ERICH",
    "MANOUCHEHRI": "DANIEL",
    "URQUETA": "EILEEN",
    "TELLO": "CAROLINA",
}


def _request_con_backoff(session, metodo: str, url: str, **kwargs):
    ultimo_error = None
    for intento in range(1, REINTENTOS + 1):
        try:
            resp = session.request(metodo, url, timeout=kwargs.pop("timeout", 30), **kwargs)
            if resp.status_code in (403, 429):
                raise RuntimeError(f"bloqueado (status {resp.status_code})")
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001
            ultimo_error = e
            if intento >= REINTENTOS:
                raise
            espera = SLEEP_ENTRE_PETICIONES * (intento + 2) * 3
            log.warning(
                "%s %s falló (intento %d/%d): %s; reintentando en %.0fs",
                metodo, url[-80:], intento, REINTENTOS, e, espera,
            )
            time.sleep(espera)
    raise ultimo_error  # pragma: no cover


def make_session():
    session = cffi_requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)
    return session


def _viewstate(soup: BeautifulSoup) -> dict:
    tokens = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        el = soup.find("input", {"name": name})
        if el:
            tokens[name] = el.get("value", "")
    return tokens


def listar_sesiones(session) -> list[dict]:
    """Todas las sesiones de la legislatura actualmente seleccionada (374,
    2026-2030 mientras dure)."""
    resp = _request_con_backoff(session, "GET", SESIONES_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    sel = soup.find("select", {"id": re.compile(r"ddlSesion")})
    sesiones = []
    for opt in sel.find_all("option"):
        m = re.match(r"(\d+)ª,\s*\w+\s+(\d{1,2})\s+(\w+)\s+(\d{4})", opt.get_text(strip=True))
        if not m:
            continue  # sesiones "0ª" especiales (constitutiva, etc.) sin número real
        sesiones.append({
            "sesion_id": opt.get("value"),
            "numero": int(m.group(1)),
            "etiqueta": opt.get_text(strip=True),
        })
    return sesiones


def seleccionar_sesion(session, sesion_id: str) -> None:
    resp = _request_con_backoff(session, "GET", SESIONES_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    tokens = _viewstate(soup)
    sel = soup.find("select", {"id": re.compile(r"ddlSesion")})
    data = {**tokens, "__EVENTTARGET": sel["name"], sel["name"]: sesion_id}
    _request_con_backoff(
        session, "POST", SESIONES_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    time.sleep(SLEEP_ENTRE_PETICIONES)


def intervenciones_tabla(session) -> list[dict]:
    """Requiere haber llamado seleccionar_sesion() antes (misma session/cookies)."""
    resp = _request_con_backoff(session, "GET", INTERVENCIONES_URL)
    time.sleep(SLEEP_ENTRE_PETICIONES)
    soup = BeautifulSoup(resp.text, "html.parser")
    tabla = soup.find("table")
    filas = []
    if not tabla:
        return filas
    for tr in tabla.find_all("tr")[1:]:
        celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(celdas) < 6:
            continue
        nombre_completo = celdas[0]
        filas.append({
            "nombre": nombre_completo,
            "bancada": celdas[1],
            "tipo": celdas[2],
            "item": celdas[3],
            "detalle": celdas[4],
            "duracion": celdas[5],
        })
    return filas


def descargar_boletin_texto(session, sesion_id: str) -> str | None:
    url = f"{BASE_URL}/verdoc.aspx?prmid={sesion_id}&prmtipo=TEXTOSESION&prmtipodoc=83"
    resp = _request_con_backoff(session, "GET", url, timeout=60)
    time.sleep(SLEEP_ENTRE_PETICIONES)
    if resp.headers.get("content-type", "").split(";")[0] != "application/pdf":
        return None
    import io

    import pdfplumber
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


# "El señor/La señora/La señorita APELLIDO(S).-" — apellido puede tener
# varias palabras (ej. "DE LA CARRERA"), pero nuestros 7 son de una sola
# palabra. Se corta en el siguiente marcador del mismo patrón (o fin de
# texto). Nota real: esto solo existe para intervenciones tipo "Discurso"
# (Orden del Día, Artículo 33, etc.) — las de "Acuerdos y Resoluciones"
# (votos/mociones) se registran como resumen en tercera persona sin cita
# textual, así que quedan sin texto aunque el diputado sí haya hablado.
_TRATAMIENTO = r"(?:El señor|La señora|La señorita)"
# la mesa (presidente/a, vicepresidente/a) a veces se identifica con una
# coma antes del calificador — "La señora OSSANDÓN, doña Ximena
# (Vicepresidenta).-" — a diferencia del formato normal de un diputado/a
# cualquiera, "La señorita CASTILLO (doña Nathalie).-"; si no se reconoce
# esta variante como límite válido, el texto de quien habló antes se sigue
# capturando de más hasta el próximo marcador real (visto en la práctica:
# intervenciones de otros diputados/as o hasta la lista de asistencia
# colándose al final del texto de uno de los nuestros)
_CALIFICADOR_CAPTURA = r"(?:,\s*(?:doña|don)\s+[A-ZÑÁÉÍÓÚa-zñáéíóú]+)?\s*(?:\(([^)]*)\))?"
_CALIFICADOR_SIMPLE = r"(?:,\s*(?:doña|don)\s+[A-ZÑÁÉÍÓÚa-zñáéíóú]+)?\s*(?:\([^)]*\))?"
PATRON_INTERVENCION = re.compile(
    rf"{_TRATAMIENTO}\s+([A-ZÑÁÉÍÓÚ][A-ZÑÁÉÍÓÚ\s]*?){_CALIFICADOR_CAPTURA}\.-\s*(.+?)"
    rf"(?={_TRATAMIENTO}\s+[A-ZÑÁÉÍÓÚ][A-ZÑÁÉÍÓÚ\s]*?{_CALIFICADOR_SIMPLE}\.-|\Z)",
    re.S,
)

# "CASTILLO" es el único apellido de los 7 que existe más de una vez en el
# Congreso actual (también está Priscilla Castillo, Distrito 17, DC — nada
# que ver con Nathalie Castillo, Distrito 5, PC). Para ese apellido en
# particular, el texto plano "El señor/La señora CASTILLO.-" es ambiguo por
# sí solo si las dos hablaron en la misma sesión: solo se acepta con el
# calificador "(doña Nathalie)" explícito, o si por la tabla de
# intervenciones.aspx de esa sesión se sabe que la otra Castillo no habló.
APELLIDOS_AMBIGUOS = {"CASTILLO": {"nathalie-castillo-rojas-diputado": "NATHALIE"}}


def extraer_discursos(
    texto_boletin: str, apellidos_confirmados: set[str], apellidos_multiples: set[str] = frozenset()
) -> dict[str, list[str]]:
    """apellidos_confirmados: apellidos que realmente hablaron en ESTA sesión
    según la tabla de intervenciones.aspx (evita falsos positivos de
    apellidos comunes que pertenecen a otros diputados del país).
    apellidos_multiples: de esos, los que en ESTA sesión corresponden a más
    de una persona real en el Congreso (ej. las dos "Castillo" hablaron el
    mismo día) — para esos se exige el calificador "(don/doña Nombre)"."""
    resultado: dict[str, list[str]] = {}
    for m in PATRON_INTERVENCION.finditer(texto_boletin):
        apellido = m.group(1).strip().split()[0]  # primera palabra, nuestros 7 son simples
        if apellido not in apellidos_confirmados:
            continue

        if apellido in apellidos_multiples:
            candidatos = APELLIDOS_AMBIGUOS.get(apellido, {})
            calificador = (m.group(2) or "").upper()
            autoridad_id = next(
                (aid for aid, nombre in candidatos.items() if nombre in calificador), None
            )
            if not autoridad_id:
                continue  # ambiguo sin calificador explícito — se descarta, no se adivina
        else:
            autoridad_id = APELLIDO_A_AUTORIDAD.get(apellido)
        if not autoridad_id:
            continue

        texto = re.sub(r"\s+", " ", m.group(3)).strip()
        if len(texto) < 20:  # interrupciones/frases sueltas, no una intervención real
            continue
        if len(texto) > MAX_LARGO_TEXTO:
            # red de seguridad: una intervención real de sala no llega a
            # esto — si pasa, es casi seguro que el límite real (otro
            # formato de marcador de la mesa que no reconocemos aún) no se
            # detectó y se siguió capturando texto ajeno (listas de
            # asistencia, tabla de comisiones, etc.)
            corte = texto.rfind(".", 0, MAX_LARGO_TEXTO)
            texto = texto[: corte + 1] if corte != -1 else texto[:MAX_LARGO_TEXTO]
        resultado.setdefault(autoridad_id, []).append(texto)
    return resultado


class ScraperIntervencionesSala(BaseScraper):
    nombre = "intervenciones_sala"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        raise NotImplementedError("usar ejecutar_incremental()")

    def ejecutar_incremental(self) -> None:
        session = make_session()
        sesiones = listar_sesiones(session)
        print(f"{len(sesiones)} sesiones encontradas en la legislatura actual", flush=True)

        # una sesión solo se considera "ya guardada" (y se salta) si NINGUNA
        # de sus filas quedó con texto=NULL en un tipo que sí debería
        # traerlo — "Acuerdos y Resoluciones" es la única excepción real
        # (se registra sin cita textual aunque el diputado haya hablado, ver
        # docstring del módulo). Si el boletín PDF no estaba listo todavía
        # al momento del scraping, antes la sesión igual quedaba marcada
        # como resuelta para siempre con el texto vacío — ahora se
        # reintenta en la próxima corrida hasta conseguirlo.
        ya_guardadas = {
            row[0] for row in self.db.execute(
                """
                SELECT sesion_id FROM intervencion_sala
                GROUP BY sesion_id
                HAVING SUM(
                    CASE WHEN texto IS NULL AND tipo != 'Acuerdos y Resoluciones' THEN 1 ELSE 0 END
                ) = 0
                """
            ).fetchall()
        }

        for s in sesiones:
            if s["sesion_id"] in ya_guardadas:
                continue
            try:
                seleccionar_sesion(session, s["sesion_id"])
                tabla = intervenciones_tabla(session)
            except Exception as e:
                print(f"  [{s['etiqueta']}] ERROR tabla: {e}", flush=True)
                self.stats["errores"] += 1
                continue

            # cuantos nombres COMPLETOS distintos, en TODA la tabla (no solo
            # los nuestros), llevan cada apellido — si un apellido de los
            # nuestros aparece más de una vez en la sesión (con nombres de
            # pila distintos), es ambiguo y hay que exigir el calificador
            # "(don/doña Nombre)" en el PDF en vez de confiar en el apellido
            # solo (caso real: Nathalie Castillo y Priscilla Castillo)
            apellidos_en_tabla: dict[str, set[str]] = {}
            for fila in tabla:
                for apellido in APELLIDO_A_AUTORIDAD:
                    if re.search(rf"\b{apellido.capitalize()}\b", fila["nombre"], re.I):
                        apellidos_en_tabla.setdefault(apellido, set()).add(fila["nombre"])
            apellidos_multiples = {
                ap for ap, nombres in apellidos_en_tabla.items() if len(nombres) > 1
            }

            apellidos_sesion = set()
            nuestros_en_sesion = []
            for fila in tabla:
                for apellido, autoridad_id in APELLIDO_A_AUTORIDAD.items():
                    # nombre real en la tabla viene "H.D. Nombre Apellido B." —
                    # se exige apellido Y primer nombre para no confundir
                    # homónimos nacionales (ver apellidos_multiples arriba)
                    nombre_fila = fila["nombre"]
                    tiene_apellido = re.search(rf"\b{apellido.capitalize()}\b", nombre_fila, re.I)
                    primer_nombre = PRIMER_NOMBRE[apellido].capitalize()
                    tiene_nombre = re.search(rf"\b{primer_nombre}\b", nombre_fila, re.I)
                    if tiene_apellido and tiene_nombre:
                        apellidos_sesion.add(apellido)
                        nuestros_en_sesion.append((autoridad_id, apellido, fila))

            if not nuestros_en_sesion:
                print(f"  [{s['etiqueta']}] ningún diputado de la región intervino", flush=True)
                self._marcar_sesion_vacia(s)
                continue

            try:
                texto = descargar_boletin_texto(session, s["sesion_id"])
            except Exception as e:
                print(f"  [{s['etiqueta']}] ERROR boletín: {e}", flush=True)
                self.stats["errores"] += 1
                continue

            discursos = (
                extraer_discursos(texto or "", apellidos_sesion, apellidos_multiples)
                if texto
                else {}
            )

            registros = []
            for autoridad_id, apellido, fila in nuestros_en_sesion:
                textos = discursos.get(autoridad_id, [])
                registros.append({
                    "sesion_id": s["sesion_id"],
                    "numero_sesion": s["numero"],
                    "etiqueta_sesion": s["etiqueta"],
                    "autoridad_id": autoridad_id,
                    "tipo": fila["tipo"],
                    "detalle": fila["detalle"],
                    "duracion": fila["duracion"],
                    "texto": " ".join(textos) if textos else None,
                })
            self.guardar(registros)
            print(
                f"  [{s['etiqueta']}] {len(nuestros_en_sesion)} intervenciones de la región, "
                f"{sum(1 for r in registros if r['texto'])} con texto extraído",
                flush=True,
            )

        self.exportar_json()

    def _marcar_sesion_vacia(self, sesion: dict) -> None:
        # deja registro de que la sesión fue revisada, sin intervenciones de
        # la región, para no reintentarla en la próxima corrida
        self.db.execute(
            """
            INSERT OR IGNORE INTO intervencion_sala
                (sesion_id, numero_sesion, etiqueta_sesion, autoridad_id,
                 tipo, detalle, duracion, texto)
            VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (sesion["sesion_id"], sesion["numero"], sesion["etiqueta"]),
        )
        self.db.commit()

    def procesar(self, registros):
        return registros

    def guardar(self, registros: list[dict]) -> None:
        cur = self.db.cursor()
        for r in registros:
            cur.execute(
                """
                INSERT INTO intervencion_sala
                    (sesion_id, numero_sesion, etiqueta_sesion, autoridad_id,
                     tipo, detalle, duracion, texto)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sesion_id, autoridad_id, tipo, detalle) DO UPDATE SET
                    duracion=excluded.duracion,
                    texto=excluded.texto
                """,
                (
                    r["sesion_id"], r["numero_sesion"], r["etiqueta_sesion"], r["autoridad_id"],
                    r["tipo"], r["detalle"], r["duracion"], r["texto"],
                ),
            )
        self.db.commit()

    def exportar_json(self) -> None:
        cur = self.db.cursor()
        cur.execute(
            """
            SELECT sesion_id, numero_sesion, etiqueta_sesion, autoridad_id,
                   tipo, detalle, duracion, texto
            FROM intervencion_sala
            WHERE autoridad_id IS NOT NULL
            ORDER BY numero_sesion, autoridad_id
            """
        )
        cols = [d[0] for d in cur.description]
        filas = [dict(zip(cols, row)) for row in cur.fetchall()]
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        with open(PROCESSED_DIR / "intervenciones-sala.json", "w") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2)
        print(f"Exportados {len(filas)} registros a {PROCESSED_DIR}", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    scraper = ScraperIntervencionesSala()
    scraper.ejecutar_incremental()
    print("Estadísticas:", scraper.stats, flush=True)
