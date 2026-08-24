"""Presupuesto municipal (balance de ejecución presupuestaria trimestral)
desde los sitios propios de transparencia de cada municipalidad.

Piloto: La Serena. El sitio de transparencia municipal (subdominio propio,
no el portal central portaltransparencia.cl) es un PHP simple sin
protección — no requiere Playwright, httpx normal alcanza. El listado de
documentos está en `ptransact.php?n=<categoria>` y cada PDF trimestral trae
una tabla perfectamente extraíble con pdfplumber: CODIGO, DENOMINACION,
PRESUPUESTO INICIAL, PRESUPUESTO VIGENTE, INGRESOS PERCIBIDOS/OBLIGACION
ACUMULADA, SALDO. Se guarda solo el nivel más agregado de la jerarquía de
cuentas (código con formato XX-00-000-000-000) — el detalle completo tiene
cientos de líneas por documento, demasiado granular para un dashboard
comparativo.

Cada municipalidad probablemente tiene una plataforma distinta (confirmar
antes de generalizar a las 15 — ver docs/03-roadmap.md Fase 3).
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import httpx
import pdfplumber
from base import BaseScraper

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

# comuna_id -> (base_url del sitio de transparencia, n= de "Balance de ejecución presupuestaria")
MUNICIPIOS_COQUIMBO = {
    "la-serena": {
        "base_url": "https://transparencia.laserena.cl",
        "n_balance_ejecucion": 108,
    },
}

CODIGO_NIVEL_TOP = re.compile(r"^\d{2}-00-000-000-000$")


def _monto_a_numero(texto: str) -> float | None:
    texto = (texto or "").strip().replace(".", "").replace(",", "")
    if not texto or texto in ("-",):
        return None
    try:
        return float(texto)
    except ValueError:
        return None


class ScraperTransparenciaMunicipal(BaseScraper):
    """Recolecta el balance de ejecución presupuestaria trimestral más
    reciente de cada municipalidad configurada."""

    nombre = "transparencia_municipal"
    frecuencia = "semanal"

    def recolectar(self) -> list[dict]:
        registros = []
        for comuna_id, config in MUNICIPIOS_COQUIMBO.items():
            try:
                registros.extend(self._recolectar_comuna(comuna_id, config))
            except Exception:
                self.stats["errores"] += 1
        return registros

    def _recolectar_comuna(self, comuna_id: str, config: dict) -> list[dict]:
        base_url = config["base_url"]
        n = config["n_balance_ejecucion"]
        listado_url = f"{base_url}/ptransact.php?n={n}"

        resp = httpx.get(listado_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()

        # cada documento: título + fecha + link al PDF, en filas de tabla HTML
        filas = re.findall(
            r'<td[^>]*>([^<]*Balance[^<]*)</td>\s*<td[^>]*>([\d-]+)</td>.*?'
            r'href="(documentos/[^"]+\.pdf)"',
            resp.text,
            re.S,
        )
        if not filas:
            return []

        # solo el documento más reciente (evita re-parsear todo el historial cada semana)
        titulo, fecha_pub, pdf_rel = filas[0]
        pdf_url = f"{base_url}/{pdf_rel}"
        anno_m = re.search(r"(\d{4})", titulo)
        anno = int(anno_m.group(1)) if anno_m else datetime.now().year

        pdf_resp = httpx.get(pdf_url, timeout=30, follow_redirects=True)
        pdf_resp.raise_for_status()
        tmp_path = ROOT / "data" / "raw" / f"presupuesto_{comuna_id}_{anno}.pdf"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(pdf_resp.content)

        registros = []
        with pdfplumber.open(tmp_path) as pdf:
            tipo_actual = None
            for pagina in pdf.pages:
                texto = pagina.extract_text() or ""
                if "INGRESOS DE" in texto:
                    tipo_actual = "ingreso"
                elif "GASTOS DE" in texto:
                    tipo_actual = "gasto"
                if tipo_actual is None:
                    continue

                tabla = pagina.extract_table()
                if not tabla:
                    continue
                for fila in tabla:
                    if not fila or not fila[0] or not CODIGO_NIVEL_TOP.match(fila[0].strip()):
                        continue
                    categoria = (fila[1] or "").strip()
                    monto = _monto_a_numero(fila[4]) if len(fila) > 4 else None
                    if not categoria or monto is None:
                        continue
                    registros.append(
                        {
                            "comuna_id": comuna_id,
                            "anno": anno,
                            "tipo": tipo_actual,
                            "categoria": categoria,
                            "subcategoria": fila[0].strip(),
                            "monto": monto * 1000,  # el PDF reporta en miles de $
                            "fuente_url": pdf_url,
                        }
                    )
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        comunas = tuple(MUNICIPIOS_COQUIMBO.keys())
        placeholders = ",".join("?" * len(comunas))
        annos = {r["anno"] for r in registros} or {datetime.now().year}
        anno_placeholders = ",".join("?" * len(annos))
        self.db.execute(
            f"""
            DELETE FROM presupuesto_municipal
            WHERE comuna_id IN ({placeholders}) AND anno IN ({anno_placeholders})
            """,
            (*comunas, *annos),
        )
        ahora = datetime.now().isoformat()
        for r in registros:
            self.db.execute(
                """
                INSERT INTO presupuesto_municipal
                    (comuna_id, anno, tipo, categoria, subcategoria, monto,
                     fuente_url, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
