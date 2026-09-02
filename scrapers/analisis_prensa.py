"""Fase 3 de análisis de prensa regional — palabras más usadas, tendencia
semanal, coocurrencia, y menciones de autoridades/comunas.

Lee directo de la base de datos (`prensa_articulo.texto_completo`) —
nunca desde un JSON, porque el texto completo nunca se exporta (ver
docs/06-bitacora.md, decisión de analizar sin republicar). El archivo de
salida solo contiene estadísticas derivadas: nubes/listas de palabras,
series de tendencia, pares de coocurrencia y conteos de menciones — en
ningún punto se copia el texto de un artículo al JSON público.

No vuelve a tocar la red — es puro procesamiento de texto sobre lo ya
guardado por prensa_rss.py y prensa_texto.py.

Uso: python scrapers/analisis_prensa.py
"""

import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "db" / "oprc.sqlite"
PROCESSED_DIR = ROOT / "data" / "processed"

# misma lista general que analisis_intervenciones.py — palabras
# gramaticales sin carga informativa, independiente del tipo de texto
STOPWORDS = set("""
de la que el en y a los del se las por un para con no una su al es lo como más pero
sus le ya o este sí porque esta son entre cuando muy sin sobre ser tiene también me
hasta hay donde quien desde todo nos durante todos uno les ni contra otros ese eso
ante ellos e esto mi antes algunos que unos yo otro otras otra él tanto esa estos
mucho quienes nada muchos cual poco ella estar estas algunas algo nosotros mis tu
tus ellas nosotras vosotros vosotras os mio mia mios mias tuyo tuya tuyos tuyas
suyo suya suyos suyas nuestro nuestra nuestros nuestras vuestro vuestra vuestros
vuestras esos esas estoy estas esta estamos estais estan este estes estemos esteis
esten estare estaras estara estaremos estareis estaran estaria estarias estariamos
estariais estarian estaba estabas estabamos estabais estaban estuve estuviste estuvo
estuvimos estuvisteis estuvieron estuviera estuvieras estuvieramos estuvierais
estuvieran estuviese estuvieses estuviesemos estuvieseis estuviesen estando estado
estada estados estadas estad he has ha hemos habeis han haya hayas hayamos hayais
hayan habia habias habiamos habiais habian hube hubiste hubo hubimos hubisteis
hubieron hubiera hubieras hubieramos hubierais hubieran hubiese hubieses hubiesemos
hubieseis hubiesen habiendo habido habida habidos habidas soy eres somos sois sean
sea seas seamos seais fui fuiste fue fuimos fuisteis fueron fuera fueras fueramos
fuerais fueran fuese fueses fuesemos fueseis fuesen siendo sido tengo tienes tenemos
teneis tienen tenga tengas tengamos tengais tengan tenia tenias teniamos teniais
tenian tuve tuviste tuvo tuvimos tuvisteis tuvieron tuviera tuvieras tuvieramos
tuvierais tuvieran tuviese tuvieses tuviesemos tuvieseis tuviesen teniendo tenido
tenida tenidos tenidas asi solo aqui alli aca ahi bien mas dos cada cada tan tal
segun bajo cabe hacia mediante durante mientras aunque pues pese vez veces respecto
""".split())

# ruido propio del lenguaje periodístico — verbos de atribución y
# fórmulas que dominarían la frecuencia sin aportar información real,
# análogo a STOPWORDS_SALA para las transcripciones de sala
STOPWORDS_PRENSA = set("""
señalo indico declaro afirmo informo explico agrego destaco comento
manifesto sostuvo aseguro detallo preciso segun indica cabe recordar
noticia region comunas municipalidad municipio comuna año años
""".split())

TODAS_STOPWORDS = STOPWORDS | STOPWORDS_PRENSA


def _sin_tildes(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def tokenizar(texto: str) -> list[str]:
    palabras = re.findall(r"[a-záéíóúñA-ZÁÉÍÓÚÑ]+", texto.lower())
    resultado = []
    for p in palabras:
        if len(p) < 4:
            continue
        p_plana = _sin_tildes(p)
        if p_plana in TODAS_STOPWORDS or p in TODAS_STOPWORDS:
            continue
        resultado.append(p)
    return resultado


def _semana_iso(fecha_iso: str) -> str:
    """'2026-08-31T13:57:20+00:00' -> '2026-W35'."""
    d = date.fromisoformat(fecha_iso[:10])
    anno, semana, _ = d.isocalendar()
    return f"{anno}-W{semana:02d}"


def _normalizar(s: str) -> str:
    return re.sub(r"\s+", " ", _sin_tildes(s).lower()).strip()


def main():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    con_texto = db.execute(
        """
        SELECT fuente, comuna_id, titulo, fecha, texto_completo
        FROM prensa_articulo WHERE texto_completo IS NOT NULL
        """
    ).fetchall()

    # --- palabras más usadas: por medio y agregado ---
    conteo_por_medio: dict[str, Counter] = defaultdict(Counter)
    conteo_total: Counter = Counter()
    for r in con_texto:
        tokens = tokenizar(r["texto_completo"])
        conteo_por_medio[r["fuente"]].update(tokens)
        conteo_total.update(tokens)

    top_palabras_por_medio = {
        medio: [{"palabra": p, "n": n} for p, n in c.most_common(40)]
        for medio, c in conteo_por_medio.items()
    }
    top_palabras_total = [{"palabra": p, "n": n} for p, n in conteo_total.most_common(60)]

    # --- tendencia semanal: de las palabras más usadas en total, su
    # frecuencia semana a semana (la prensa cambia más rápido que las
    # sesiones parlamentarias, por eso semanal en vez de mensual) ---
    palabras_seguidas = [p for p, _ in conteo_total.most_common(15)]
    conteo_por_semana: dict[str, Counter] = defaultdict(Counter)
    for r in con_texto:
        semana = _semana_iso(r["fecha"])
        tokens = tokenizar(r["texto_completo"])
        conteo_por_semana[semana].update(t for t in tokens if t in palabras_seguidas)

    semanas_ordenadas = sorted(conteo_por_semana.keys())
    tendencia = {
        "semanas": semanas_ordenadas,
        "palabras": palabras_seguidas,
        "serie": {
            palabra: [conteo_por_semana[s].get(palabra, 0) for s in semanas_ordenadas]
            for palabra in palabras_seguidas
        },
    }

    # --- coocurrencia: de las top-25 palabras totales, cuántas veces
    # aparecen juntas en un mismo artículo ---
    top_25 = set(p for p, _ in conteo_total.most_common(25))
    pares: Counter = Counter()
    for r in con_texto:
        presentes = set(t for t in tokenizar(r["texto_completo"]) if t in top_25)
        for a, b in combinations(sorted(presentes), 2):
            pares[(a, b)] += 1

    coocurrencia = {
        "nodos": [{"palabra": p, "n": conteo_total[p]} for p in top_25],
        "enlaces": [
            {"a": a, "b": b, "peso": peso} for (a, b), peso in pares.items() if peso >= 2
        ],
    }

    # --- nube por semana: no reutiliza las 15 "palabras seguidas" de la
    # tendencia — cada semana tiene su propio top, para que la nube
    # muestre lo que realmente dominó esa semana en particular ---
    conteo_por_semana_todas: dict[str, Counter] = defaultdict(Counter)
    for r in con_texto:
        semana = _semana_iso(r["fecha"])
        conteo_por_semana_todas[semana].update(tokenizar(r["texto_completo"]))

    top_palabras_por_semana = {
        s: [{"palabra": p, "n": n} for p, n in c.most_common(30)]
        for s, c in conteo_por_semana_todas.items()
    }

    # --- tendencia por medio: de las mismas 15 palabras seguidas de la
    # tendencia, su frecuencia semana a semana separada por medio —
    # alimenta tanto el desglose por medio de una semana (barras
    # apiladas) como el seguimiento de un concepto elegido comparando
    # medios (ambos se pueden recortar de la misma matriz semana×medio) ---
    conteo_semana_medio: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in con_texto:
        semana = _semana_iso(r["fecha"])
        tokens = tokenizar(r["texto_completo"])
        clave = (semana, r["fuente"])
        conteo_semana_medio[clave].update(t for t in tokens if t in palabras_seguidas)

    tendencia_por_medio = {}
    for palabra in palabras_seguidas:
        medios_con_palabra = sorted(
            {
                medio
                for (_s, medio), c in conteo_semana_medio.items()
                if c.get(palabra, 0) > 0
            }
        )
        tendencia_por_medio[palabra] = {
            "medios": medios_con_palabra,
            "serie": {
                medio: [
                    conteo_semana_medio.get((s, medio), Counter()).get(palabra, 0)
                    for s in semanas_ordenadas
                ]
                for medio in medios_con_palabra
            },
        }

    # --- menciones por autoridad: la prensa casi nunca escribe el nombre
    # completo de 4 partes que usamos como identificador ("Juan Carlos
    # Alfaro Aravena") — escribe "el alcalde Juan Alfaro" o solo
    # "Alfaro". Buscar solo el nombre completo exacto dejaba a solo 6 de
    # 142 autoridades activas con alguna mención en 291 artículos
    # (bug real, detectado por el usuario al ver conteos de 1). Se
    # agrega un "nombre corto" (primer nombre + apellido paterno, el
    # segundo-a-último token del nombre completo) como alternativa de
    # búsqueda — pero solo cuando ese nombre corto identifica a una sola
    # autoridad activa; si dos autoridades comparten primer nombre +
    # apellido paterno (2 casos de 142: "Denis Cortés", "Juan
    # Castillo"), esas quedan con el nombre completo exacto nomás, para
    # no confundir personas ---
    with open(PROCESSED_DIR / "autoridades.json", encoding="utf-8") as f:
        autoridades = json.load(f)

    textos_normalizados = [
        (r, _normalizar(f"{r['titulo']} {r['texto_completo']}")) for r in con_texto
    ]

    def _nombre_corto(nombre_completo: str) -> str | None:
        tokens = nombre_completo.split()
        if len(tokens) < 2:
            return None
        apellido_paterno = tokens[-2] if len(tokens) >= 3 else tokens[-1]
        return _normalizar(f"{tokens[0]} {apellido_paterno}")

    activas = [
        a for a in autoridades if a.get("activo") and a.get("nombre_completo")
    ]
    conteo_nombres_cortos: Counter = Counter(
        c for a in activas if (c := _nombre_corto(a["nombre_completo"]))
    )

    menciones_autoridad: Counter = Counter()
    for a in activas:
        nombre_norm = _normalizar(a["nombre_completo"])
        if len(nombre_norm.split()) < 2:
            continue
        corto = _nombre_corto(a["nombre_completo"])
        usa_corto = corto is not None and conteo_nombres_cortos[corto] == 1
        for _r, texto_norm in textos_normalizados:
            if nombre_norm in texto_norm or (usa_corto and corto in texto_norm):
                menciones_autoridad[a["id"]] += 1

    menciones_por_autoridad = [
        {"autoridad_id": aid, "n": n}
        for aid, n in menciones_autoridad.most_common()
        if n > 0
    ]

    # --- menciones por comuna: nombre de la comuna como substring, sobre
    # TODOS los artículos (no solo los de medios comunales con comuna_id
    # asignado) — así los medios regionales externos también aportan ---
    with open(PROCESSED_DIR / "comunas.json", encoding="utf-8") as f:
        comunas = json.load(f)

    menciones_comuna: Counter = Counter()
    for c in comunas:
        nombre_norm = _normalizar(c["nombre"])
        for _r, texto_norm in textos_normalizados:
            if nombre_norm in texto_norm:
                menciones_comuna[c["id"]] += 1

    menciones_por_comuna = [
        {"comuna_id": cid, "n": n} for cid, n in menciones_comuna.most_common() if n > 0
    ]

    salida = {
        "top_palabras_por_medio": top_palabras_por_medio,
        "top_palabras_total": top_palabras_total,
        "top_palabras_por_semana": top_palabras_por_semana,
        "tendencia": tendencia,
        "tendencia_por_medio": tendencia_por_medio,
        "coocurrencia": coocurrencia,
        "menciones_por_autoridad": menciones_por_autoridad,
        "menciones_por_comuna": menciones_por_comuna,
        "total_articulos": len(con_texto),
        "total_palabras_corpus": sum(len(tokenizar(r["texto_completo"])) for r in con_texto),
    }

    with open(PROCESSED_DIR / "analisis-prensa.json", "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"Análisis exportado a {PROCESSED_DIR / 'analisis-prensa.json'}")
    print(f"  {len(con_texto)} artículos, {salida['total_palabras_corpus']} palabras útiles")


if __name__ == "__main__":
    main()
