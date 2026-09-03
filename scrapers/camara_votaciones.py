"""Votaciones de sala de los diputados de la Región de Coquimbo, vía
quieneseljefe.cl (no camara.cl directo).

Reescrito el 2026-09-03 (segunda reescritura del día — ver
docs/06-bitacora.md para el historial completo de intentos previos con
camara.cl directo, todos fallidos por tiempo: 2 corridas de GitHub
Actions terminaron sin completar, una llevó más de 6 horas y la cortó
el timeout por defecto del job).

Por qué el cambio: camara.cl exige, por cada diputado, recorrer TODA su
ficha de votaciones paginada (decenas de páginas ya a esta altura de la
legislatura) solo para descubrir los IDs de votación, y después pedir el
detalle completo (roster de 155 nombres) de cada una — cientos de
peticiones, cada una con pausa deliberada de 4s por el rate-limiting
real del sitio. quieneseljefe.cl publica el historial COMPLETO de
votos de cada diputado en una sola página HTML estática
(`/diputado/{id}/{slug}`, mismo ID numérico `prmId` que usa camara.cl) —
7 peticiones en vez de la fase de descubrimiento completa. El detalle
agregado (a favor/en contra/no vota de los 155, y si se aprobó o
rechazó) todavía requiere una petición por votación única
(`/votacion/{id}/{slug}`) — eso no cambia, pero ya no hay fase de
descubrimiento paginada por delante.

Confirmado el 2026-09-02 comparando el boletín 18189-14 en camara.cl y
quieneseljefe.cl: cada proyecto tiene un voto "general" (una vez) y
votos "particular" (uno por artículo/indicación con votación separada)
— quieneseljefe.cl expone esto en el mismo campo `.dp-vote-summary` de
cada voto ("Incluye resultado de votacion general del proyecto." para
el general, o el texto del artículo/indicación para los particulares).

Pérdida real frente al detalle de camara.cl: la categoría "Abstención"
de camara.cl no siempre coincide 1:1 con la de quieneseljefe.cl — acá
se usa su categoría "No vota" (que probablemente mezcla abstención,
inhabilitado y dispensado) como aproximación de `abstenciones`. No se
guarda `numero_sesion` (esta fuente no lo expone en la página de
detalle de la votación).
"""

import json
import re
import sqlite3
from pathlib import Path

from base import BaseScraper
from camara_mociones import DIPUTADOS_COQUIMBO

try:
    from curl_cffi import requests as cffi_requests
except ImportError:  # pragma: no cover
    import sys

    print("Falta curl_cffi: pip install curl_cffi", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

BASE_URL = "https://quieneseljefe.cl"

MES_A_NUM = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}
ANNO_LEGISLATURA = 2026  # quieneseljefe.cl no publica el año en la fecha del voto
LEGISLATURA_INICIO = "2026-03-11"

BADGE_A_VOTO = {
    "A favor": "favor",
    "En contra": "contra",
    "Abstencion": "abstencion",
    "No vota": "ausente",
}


def _session():
    s = cffi_requests.Session(impersonate="chrome")
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        ),
    })
    return s


def _fecha_iso(texto_corto: str) -> str | None:
    # "19 AUG" -> "2026-08-19"
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})", texto_corto.strip())
    if not m:
        return None
    dia, mes_abrev = m.groups()
    mes = MES_A_NUM.get(mes_abrev.lower())
    if not mes:
        return None
    return f"{ANNO_LEGISLATURA}-{mes}-{int(dia):02d}"


class ScraperCamaraVotaciones(BaseScraper):
    """Trae los votos de cada diputado regional desde su página en
    quieneseljefe.cl, y el detalle agregado (resultado, tally) de cada
    votación única desde la página de detalle de esa misma fuente."""

    nombre = "camara_votaciones"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        from bs4 import BeautifulSoup

        session = _session()
        votos_por_diputado: dict[str, list[dict]] = {}
        # id_votacion -> {boletin, titulo, fecha, etapa, articulo}
        votaciones_vistas: dict[str, dict] = {}

        for autoridad_id, dip_id in DIPUTADOS_COQUIMBO.items():
            url = f"{BASE_URL}/diputado/{dip_id}/x"
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                print(f"  {autoridad_id}: ERROR cargando página: {e}", flush=True)
                self.stats["errores"] += 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select("#dp-vote-list .dp-vote-item")
            for item in items:
                link = item.select_one("a.dp-vi-row")
                badge = item.select_one(".dp-vote-badge")
                fecha_el = item.select_one(".dp-vote-date")
                boletin_el = item.select_one(".dp-vote-boletin")
                titulo_el = item.select_one(".dp-vote-name")
                resumen_el = item.select_one(".dp-vote-summary")
                if not (link and badge and fecha_el and boletin_el and titulo_el):
                    continue
                m_id = re.search(r"/votacion/(\d+)/", link["href"])
                if not m_id:
                    continue
                id_votacion = m_id.group(1)
                fecha = _fecha_iso(fecha_el.get_text())
                if not fecha or fecha < LEGISLATURA_INICIO:
                    continue
                voto = BADGE_A_VOTO.get(badge.get("title", "").strip())
                if not voto:
                    continue
                boletin = boletin_el.get_text(strip=True).removeprefix("Bol.").strip()
                resumen_txt = resumen_el.get_text(strip=True) if resumen_el else ""
                es_general = "resultado de votacion general" in resumen_txt.lower()

                votos_por_diputado.setdefault(autoridad_id, []).append(
                    {"id_votacion": id_votacion, "voto": voto, "fecha": fecha}
                )
                votaciones_vistas.setdefault(
                    id_votacion,
                    {
                        "boletin": boletin,
                        "titulo": titulo_el.get_text(strip=True),
                        "fecha": fecha,
                        "etapa": "general" if es_general else "particular",
                        "articulo": None if es_general else resumen_txt,
                        # se pide el detalle a quieneseljefe.cl (más
                        # liviano), pero lo que se guarda y se muestra en
                        # el sitio es la URL oficial de camara.cl — mismo
                        # id de votación en ambos sitios
                        "_url_fetch": f"{BASE_URL}{link['href']}",
                        "fuente_url": (
                            "https://www.camara.cl/legislacion/sala_sesiones/"
                            f"votacion_detalle.aspx?prmIdVotacion={id_votacion}"
                        ),
                    },
                )
            print(f"  {autoridad_id}: {len(items)} votos", flush=True)

        # ids ya guardados de corridas anteriores — el resultado de una
        # votación de sala es definitivo una vez cerrada, no hace falta
        # re-pedir su página de detalle cada semana
        ids_conocidos = {
            row[0].removeprefix("camara-")
            for row in self.db.execute(
                "SELECT id FROM votacion_sesion WHERE camara = 'camara'"
            ).fetchall()
        }
        ids_nuevos = [vid for vid in votaciones_vistas if vid not in ids_conocidos]
        print(
            f"  {len(votaciones_vistas)} votaciones descubiertas, {len(ids_nuevos)} nuevas",
            flush=True,
        )

        detalle_por_id: dict[str, dict] = {}
        for vid in ids_nuevos:
            info = votaciones_vistas[vid]
            try:
                resp = session.get(info["_url_fetch"], timeout=30)
                resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                print(f"  votación {vid}: ERROR cargando detalle: {e}", flush=True)
                self.stats["errores"] += 1
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            outcome = soup.select_one(".vdt-outcome-title")
            counts = [c.get_text(strip=True) for c in soup.select(".vdt-dch-count")]
            labels = [el.get_text(strip=True) for el in soup.select(".vdt-dch-label")]
            if not outcome or len(counts) < 2 or len(labels) < 2:
                self.stats["errores"] += 1
                continue
            por_label = dict(zip(labels, counts))
            try:
                favor = int(por_label.get("A favor", 0))
                contra = int(por_label.get("En contra", 0))
                no_vota = int(por_label.get("No vota", 0))
            except ValueError:
                self.stats["errores"] += 1
                continue
            detalle_por_id[vid] = {
                "resultado": outcome.get_text(strip=True).lower(),
                "votos_favor": favor,
                "votos_contra": contra,
                "abstenciones": no_vota,
            }

        registros = []
        for vid, detalle in detalle_por_id.items():
            registros.append({"id_votacion": vid, **votaciones_vistas[vid], **detalle})

        # un voto individual solo se guarda si su votación ya existe en la
        # base (de antes, o recién guardada arriba) — insertarlo sin eso
        # viola la foreign key sesion_id -> votacion_sesion(id)
        ids_resueltos = ids_conocidos | detalle_por_id.keys()
        self._votos_por_diputado = {
            autoridad_id: [v for v in votos if v["id_votacion"] in ids_resueltos]
            for autoridad_id, votos in votos_por_diputado.items()
        }
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
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
                    (id, camara, fecha, proyecto_ley_id, descripcion, etapa, articulo,
                     resultado, votos_favor, votos_contra, abstenciones, fuente_url)
                VALUES (?, 'camara', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    resultado = excluded.resultado,
                    votos_favor = excluded.votos_favor,
                    votos_contra = excluded.votos_contra,
                    abstenciones = excluded.abstenciones,
                    fuente_url = excluded.fuente_url
                """,
                (
                    f"camara-{r['id_votacion']}", r["fecha"], r["boletin"], r["titulo"],
                    r["etapa"], r["articulo"], r["resultado"], r["votos_favor"], r["votos_contra"],
                    r["abstenciones"], r["fuente_url"],
                ),
            )
            self.stats["nuevos"] += 1

        for autoridad_id, votos in self._votos_por_diputado.items():
            for v in votos:
                self.db.execute(
                    """
                    INSERT INTO voto (autoridad_id, sesion_id, voto, fecha)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(autoridad_id, sesion_id) DO UPDATE SET voto = excluded.voto
                    """,
                    (autoridad_id, f"camara-{v['id_votacion']}", v["voto"], v["fecha"]),
                )
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
