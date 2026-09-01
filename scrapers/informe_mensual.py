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
import re
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
FOTOS_DIR = ROOT / "site" / "public" / "autoridades"
BLOG_DIR = ROOT / "site" / "src" / "content" / "blog"

MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

MAILRELAY_DOMINIO = "oprcoquimbo1.ipzmarketing.com"
MAILRELAY_GRUPO_NEWSLETTER = 1
COLOR_MARCA = "#aa0000"
# mismos colores por tema de dato que usa el sitio (site/src/styles/global.css),
# para que el correo se sienta parte de OPRC y no de una plantilla genérica
COLOR_GASTO = "#e87ba4"
COLOR_DISCURSOS = "#4a3aa7"
COLOR_ASISTENCIA = "#2a78d6"
COLOR_VOTACIONES = "#eb6834"
COLOR_MOCIONES = "#1baf7a"
COLOR_MUNICIPIOS = "#eda100"
# hasta que oprcoquimbo.cl termine el corte al sitio nuevo, las imágenes
# del correo apuntan al dominio de Cloudflare Pages, que ya sirve el sitio
# real (oprcoquimbo.cl todavía redirige al sitio viejo en algunas rutas)
SITE_BASE = "https://oprc-coquimbo.pages.dev"
FUENTE = "-apple-system,Helvetica,Arial,sans-serif"


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


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.split(" ") if p]
    return ((partes[0][0] if partes else "") + (partes[1][0] if len(partes) > 1 else "")).upper()


def foto_url(autoridad_id: str) -> str | None:
    for ext in ("png", "jpg", "jpeg", "webp"):
        if (FOTOS_DIR / f"{autoridad_id}.{ext}").exists():
            return f"{SITE_BASE}/autoridades/{autoridad_id}.{ext}"
    return None


def avatar_html(autoridad_id: str, nombre: str, tam: int = 56) -> str:
    url = foto_url(autoridad_id)
    if url:
        return (
            f'<img src="{url}" width="{tam}" height="{tam}" alt="" '
            f'style="display:block;width:{tam}px;height:{tam}px;border-radius:999px;'
            f'object-fit:cover;border:2px solid #ffffff" />'
        )
    tam_letra = max(12, tam // 3)
    return (
        f'<table role="presentation" width="{tam}" height="{tam}" cellpadding="0" cellspacing="0" '
        f'style="width:{tam}px;height:{tam}px;border-radius:999px;background:#fdf2f2">'
        f'<tr><td align="center" valign="middle" style="font:700 {tam_letra}px {FUENTE};color:{COLOR_MARCA}">'
        f"{iniciales(nombre)}</td></tr></table>"
    )


def posts_del_mes(anno: int, mes: int) -> list[dict]:
    """Entradas del blog publicadas en el mes informado, más recientes primero."""
    posts = []
    for archivo in sorted(BLOG_DIR.glob("*.md")):
        texto = archivo.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---", texto, re.DOTALL)
        if not m:
            continue
        frontmatter = {}
        for linea in m.group(1).splitlines():
            if ":" not in linea:
                continue
            clave, _, valor = linea.partition(":")
            frontmatter[clave.strip()] = valor.strip().strip('"')
        if frontmatter.get("fecha", "")[:7] != f"{anno}-{mes:02d}":
            continue
        posts.append({
            "titulo": frontmatter.get("titulo", ""),
            "resumen": frontmatter.get("resumen", ""),
            "fecha": frontmatter.get("fecha", ""),
            "slug": archivo.stem,
        })
    posts.sort(key=lambda p: p["fecha"], reverse=True)
    return posts


def main():
    anno, mes = mes_objetivo()
    etiqueta_mes = f"{MESES_ES[mes]} de {anno}"
    enviar = "--send" in sys.argv
    print(f"Generando informe de {etiqueta_mes} ({'con envío' if enviar else 'dry-run, sin envío'})...")

    autoridades = {a["id"]: a for a in cargar("autoridades.json")}

    def nombre_de(aid: str) -> str:
        a = autoridades.get(aid)
        return a["nombre_completo"] if a else aid

    # --- diputados: votaciones de la Cámara + mociones propias + asistencia ---
    votaciones_camara_mes = [v for v in cargar("votaciones-camara.json") if en_mes(v["fecha"], anno, mes)]
    mociones_dip_mes = [m for m in cargar("mociones.json") if en_mes(m["fecha"], anno, mes)]

    asistencia_dip = cargar("asistencia-diputados.json")
    asistencia_mes = [a for a in asistencia_dip if en_mes(a["fecha"], anno, mes)]
    por_autoridad_asis: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for a in asistencia_mes:
        por_autoridad_asis[a["autoridad_id"]][1] += 1
        if a["presente"]:
            por_autoridad_asis[a["autoridad_id"]][0] += 1
    ranking_asistencia = sorted(
        (
            (aid, presentes, total, round(100 * presentes / total))
            for aid, (presentes, total) in por_autoridad_asis.items()
            if total > 0
        ),
        key=lambda x: x[3],
    )
    peor_asistencia = ranking_asistencia[0] if ranking_asistencia else None

    # --- gasto parlamentario del mes (solo categorías con monto real; solo hay datos de diputados) ---
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
    mayor_gasto = ranking_gasto[0] if ranking_gasto else None

    # --- intervenciones en sala (solo hay datos de diputados) ---
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
    ranking_tiempo = sorted(segundos_por_autoridad.items(), key=lambda x: -x[1])
    mas_tiempo = ranking_tiempo[0] if ranking_tiempo else None

    # --- senadores: votaciones del Senado + mociones propias ---
    votaciones_senado_mes = [v for v in cargar("votaciones.json") if en_mes(v["fecha"], anno, mes)]
    mociones_senado_mes = [m for m in cargar("mociones-senadores.json") if en_mes(m["fecha"], anno, mes)]
    mociones_por_senador: dict[str, int] = defaultdict(int)
    for m in mociones_senado_mes:
        if m.get("rol") == "autor":
            mociones_por_senador[m["autoridad_id"]] += 1
    ranking_mociones_senado = sorted(mociones_por_senador.items(), key=lambda x: -x[1])
    mas_mociones_senado = ranking_mociones_senado[0] if ranking_mociones_senado else None

    # --- consejo regional: acuerdos del mes + quién de los consejeros participó más ---
    # (se excluye al gobernador: preside todas las sesiones, así que no es un consejero)
    core_ids = {aid for aid, a in autoridades.items() if a["cargo"] == "core"}
    votaciones_core_mes = [v for v in cargar("votaciones-core.json") if en_mes(v["fecha"], anno, mes)]
    aprobados_core = sum(1 for v in votaciones_core_mes if v["resultado"] == "aprobado")
    rechazados_core = sum(1 for v in votaciones_core_mes if v["resultado"] == "rechazado")
    participacion_core: dict[str, int] = defaultdict(int)
    for v in votaciones_core_mes:
        for voto in v["votos"]:
            if voto.get("voto") and voto["autoridad_id"] in core_ids:
                participacion_core[voto["autoridad_id"]] += 1
    ranking_core = sorted(participacion_core.items(), key=lambda x: -x[1])
    mas_participacion_core = ranking_core[0] if ranking_core else None

    # --- municipios: remuneración de alcaldes + cobertura de dotación municipal del mes ---
    alcalde_por_comuna = {a["comuna"]: a["id"] for a in autoridades.values() if a["cargo"] == "alcalde"}
    remun_mes = [
        r for r in cargar("remuneracion-autoridad.json")
        if r["anno"] == anno and r["mes"] == mes
        and "ALCALDE" in r["cargo"].upper() and "SECRETARIA" not in r["cargo"].upper()
    ]
    ranking_remun_alcalde = sorted(remun_mes, key=lambda r: -r["remuneracion_bruta"])
    mayor_remun_alcalde = None
    if ranking_remun_alcalde:
        top = ranking_remun_alcalde[0]
        aid = alcalde_por_comuna.get(top["comuna_id"])
        if aid:
            mayor_remun_alcalde = (nombre_de(aid), aid, top["remuneracion_bruta"])

    personal_mes = [
        r for r in cargar("personal-municipal.json")
        if r["anno"] == anno and r["mes"] == mes and r["area"] == "municipal"
    ]
    total_comunas_personal = len({r["comuna_id"] for r in personal_mes})

    # --- investigaciones publicadas este mes ---
    posts_mes = posts_del_mes(anno, mes)

    # --- "resumen del mes": el número más concreto y citable que tengamos ---
    total_votaciones_mes = len(votaciones_camara_mes) + len(votaciones_senado_mes) + len(votaciones_core_mes)
    if total_gasto_mes > 0:
        dato_valor = formato_clp(total_gasto_mes)
        dato_contexto = "en gasto operacional + personal de apoyo, entre los 7 diputados de la región."
    elif total_votaciones_mes > 0:
        dato_valor = str(total_votaciones_mes)
        dato_contexto = "votaciones y acuerdos registrados este mes, entre Cámara, Senado y Consejo Regional."
    else:
        dato_valor = "—"
        dato_contexto = "Todavía no hay datos suficientes de este mes para destacar un número."

    html = render_html(
        etiqueta_mes=etiqueta_mes,
        dato_valor=dato_valor,
        dato_contexto=dato_contexto,
        posts_mes=posts_mes,
        total_votaciones_camara=len(votaciones_camara_mes),
        total_mociones_dip=len(mociones_dip_mes),
        mayor_gasto=(nombre_de(mayor_gasto[0]), mayor_gasto[0], mayor_gasto[1]) if mayor_gasto else None,
        mas_tiempo=(nombre_de(mas_tiempo[0]), mas_tiempo[0], mas_tiempo[1]) if mas_tiempo else None,
        peor_asistencia=(
            (nombre_de(peor_asistencia[0]), peor_asistencia[0], peor_asistencia[3])
            if peor_asistencia else None
        ),
        palabras_mes_top=palabras_mes_top,
        total_votaciones_senado=len(votaciones_senado_mes),
        total_mociones_senado=len(mociones_senado_mes),
        mas_mociones_senado=(
            (nombre_de(mas_mociones_senado[0]), mas_mociones_senado[0], mas_mociones_senado[1])
            if mas_mociones_senado else None
        ),
        total_acuerdos_core=len(votaciones_core_mes),
        aprobados_core=aprobados_core,
        rechazados_core=rechazados_core,
        mas_participacion_core=(
            (nombre_de(mas_participacion_core[0]), mas_participacion_core[0], mas_participacion_core[1])
            if mas_participacion_core else None
        ),
        total_comunas_personal=total_comunas_personal,
        mayor_remun_alcalde=mayor_remun_alcalde,
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
    dato_valor: str,
    dato_contexto: str,
    posts_mes: list[dict],
    total_votaciones_camara: int,
    total_mociones_dip: int,
    mayor_gasto: tuple[str, str, float] | None,
    mas_tiempo: tuple[str, str, int] | None,
    peor_asistencia: tuple[str, str, int] | None,
    palabras_mes_top: list[tuple[str, int]],
    total_votaciones_senado: int,
    total_mociones_senado: int,
    mas_mociones_senado: tuple[str, str, int] | None,
    total_acuerdos_core: int,
    aprobados_core: int,
    rechazados_core: int,
    mas_participacion_core: tuple[str, str, int] | None,
    total_comunas_personal: int,
    mayor_remun_alcalde: tuple[str, str, float] | None,
) -> str:
    def titulo_seccion(color: str, texto: str) -> str:
        return f"""
        <tr><td style="padding:30px 0 6px">
            <p style="margin:0;font:700 17px/1.3 {FUENTE};color:#0f172a">
                <span style="display:inline-block;width:9px;height:9px;border-radius:999px;background:{color};margin-right:9px"></span>{texto}
            </p>
        </td></tr>
        """

    def pill(color: str, texto: str) -> str:
        return (
            f'<span style="display:inline-block;background:{color};color:#ffffff;'
            f'font:700 10px {FUENTE};letter-spacing:.04em;padding:3px 9px;border-radius:999px">{texto.upper()}</span>'
        )

    def chip(texto: str) -> str:
        return (
            f'<span style="display:inline-block;background:#f1f5f9;color:#475569;'
            f'font:600 12px {FUENTE};padding:4px 10px;border-radius:999px;margin:0 6px 6px 0">{texto}</span>'
        )

    def spotlight(autoridad_id: str, nombre: str, rol: str, metrica: str, color: str, etiqueta: str) -> str:
        return f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px">
            <tr>
                <td width="56" valign="top">{avatar_html(autoridad_id, nombre)}</td>
                <td style="padding-left:14px" valign="middle">
                    <p style="margin:0 0 5px">{pill(color, etiqueta)}</p>
                    <p style="margin:0;font:700 14px {FUENTE};color:#0f172a">{nombre}</p>
                    <p style="margin:2px 0 0;font:400 13px {FUENTE};color:#64748b">{rol}</p>
                    <p style="margin:4px 0 0;font:700 14px {FUENTE};color:{color}">{metrica}</p>
                </td>
            </tr>
        </table>
        """

    # investigaciones publicadas este mes
    seccion_posts = ""
    if posts_mes:
        posts_html = ""
        for i, p in enumerate(posts_mes):
            resumen = p["resumen"]
            if len(resumen) > 180:
                resumen = resumen[:177].rsplit(" ", 1)[0] + "…"
            posts_html += f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fdf2f2;border-radius:10px;margin-top:{0 if i == 0 else 14}px">
                <tr><td style="padding:20px 22px">
                    <p style="margin:0 0 8px">{pill(COLOR_MARCA, "Nueva investigación")}</p>
                    <p style="margin:0;font:700 15px/1.4 {FUENTE};color:#0f172a">{p["titulo"]}</p>
                    <p style="margin:8px 0 0;font:400 13px/1.6 {FUENTE};color:#475569">{resumen}</p>
                    <p style="margin:12px 0 0">
                        <a href="{SITE_BASE}/blog/{p["slug"]}/" style="color:{COLOR_MARCA};font:700 13px {FUENTE};text-decoration:none">Leer el artículo →</a>
                    </p>
                </td></tr>
            </table>
            """
        titulo_posts = "Nueva investigación" if len(posts_mes) == 1 else "Nuevas investigaciones"
        seccion_posts = f"""
        {titulo_seccion(COLOR_MARCA, titulo_posts)}
        <tr><td>{posts_html}</td></tr>
        """

    # diputados
    diputados_html = f"""
        <p style="margin:0 0 4px;font:400 14px/1.6 {FUENTE};color:#334155">
            <strong>{total_votaciones_camara}</strong> votaciones registradas en la Cámara ·
            <strong>{total_mociones_dip}</strong> mociones nuevas presentadas este mes.
        </p>
    """
    if mayor_gasto:
        nombre, aid, monto = mayor_gasto
        diputados_html += spotlight(aid, nombre, "Mayor gasto del mes", formato_clp(monto), COLOR_GASTO, "Gasto")
    if mas_tiempo:
        nombre, aid, seg = mas_tiempo
        diputados_html += spotlight(
            aid, nombre, "Más tiempo hablado en sala", f"{seg // 60}:{seg % 60:02d} min", COLOR_DISCURSOS, "Sala"
        )
    if peor_asistencia:
        nombre, aid, pct = peor_asistencia
        diputados_html += spotlight(
            aid, nombre, "Menor asistencia del mes", f"{pct}%", COLOR_ASISTENCIA, "Asistencia"
        )
    if palabras_mes_top:
        palabras_html = "".join(chip(f"{p} · {n}") for p, n in palabras_mes_top)
        diputados_html += f"""
        <p style="margin:22px 0 8px;font:600 12px {FUENTE};color:#94a3b8;letter-spacing:.03em">
            PALABRAS MÁS REPETIDAS EN SALA
        </p>
        <div>{palabras_html}</div>
        """

    # senadores
    if total_votaciones_senado > 0 or total_mociones_senado > 0:
        senadores_html = f"""
        <p style="margin:0 0 4px;font:400 14px/1.6 {FUENTE};color:#334155">
            <strong>{total_votaciones_senado}</strong> votaciones registradas en el Senado ·
            <strong>{total_mociones_senado}</strong> mociones nuevas presentadas este mes.
        </p>
        """
        if mas_mociones_senado:
            nombre, aid, n = mas_mociones_senado
            senadores_html += spotlight(
                aid, nombre, "Autor de más mociones este mes", f"{n} mociones", COLOR_MOCIONES, "Mociones"
            )
    else:
        senadores_html = f"""
        <p style="margin:0;font:400 14px/1.6 {FUENTE};color:#334155">
            Sin actividad del Senado registrada este mes.
        </p>
        """

    # consejo regional
    if total_acuerdos_core > 0:
        core_html = f"""
        <p style="margin:0;font:400 14px/1.6 {FUENTE};color:#334155">
            <strong>{total_acuerdos_core}</strong> acuerdos del Consejo Regional este mes
            ({aprobados_core} aprobados, {rechazados_core} rechazados).
        </p>
        """
        if mas_participacion_core:
            nombre, aid, n = mas_participacion_core
            core_html += spotlight(
                aid, nombre, "Consejero(a) con más participación", f"{n} votos emitidos", COLOR_VOTACIONES, "Core"
            )
    else:
        core_html = f"""
        <p style="margin:0;font:400 14px/1.6 {FUENTE};color:#334155">
            Sin acuerdos del Consejo Regional registrados este mes.
        </p>
        """

    # municipios
    if total_comunas_personal > 0 or mayor_remun_alcalde:
        municipios_html = f"""
        <p style="margin:0 0 4px;font:400 14px/1.6 {FUENTE};color:#334155">
            <strong>{total_comunas_personal}</strong> de 15 comunas reportaron su dotación municipal este mes.
        </p>
        """
        if mayor_remun_alcalde:
            nombre, aid, monto = mayor_remun_alcalde
            municipios_html += spotlight(
                aid, nombre, "Alcalde/sa con mayor remuneración bruta", formato_clp(monto), COLOR_GASTO, "Gasto"
            )
    else:
        municipios_html = f"""
        <p style="margin:0;font:400 14px/1.6 {FUENTE};color:#334155">
            Sin datos municipales publicados todavía para este mes.
        </p>
        """

    return f"""<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#e2e8f0">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e2e8f0;padding:28px 0">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;max-width:600px">

    <tr><td style="background:{COLOR_MARCA};padding:32px" align="center">
        <img src="{SITE_BASE}/logo-oprc-blanco.png" alt="OPRC" width="150" style="display:block;width:150px;height:auto;margin:0 auto" />
        <p style="margin:14px 0 0;font:400 13px {FUENTE};color:#fbdcdc">
            Informe mensual · {etiqueta_mes}
        </p>
        <p style="margin:6px 0 0;font:400 11px/1.4 {FUENTE};color:#f5b3b3">
            Se publica con los datos disponibles a esta fecha — algunas fuentes todavía están completando su historial.
        </p>
    </td></tr>

    <tr><td style="padding:24px 32px 32px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">

            {seccion_posts}

            <tr><td style="padding:0 0 28px">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fdf2f2;border-radius:10px">
                    <tr><td style="padding:22px 24px">
                        <p style="margin:0 0 8px">
                            <span style="display:inline-block;background:{COLOR_MARCA};color:#ffffff;font:700 10px {FUENTE};letter-spacing:.04em;padding:3px 9px;border-radius:999px">RESUMEN DEL MES</span>
                        </p>
                        <p style="margin:0;font:800 38px/1.1 {FUENTE};color:{COLOR_MARCA}">{dato_valor}</p>
                        <p style="margin:8px 0 0;font:400 14px/1.5 {FUENTE};color:#475569">{dato_contexto}</p>
                    </td></tr>
                </table>
            </td></tr>

            {titulo_seccion(COLOR_DISCURSOS, "Diputados")}
            <tr><td>{diputados_html}</td></tr>

            {titulo_seccion(COLOR_MOCIONES, "Senadores")}
            <tr><td>{senadores_html}</td></tr>

            {titulo_seccion(COLOR_VOTACIONES, "Consejo Regional")}
            <tr><td>{core_html}</td></tr>

            {titulo_seccion(COLOR_MUNICIPIOS, "Municipios")}
            <tr><td>{municipios_html}</td></tr>

        </table>

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;border-top:1px solid #e2e8f0">
            <tr><td style="padding-top:20px" align="center">
                <p style="margin:0 0 14px;font:400 12px {FUENTE};color:#94a3b8">
                    Concejales: sumaremos comparativos por comuna cuando terminemos de reunir sus fotos.
                </p>
                <a href="{SITE_BASE}/" style="display:inline-block;background:{COLOR_MARCA};color:#fff;text-decoration:none;font:700 14px {FUENTE};padding:12px 24px;border-radius:8px">
                    Ver todos los datos →
                </a>
            </td></tr>
        </table>
    </td></tr>

    <tr><td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #e2e8f0">
        <p style="margin:0;font:400 11px/1.6 {FUENTE};color:#94a3b8">
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
