"""Genera el informe mensual del observatorio y lo envía por Mailrelay a
la lista de suscriptores del newsletter.

Corre automáticamente el día 1 de cada mes (ver
.github/workflows/informe-mensual.yml), resumiendo el mes calendario
recién terminado — no el mes en curso.

Uso:
    python scrapers/informe_mensual.py                # mes anterior, solo genera el HTML (dry-run)
    python scrapers/informe_mensual.py 2026-07         # un mes específico, dry-run
    python scrapers/informe_mensual.py --send          # mes anterior, genera Y envía por Mailrelay
    python scrapers/informe_mensual.py 2026-07 --send  # un mes específico, genera Y envía

Sin --send nunca llama a la API de envío — solo escribe el HTML en
data/informes/ para poder revisarlo antes de mandarlo a suscriptores
reales.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analisis_intervenciones import parsear_fecha  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
SALIDA_DIR = ROOT / "data" / "informes"

MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

MAILRELAY_DOMINIO = "oprcoquimbo1.ipzmarketing.com"
MAILRELAY_GRUPO_NEWSLETTER = 1
COLOR_MARCA = "#aa0000"


def cargar(nombre: str) -> list[dict]:
    with open(PROCESSED / nombre, encoding="utf-8") as f:
        return json.load(f)


def mes_objetivo() -> tuple[int, int]:
    """Por defecto, el mes calendario recién terminado (hoy es de otro mes)."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        anno, mes = map(int, args[0].split("-"))
        return anno, mes
    hoy = date.today()
    if hoy.month == 1:
        return hoy.year - 1, 12
    return hoy.year, hoy.month - 1


def en_mes(fecha_str: str, anno: int, mes: int) -> bool:
    return fecha_str[:7] == f"{anno}-{mes:02d}"


def formato_clp(monto: float) -> str:
    return f"${monto:,.0f}".replace(",", ".")


def main():
    anno, mes = mes_objetivo()
    etiqueta_mes = f"{MESES_ES[mes]} de {anno}"
    enviar = "--send" in sys.argv
    print(f"Generando informe de {etiqueta_mes} ({'con envío' if enviar else 'dry-run, sin envío'})...")

    autoridades = {a["id"]: a for a in cargar("autoridades.json")}

    def nombre_de(aid: str) -> str:
        a = autoridades.get(aid)
        return a["nombre_completo"] if a else aid

    # --- resumen de actividad: votaciones/acuerdos, mociones, asistencia ---
    votaciones = cargar("votaciones.json") + cargar("votaciones-camara.json") + cargar("votaciones-core.json")
    votaciones_mes = [v for v in votaciones if en_mes(v["fecha"], anno, mes)]
    aprobadas = sum(1 for v in votaciones_mes if v["resultado"] == "aprobado")
    rechazadas = sum(1 for v in votaciones_mes if v["resultado"] == "rechazado")

    mociones = cargar("mociones.json") + cargar("mociones-senadores.json")
    mociones_mes = [m for m in mociones if en_mes(m["fecha"], anno, mes)]

    asistencia_dip = cargar("asistencia-diputados.json")
    asistencia_mes = [a for a in asistencia_dip if en_mes(a["fecha"], anno, mes)]
    por_autoridad_asis: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for a in asistencia_mes:
        por_autoridad_asis[a["autoridad_id"]][1] += 1
        if a["presente"]:
            por_autoridad_asis[a["autoridad_id"]][0] += 1
    ranking_asistencia = sorted(
        (
            (nombre_de(aid), presentes, total, round(100 * presentes / total))
            for aid, (presentes, total) in por_autoridad_asis.items()
            if total > 0
        ),
        key=lambda x: x[3],
    )

    # --- gasto parlamentario del mes (solo categorías con monto real) ---
    gasto = cargar("gasto-parlamentario.json")
    gasto_mes = [
        g for g in gasto
        if g["anno"] == anno and g["mes"] == mes
        and g["categoria"] in ("gastos_operacionales", "personal_apoyo")
        and g["monto"]
    ]
    gasto_por_autoridad: dict[str, float] = defaultdict(float)
    for g in gasto_mes:
        gasto_por_autoridad[g["autoridad_id"]] += g["monto"]
    ranking_gasto = sorted(gasto_por_autoridad.items(), key=lambda x: -x[1])
    total_gasto_mes = sum(gasto_por_autoridad.values())

    # --- destacados de intervenciones en sala ---
    analisis = cargar("analisis-intervenciones.json")
    clave_mes = f"{anno}-{mes:02d}"
    palabras_mes: dict[str, int] = {}
    if clave_mes in analisis["tendencia"]["meses"]:
        idx = analisis["tendencia"]["meses"].index(clave_mes)
        for palabra in analisis["tendencia"]["palabras"]:
            n = analisis["tendencia"]["serie"][palabra][idx]
            if n > 0:
                palabras_mes[palabra] = n
    palabras_mes_top = sorted(palabras_mes.items(), key=lambda x: -x[1])[:8]

    intervenciones = cargar("intervenciones-sala.json")
    intervenciones_mes = [
        r for r in intervenciones
        if r.get("autoridad_id") and parsear_fecha(r["etiqueta_sesion"]) == (anno, mes)
    ]
    segundos_por_autoridad: dict[str, int] = defaultdict(int)
    for r in intervenciones_mes:
        d = r.get("duracion") or ""
        if ":" in d:
            mm, ss = d.split(":")
            segundos_por_autoridad[r["autoridad_id"]] += int(mm) * 60 + int(ss)
    ranking_tiempo = sorted(segundos_por_autoridad.items(), key=lambda x: -x[1])[:3]

    # --- arma el HTML ---
    html = render_html(
        etiqueta_mes=etiqueta_mes,
        aprobadas=aprobadas,
        rechazadas=rechazadas,
        total_votaciones=len(votaciones_mes),
        mociones_mes=mociones_mes,
        ranking_asistencia=ranking_asistencia,
        total_gasto_mes=total_gasto_mes,
        ranking_gasto=ranking_gasto,
        nombre_de=nombre_de,
        palabras_mes_top=palabras_mes_top,
        ranking_tiempo=[(nombre_de(aid), seg) for aid, seg in ranking_tiempo],
        total_intervenciones_mes=len(intervenciones_mes),
    )

    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    archivo_salida = SALIDA_DIR / f"informe-{anno}-{mes:02d}.html"
    archivo_salida.write_text(html, encoding="utf-8")
    print(f"HTML del informe escrito en {archivo_salida}")

    if enviar:
        enviar_por_mailrelay(etiqueta_mes, html)
    else:
        print("Dry-run: no se llamó a la API de Mailrelay. Agrega --send para enviarlo de verdad.")


def render_html(
    *,
    etiqueta_mes: str,
    aprobadas: int,
    rechazadas: int,
    total_votaciones: int,
    mociones_mes: list[dict],
    ranking_asistencia: list[tuple[str, int, int, int]],
    total_gasto_mes: float,
    ranking_gasto: list[tuple[str, float]],
    nombre_de,
    palabras_mes_top: list[tuple[str, int]],
    ranking_tiempo: list[tuple[str, int]],
    total_intervenciones_mes: int,
) -> str:
    def seccion(titulo: str, contenido: str) -> str:
        return f"""
        <tr><td style="padding:28px 0 10px">
            <h2 style="margin:0;font:700 18px/1.3 -apple-system,Helvetica,Arial,sans-serif;color:#0f172a">{titulo}</h2>
        </td></tr>
        <tr><td style="font:400 14px/1.6 -apple-system,Helvetica,Arial,sans-serif;color:#334155">{contenido}</td></tr>
        """

    # resumen de actividad
    resumen_html = f"""
        <p style="margin:0 0 10px">
            <strong>{total_votaciones}</strong> votaciones/acuerdos registrados
            ({aprobadas} aprobados, {rechazadas} rechazados) ·
            <strong>{len(mociones_mes)}</strong> mociones nuevas presentadas.
        </p>
    """
    if ranking_asistencia:
        peor = ranking_asistencia[:3]
        filas = "".join(
            f'<li style="margin:4px 0">{n} — {pres}/{tot} sesiones ({pct}%)</li>'
            for n, pres, tot, pct in peor
        )
        resumen_html += f"""
        <p style="margin:14px 0 4px"><strong>Menor asistencia del mes (diputados):</strong></p>
        <ul style="margin:0;padding-left:18px">{filas}</ul>
        """

    # gasto
    if ranking_gasto:
        filas_gasto = "".join(
            f'<li style="margin:4px 0">{nombre_de(aid)} — {formato_clp(monto)}</li>'
            for aid, monto in ranking_gasto[:3]
        )
        gasto_html = f"""
        <p style="margin:0 0 10px">
            <strong>{formato_clp(total_gasto_mes)}</strong> en gasto operacional + personal de apoyo
            entre los 7 diputados de la región este mes.
        </p>
        <p style="margin:14px 0 4px"><strong>Mayor gasto del mes:</strong></p>
        <ul style="margin:0;padding-left:18px">{filas_gasto}</ul>
        """
    else:
        gasto_html = """
        <p style="margin:0">
            camara.cl todavía no ha publicado el detalle de gasto de este mes — la publicación
            suele ir con semanas de atraso. Lo incluimos en el próximo informe.
        </p>
        """

    # discursos
    if palabras_mes_top or ranking_tiempo:
        palabras_html = ", ".join(f"<strong>{p}</strong> ({n})" for p, n in palabras_mes_top) or "—"
        tiempo_html = "".join(
            f'<li style="margin:4px 0">{n} — {seg // 60}:{seg % 60:02d} min</li>'
            for n, seg in ranking_tiempo
        )
        discursos_html = f"""
        <p style="margin:0 0 10px">
            <strong>{total_intervenciones_mes}</strong> intervenciones en sala registradas este mes.
            Palabras más repetidas: {palabras_html}.
        </p>
        {'<p style="margin:14px 0 4px"><strong>Quiénes hablaron más tiempo:</strong></p><ul style="margin:0;padding-left:18px">' + tiempo_html + '</ul>' if ranking_tiempo else ''}
        """
    else:
        discursos_html = """
        <p style="margin:0">
            Todavía no hay boletines de sesión publicados por camara.cl para este mes.
        </p>
        """

    return f"""<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#f1f5f9">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 0">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;max-width:600px">
    <tr><td style="background:{COLOR_MARCA};padding:28px 32px">
        <span style="font:700 20px/1 -apple-system,Helvetica,Arial,sans-serif;color:#ffffff">OPRC</span>
        <p style="margin:6px 0 0;font:400 13px/1.4 -apple-system,Helvetica,Arial,sans-serif;color:#fbdcdc">
            Observatorio Político Región de Coquimbo — informe de {etiqueta_mes}
        </p>
    </td></tr>
    <tr><td style="padding:8px 32px 32px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            {seccion("Resumen de actividad", resumen_html)}
            {seccion("Gasto parlamentario del mes", gasto_html)}
            {seccion("Intervenciones en sala", discursos_html)}
        </table>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px">
            <tr><td style="padding-top:20px;border-top:1px solid #e2e8f0">
                <a href="https://oprcoquimbo.cl/" style="display:inline-block;background:{COLOR_MARCA};color:#fff;text-decoration:none;font:700 14px -apple-system,Helvetica,Arial,sans-serif;padding:12px 22px;border-radius:8px">
                    Ver todos los datos →
                </a>
            </td></tr>
        </table>
    </td></tr>
    <tr><td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #e2e8f0">
        <p style="margin:0;font:400 11px/1.6 -apple-system,Helvetica,Arial,sans-serif;color:#94a3b8">
            Recibes este correo porque te suscribiste en oprcoquimbo.cl.
            <a href="{{unsubscribe}}" style="color:#94a3b8">Darse de baja</a>.
        </p>
    </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def enviar_por_mailrelay(etiqueta_mes: str, html: str) -> None:
    api_key = os.environ.get("MAILRELAY_API_KEY")
    if not api_key:
        raise SystemExit("Falta la variable de entorno MAILRELAY_API_KEY.")

    base = f"https://{MAILRELAY_DOMINIO}/api/v1"
    headers = {
        "X-AUTH-TOKEN": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    with httpx.Client(base_url=base, headers=headers, timeout=30) as client:
        # 1) crear la campaña (borrador con el HTML del informe)
        resp = client.post(
            "/campaigns",
            json={
                "subject": f"Informe OPRC — {etiqueta_mes}",
                "from_name": "Observatorio Político Región de Coquimbo",
                "html": html,
            },
        )
        resp.raise_for_status()
        campana = resp.json()
        campana_id = campana.get("id") or campana.get("data", {}).get("id")
        print(f"Campaña creada: id={campana_id}")

        # 2) enviarla al grupo de suscriptores del newsletter
        resp = client.post(
            f"/campaigns/{campana_id}/send_all",
            json={"group_ids": [MAILRELAY_GRUPO_NEWSLETTER]},
        )
        resp.raise_for_status()
        print("Informe enviado vía Mailrelay.")


if __name__ == "__main__":
    main()
