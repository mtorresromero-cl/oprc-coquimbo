"""Gasto operacional de los 7 diputados de la Región de Coquimbo (Distrito 5),
vía camara.cl (transparencia por Ley 20.285). Cuatro categorías, cada una en
su propia página del sitio, con su propio selector de mes/año:

- Gastos operacionales: monto total ejecutado. Confirmado que camara.cl
  todavía no publica NINGÚN mes de este período (2026-2030, inicia marzo
  2026) para ningún diputado probado — no es una falla del scraper, la
  propia página lo dice explícitamente.
- Asesorías externas: contratos de asesoría a honorarios (persona/empresa,
  monto, materia).
- Pasajes aéreos nacionales: vuelos nacionales financiados. "No hay
  registros para el mes seleccionado" es un cero real (voló 0 veces ese
  mes), distinto de "no publicado".
- Personal de apoyo: nómina de asesores/administrativos contratados
  (nombre, cargo, sueldo) — no varía por mes seleccionado en la práctica
  (es la nómina vigente), pero igual se re-consulta por mes por si un
  diputado tiene rotación de personal registrada con fecha.

IDs reales (prmId) encontrados a mano en camara.cl/diputados/diputados.aspx,
buscando cada apellido — no existe otro mapeo público confiable.
"""

import json
import re
import sqlite3
import time
from pathlib import Path

from base import BaseScraper
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

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

# el período actual (2026-2030) solo tiene estos meses como opción en el
# selector — no existe febrero (empieza el 11 de marzo).
MESES = ["marzo", "abril", "mayo", "junio", "julio", "agosto"]
MES_NUM = {m: i + 3 for i, m in enumerate(MESES)}

DDL_MES_ID = "ContentPlaceHolder1_ContentPlaceHolder1_DetallePlaceHolder_ddlMes"
ANNO = 2026


def _monto_a_numero(texto: str) -> float | None:
    texto = re.sub(r"\s+", "", texto or "").replace(".", "").replace(",", "")
    if not texto or texto in ("-",):
        return None
    try:
        return float(texto)
    except ValueError:
        return None


class ScraperGastoParlamentario(BaseScraper):
    """Recolecta gasto operacional/asesorías/pasajes/personal de apoyo de
    los diputados de la Región de Coquimbo, mes a mes, para el período
    2026-2030."""

    nombre = "gasto_parlamentario"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        # se guarda incrementalmente por diputado (ver ejecutar_incremental)
        # en vez de solo devolver todo al final: una corrida larga contra un
        # sitio con Cloudflare puede colgarse a mitad de camino (confirmado
        # en la práctica — 50+ min sin terminar, sin señales de error), y
        # sin guardado incremental esa corrida no deja nada útil aunque
        # haya recolectado la mayoría de los datos reales.
        raise NotImplementedError("usar ejecutar_incremental()")

    def ejecutar_incremental(self) -> None:
        self.log_inicio()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for autoridad_id, prm_id in DIPUTADOS_COQUIMBO.items():
                    print(f"[{autoridad_id}] prmId={prm_id}", flush=True)
                    page = browser.new_page(user_agent=USER_AGENT)
                    registros = []
                    registros.extend(self._gastos_operacionales(page, autoridad_id, prm_id))
                    registros.extend(self._pasajes_aereos(page, autoridad_id, prm_id))
                    registros.extend(self._asesorias_externas(page, autoridad_id, prm_id))
                    registros.extend(self._personal_apoyo(page, autoridad_id, prm_id))
                    page.close()
                    self.guardar(registros)
                    self.exportar_json()
                    print(f"[{autoridad_id}] guardado ({len(registros)} filas)", flush=True)
                    time.sleep(2)
                browser.close()
            self.log_fin("ok")
        except Exception as e:
            self.log_fin("error", str(e))
            raise

    def _selecciona_mes_y_lee(self, page, mes: str) -> str:
        page.select_option(f"#{DDL_MES_ID}", label=mes, timeout=15000)
        page.wait_for_load_state("load", timeout=15000)
        page.wait_for_timeout(800)
        return page.locator("body").inner_text(timeout=15000)

    def _gastos_operacionales(self, page, autoridad_id: str, prm_id: int) -> list[dict]:
        url = f"https://www.camara.cl/diputados/detalle/gastosoperacionales.aspx?prmId={prm_id}"
        try:
            page.goto(url, wait_until="load", timeout=20000)
        except Exception as e:
            print(f"  [gastos_operacionales] ERROR navegando: {e}", flush=True)
            self.stats["errores"] += 1
            return []
        registros = []
        for mes in MESES[:-1]:  # sin agosto: nunca hay dato publicado ese mes en curso
            try:
                texto = self._selecciona_mes_y_lee(page, mes)
            except Exception as e:
                print(f"  [gastos_operacionales {mes}] ERROR: {e}", flush=True)
                self.stats["errores"] += 1
                continue
            publicado = "no han sido publicados" not in texto
            monto = None
            if publicado:
                m = re.search(r"TOTAL[\s:]*\$?\s*([\d.,\s]+)", texto, re.IGNORECASE)
                if m:
                    monto = _monto_a_numero(m.group(1))
            registros.append(
                {
                    "autoridad_id": autoridad_id,
                    "anno": ANNO,
                    "mes": MES_NUM[mes],
                    "categoria": "gastos_operacionales",
                    "publicado": publicado,
                    "monto": monto,
                    "cantidad": None,
                    "fuente_url": url,
                }
            )
            print(f"  [gastos_operacionales {mes}] publicado={publicado} monto={monto}", flush=True)
        return registros

    def _pasajes_aereos(self, page, autoridad_id: str, prm_id: int) -> list[dict]:
        url = f"https://www.camara.cl/diputados/detalle/pasajesaereos.aspx?prmId={prm_id}"
        try:
            page.goto(url, wait_until="load", timeout=20000)
        except Exception as e:
            print(f"  [pasajes_aereos] ERROR navegando: {e}", flush=True)
            self.stats["errores"] += 1
            return []
        registros = []
        for mes in MESES[:-1]:
            try:
                texto = self._selecciona_mes_y_lee(page, mes)
            except Exception as e:
                print(f"  [pasajes_aereos {mes}] ERROR: {e}", flush=True)
                self.stats["errores"] += 1
                continue
            sin_registros = "No hay registros para el mes seleccionado" in texto
            no_publicado = "no han sido publicados" in texto
            cantidad = 0
            if not sin_registros and not no_publicado:
                # cada fila real de la tabla trae un origen/destino real
                # (dos comunas o "Santiago"/región) — se cuenta por
                # ocurrencias de fechas dd/mm/aaaa en el bloque de tabla,
                # más simple y robusto que adivinar encabezados de columna.
                cantidad = len(re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto))
            registros.append(
                {
                    "autoridad_id": autoridad_id,
                    "anno": ANNO,
                    "mes": MES_NUM[mes],
                    "categoria": "pasajes_aereos",
                    "publicado": not no_publicado,
                    "monto": None,
                    "cantidad": cantidad,
                    "fuente_url": url,
                }
            )
            pub = not no_publicado
            print(f"  [pasajes_aereos {mes}] publicado={pub} cantidad={cantidad}", flush=True)
        return registros

    def _asesorias_externas(self, page, autoridad_id: str, prm_id: int) -> list[dict]:
        url = f"https://www.camara.cl/diputados/detalle/asesoriaexterna.aspx?prmId={prm_id}"
        try:
            page.goto(url, wait_until="load", timeout=20000)
        except Exception as e:
            print(f"  [asesorias_externas] ERROR navegando: {e}", flush=True)
            self.stats["errores"] += 1
            return []
        registros = []
        for mes in MESES[:-1]:
            try:
                page.select_option(f"#{DDL_MES_ID}", label=mes.capitalize())
                page.wait_for_load_state("load", timeout=15000)
                page.wait_for_timeout(800)
                texto = page.locator("body").inner_text()
            except Exception as e:
                print(f"  [asesorias_externas {mes}] ERROR: {e}", flush=True)
                self.stats["errores"] += 1
                continue
            no_publicado = "no han sido publicados" in texto
            montos = re.findall(r"\$\s*([\d.,]+)", texto)
            total = sum(v for v in (_monto_a_numero(m) for m in montos) if v)
            registros.append(
                {
                    "autoridad_id": autoridad_id,
                    "anno": ANNO,
                    "mes": MES_NUM[mes],
                    "categoria": "asesorias_externas",
                    "publicado": not no_publicado,
                    "monto": total if total else None,
                    "cantidad": None,
                    "fuente_url": url,
                }
            )
            pub = not no_publicado
            print(f"  [asesorias_externas {mes}] publicado={pub} monto={total}", flush=True)
        return registros

    def _personal_apoyo(self, page, autoridad_id: str, prm_id: int) -> list[dict]:
        url = f"https://www.camara.cl/diputados/detalle/personaldepoyo.aspx?prmId={prm_id}"
        try:
            page.goto(url, wait_until="load", timeout=20000)
        except Exception as e:
            print(f"  [personal_apoyo] ERROR navegando: {e}", flush=True)
            self.stats["errores"] += 1
            return []
        registros = []
        for mes in MESES[:-1]:
            try:
                texto = self._selecciona_mes_y_lee(page, mes)
            except Exception as e:
                print(f"  [personal_apoyo {mes}] ERROR: {e}", flush=True)
                self.stats["errores"] += 1
                continue
            no_publicado = "no han sido publicados" in texto
            # cada fila real empieza con "Contrato" seguido de un sueldo en
            # formato NNN.NNN al final de la fila.
            sueldos = re.findall(r"Contrato\s+.+?\s([\d]{2,3}\.\d{3})\s", texto)
            total = sum(v for v in (_monto_a_numero(s) for s in sueldos) if v)
            registros.append(
                {
                    "autoridad_id": autoridad_id,
                    "anno": ANNO,
                    "mes": MES_NUM[mes],
                    "categoria": "personal_apoyo",
                    "publicado": not no_publicado,
                    "monto": total if total else None,
                    "cantidad": len(sueldos),
                    "fuente_url": url,
                }
            )
            n = len(sueldos)
            pub = not no_publicado
            print(f"  [personal_apoyo {mes}] publicado={pub} n={n} monto={total}", flush=True)
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        for r in registros:
            self.db.execute(
                """
                INSERT INTO gasto_parlamentario
                    (autoridad_id, anno, mes, categoria, publicado, monto, cantidad, fuente_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(autoridad_id, anno, mes, categoria) DO UPDATE SET
                    publicado = excluded.publicado,
                    monto = excluded.monto,
                    cantidad = excluded.cantidad,
                    fuente_url = excluded.fuente_url
                """,
                (
                    r["autoridad_id"], r["anno"], r["mes"], r["categoria"],
                    r["publicado"], r["monto"], r["cantidad"], r["fuente_url"],
                ),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        self.db.row_factory = sqlite3.Row
        filas = self.db.execute(
            """
            SELECT autoridad_id, anno, mes, categoria, publicado, monto, cantidad, fuente_url
            FROM gasto_parlamentario
            ORDER BY autoridad_id, categoria, mes
            """
        ).fetchall()
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "gasto-parlamentario.json").write_text(
            json.dumps([dict(f) for f in filas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Exportados {len(filas)} registros a {PROCESSED_DIR}", flush=True)


if __name__ == "__main__":
    scraper = ScraperGastoParlamentario()
    scraper.ejecutar_incremental()
    print("Estadísticas:", scraper.stats, flush=True)
