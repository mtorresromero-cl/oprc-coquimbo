"""Intervenciones en sala de los 3 senadores de la Región de Coquimbo, vía
www.senado.cl (Legislatura 374, 2026-2030), para el mismo tipo de análisis
de texto que ya existe para diputados (scrapers/intervenciones_sala.py +
analisis_intervenciones.py).

A diferencia de camara.cl (que exige parsear un PDF completo del boletín de
sesión con un patrón "El señor/La señora APELLIDO.-"), senado.cl publica
cada intervención como su propia página, renderizada por Next.js con los
datos completos embebidos en un <script id="__NEXT_DATA__"> — no hace falta
parsear PDF ni desambiguar apellidos con regex: el texto ya viene separado
por intervención, con el nombre completo del senador/a en NOMBRE.

Estructura descubierta a mano el 2026-09-02, inspeccionando el HTML real:

- Página de una sesión: /actividad-legislativa/sala-de-sesiones/sesiones-de-sala/{sesion_id}
  trae node.mainData: ID_SESION, NRO_SESION, NRO_LEGISLATURA, FECHA, etc.
  (esto es la pestaña "Tabla" — la orden del día, no las intervenciones).
- Página de una intervención puntual: .../sesiones-de-sala/{sesion_id}/{tag}
  trae node.interventionTextData: NOMBRE, TIPO ("Senador"/"Senadora"/...),
  TEMA, BOLETIN, TEXTO (texto completo, con <br/> como salto de línea).
  `tag` es simplemente la posición de la intervención dentro de esa sesión
  (1, 2, 3...) — se recorre hasta el primer 404.

No hay un listado público simple de todas las sesiones de la legislatura
(el listado de la web se arma con una llamada aparte a
web-back.senado.cl/api/... que, a diferencia de /api/legislatures y
/api/sessions/attendance que sí usa senado_asistencia.py, no se logró
confirmar de forma confiable). En su lugar, se recorren los ID_SESION de
forma secuencial desde MIN_SESION_ID (Sesión 1 de la Legislatura 374,
confirmado a mano) — no son perfectamente consecutivos (hay huecos), así
que se tolera una racha de fallos antes de dar por terminada la búsqueda.
Cuando cambie la legislatura habrá que actualizar MIN_SESION_ID a mano.
"""

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from base import BaseScraper
from senado_asistencia import SENADORES_COQUIMBO, _es_la_misma_persona, _tokens

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

BASE_URL = "https://www.senado.cl"
SESION_URL = f"{BASE_URL}/actividad-legislativa/sala-de-sesiones/sesiones-de-sala"

MIN_SESION_ID = 10124  # Sesión 1, Legislatura 374 — ajustar a mano si cambia la legislatura
MAX_FALLOS_CONSECUTIVOS = 20  # sesiones: cuántos ID_SESION seguidos sin sesión real antes de parar
# intervenciones: la numeración de "tag" NO es un correlativo denso desde 1
# — se confirmó a mano que la sesión 10124 (56 min de sala) tiene 6 fallos
# seguidos antes del primer tag válido (7), y termina recién en el tag 56.
# 60 da margen real sin quedar escaneando para siempre.
MAX_TAGS_FALLOS_CONSECUTIVOS = 60
SLEEP_ENTRE_PETICIONES = 0.3

NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _obtener_next_data(client, url: str) -> dict | None:
    """None si la página no existe (404) o no trae __NEXT_DATA__ (página de
    error genérica en vez de un 404 real, visto en la práctica)."""
    resp = client.get(url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    m = NEXT_DATA_RE.search(resp.text)
    if not m:
        return None
    return json.loads(m.group(1))


def _fetch_sesion(client, sesion_id: int) -> dict | None:
    data = _obtener_next_data(client, f"{SESION_URL}/{sesion_id}")
    if not data:
        return None
    try:
        return data["props"]["pageProps"]["resource"]["data"]["node"]["mainData"]
    except (KeyError, TypeError):
        return None


def _fetch_intervencion(client, sesion_id: int, tag: int) -> dict | None:
    data = _obtener_next_data(client, f"{SESION_URL}/{sesion_id}/{tag}")
    if not data:
        return None
    try:
        return data["props"]["pageProps"]["resource"]["data"]["node"]["interventionTextData"]
    except (KeyError, TypeError):
        return None


def _limpiar_texto(texto: str | None) -> str | None:
    if not texto:
        return None
    texto = re.sub(r"<br\s*/?>", " ", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto or None


def _es_fecha_futura(fecha_str: str | None, hoy: date) -> bool:
    if not fecha_str:
        return False
    try:
        d, m, a = (int(x) for x in fecha_str.split("/"))
        return date(a, m, d) > hoy
    except ValueError:
        return False


class ScraperSenadoIntervenciones(BaseScraper):
    nombre = "senado_intervenciones"
    frecuencia = "semanal"

    def recolectar(self):
        raise NotImplementedError("usar ejecutar_incremental()")

    def ejecutar_incremental(self, sesion_id_max: int | None = None) -> None:
        tokens_autoridades = {
            aid: _tokens(self._nombre_completo(aid)) for aid in SENADORES_COQUIMBO
        }

        ya_guardadas = {
            row[0] for row in self.db.execute(
                "SELECT DISTINCT sesion_id FROM intervencion_sala_senado"
            ).fetchall()
        }

        hoy = date.today()
        sesion_id = MIN_SESION_ID
        fallos = 0
        while fallos < MAX_FALLOS_CONSECUTIVOS:
            if sesion_id_max and sesion_id > sesion_id_max:
                break
            sid = str(sesion_id)
            if sid in ya_guardadas:
                fallos = 0
                sesion_id += 1
                continue

            try:
                main_data = _fetch_sesion(self.client, sesion_id)
            except Exception as e:
                print(f"  [{sid}] ERROR sesión: {e}", flush=True)
                self.stats["errores"] += 1
                main_data = None
            time.sleep(SLEEP_ENTRE_PETICIONES)

            if main_data is None:
                fallos += 1
                sesion_id += 1
                continue
            fallos = 0

            nro_legislatura = main_data.get("NRO_LEGISLATURA")
            if nro_legislatura and nro_legislatura < 374:
                sesion_id += 1
                continue

            fecha = main_data.get("FECHA")
            if _es_fecha_futura(fecha, hoy):
                print(f"  [{sid}] sesión aún no ocurre ({fecha}) — se revisa después", flush=True)
                sesion_id += 1
                continue

            nro_sesion = main_data.get("NRO_SESION")
            etiqueta = f"{nro_sesion or '?'} / {nro_legislatura}"

            registros = []
            hubo_algun_tag_publicado = False
            tag = 1
            tag_fallos = 0
            while tag_fallos < MAX_TAGS_FALLOS_CONSECUTIVOS:
                try:
                    interv = _fetch_intervencion(self.client, sesion_id, tag)
                except Exception as e:
                    print(f"  [{sid}] ERROR intervención {tag}: {e}", flush=True)
                    self.stats["errores"] += 1
                    interv = None
                time.sleep(SLEEP_ENTRE_PETICIONES)

                if interv is None:
                    tag_fallos += 1
                    tag += 1
                    continue
                tag_fallos = 0
                # cualquier tag válido (aunque sea de otro senador/otra
                # persona) confirma que senado.cl ya publicó el texto de
                # esta sesión — recién ahí es seguro concluir "ninguno de
                # los 3 habló" y no volver a revisarla.
                hubo_algun_tag_publicado = True

                if interv.get("TIPO") == "Senador":
                    tokens_fila = _tokens(interv.get("NOMBRE") or "")
                    autoridad_id = next(
                        (
                            aid
                            for aid, tk in tokens_autoridades.items()
                            if _es_la_misma_persona(tk, tokens_fila)
                        ),
                        None,
                    )
                    if autoridad_id:
                        registros.append({
                            "sesion_id": sid,
                            "numero_sesion": int(nro_sesion) if nro_sesion else None,
                            "etiqueta_sesion": etiqueta,
                            "fecha": fecha,
                            "tag": tag,
                            "autoridad_id": autoridad_id,
                            "tema": interv.get("TEMA"),
                            "boletin": interv.get("BOLETIN"),
                            "texto": _limpiar_texto(interv.get("TEXTO")),
                        })
                tag += 1

            if registros:
                self.guardar(registros)
                print(f"  [{sid}] {len(registros)} intervenciones de la región", flush=True)
            elif hubo_algun_tag_publicado:
                self._marcar_sesion_vacia(sid, nro_sesion, etiqueta, fecha)
                print(f"  [{sid}] ningún senador de la región intervino", flush=True)
            else:
                # senado.cl todavía no publica el texto de esta sesión (0
                # tags válidos en todo el rango escaneado) — no se marca
                # como revisada, así se reintenta en la próxima corrida en
                # vez de quedar descartada para siempre.
                print(f"  [{sid}] aún sin texto publicado — se revisa en otra corrida", flush=True)

            sesion_id += 1

        self.exportar_json()

    def _nombre_completo(self, autoridad_id: str) -> str:
        fila = self.db.execute(
            "SELECT nombre_completo FROM autoridad WHERE id = ?", (autoridad_id,)
        ).fetchone()
        return fila[0] if fila else autoridad_id

    def _marcar_sesion_vacia(
        self, sesion_id: str, nro_sesion, etiqueta: str, fecha: str | None
    ) -> None:
        self.db.execute(
            """
            INSERT OR IGNORE INTO intervencion_sala_senado
                (sesion_id, numero_sesion, etiqueta_sesion, fecha, tag,
                 autoridad_id, tema, boletin, texto)
            VALUES (?, ?, ?, ?, 0, NULL, NULL, NULL, NULL)
            """,
            (sesion_id, int(nro_sesion) if nro_sesion else None, etiqueta, fecha),
        )
        self.db.commit()

    def procesar(self, registros):
        return registros

    def guardar(self, registros: list[dict]) -> None:
        cur = self.db.cursor()
        for r in registros:
            cur.execute(
                """
                INSERT INTO intervencion_sala_senado
                    (sesion_id, numero_sesion, etiqueta_sesion, fecha, tag,
                     autoridad_id, tema, boletin, texto)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sesion_id, tag) DO UPDATE SET
                    autoridad_id=excluded.autoridad_id,
                    tema=excluded.tema,
                    boletin=excluded.boletin,
                    texto=excluded.texto
                """,
                (
                    r["sesion_id"], r["numero_sesion"], r["etiqueta_sesion"], r["fecha"],
                    r["tag"], r["autoridad_id"], r["tema"], r["boletin"], r["texto"],
                ),
            )
        self.db.commit()

    def exportar_json(self) -> None:
        cur = self.db.cursor()
        cur.execute(
            """
            SELECT sesion_id, numero_sesion, etiqueta_sesion, fecha, autoridad_id,
                   tema, boletin, texto
            FROM intervencion_sala_senado
            WHERE autoridad_id IS NOT NULL
            ORDER BY numero_sesion, autoridad_id
            """
        )
        cols = [d[0] for d in cur.description]
        filas = [dict(zip(cols, row)) for row in cur.fetchall()]
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        with open(PROCESSED_DIR / "intervenciones-sala-senado.json", "w") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2)
        print(f"Exportados {len(filas)} registros a {PROCESSED_DIR}", flush=True)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else None
    scraper = ScraperSenadoIntervenciones()
    scraper.ejecutar_incremental(sesion_id_max=limite)
    print("Estadísticas:", scraper.stats, flush=True)
