"""Análisis de texto de las intervenciones en sala de los 7 diputados de la
región: palabras más usadas, tendencia mensual, coocurrencia. Consume
data/processed/intervenciones-sala.json (scrapers/intervenciones_sala.py) y
genera data/processed/analisis-intervenciones.json — no vuelve a tocar la
red, es puro procesamiento de texto sobre lo ya guardado.
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

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

# ruido específico del formato de las transcripciones de sala (tratamientos,
# procedimiento parlamentario) — no son "palabras vacías" en general, pero
# aquí serían solo ruido protocolar en cada intervención sin excepción
STOPWORDS_SALA = set("""
señor señora señorita presidente presidenta diputado diputada diputados diputadas
honorable camara gracias aplausos favor votos abstenciones colegas colega ministro
ministra secretario general votar votacion sala tiene palabra ofrezco muchas gran
dicho
""".split())

TODAS_STOPWORDS = STOPWORDS | STOPWORDS_SALA


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


def parsear_fecha(etiqueta: str) -> tuple[int, int] | None:
    """'31ª, martes 9 junio 2026' -> (2026, 6)"""
    m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", etiqueta)
    if not m:
        return None
    mes = MESES_ES.get(_sin_tildes(m.group(2).lower()))
    if not mes:
        return None
    return int(m.group(3)), mes


def main():
    with open(PROCESSED_DIR / "intervenciones-sala.json") as f:
        registros = json.load(f)

    con_texto = [r for r in registros if r.get("texto")]

    # --- palabras más usadas: por diputado y agregado ---
    conteo_por_autoridad: dict[str, Counter] = defaultdict(Counter)
    conteo_total: Counter = Counter()
    for r in con_texto:
        tokens = tokenizar(r["texto"])
        conteo_por_autoridad[r["autoridad_id"]].update(tokens)
        conteo_total.update(tokens)

    top_palabras_por_autoridad = {
        aid: [{"palabra": p, "n": n} for p, n in c.most_common(40)]
        for aid, c in conteo_por_autoridad.items()
    }
    top_palabras_total = [{"palabra": p, "n": n} for p, n in conteo_total.most_common(60)]

    # --- tendencia mensual: de las palabras más usadas en total, su
    # frecuencia mes a mes (para graficar evolución) ---
    palabras_seguidas = [p for p, _ in conteo_total.most_common(15)]
    conteo_por_mes: dict[str, Counter] = defaultdict(Counter)
    for r in con_texto:
        fecha = parsear_fecha(r["etiqueta_sesion"])
        if not fecha:
            continue
        clave_mes = f"{fecha[0]}-{fecha[1]:02d}"
        tokens = tokenizar(r["texto"])
        conteo_por_mes[clave_mes].update(t for t in tokens if t in palabras_seguidas)

    meses_ordenados = sorted(conteo_por_mes.keys())
    tendencia = {
        "meses": meses_ordenados,
        "palabras": palabras_seguidas,
        "serie": {
            palabra: [conteo_por_mes[mes].get(palabra, 0) for mes in meses_ordenados]
            for palabra in palabras_seguidas
        },
    }

    # --- coocurrencia: de las top-25 palabras totales, cuántas veces
    # aparecen juntas en una misma intervención ---
    top_25 = set(p for p, _ in conteo_total.most_common(25))
    pares: Counter = Counter()
    for r in con_texto:
        presentes = set(t for t in tokenizar(r["texto"]) if t in top_25)
        for a, b in combinations(sorted(presentes), 2):
            pares[(a, b)] += 1

    coocurrencia = {
        "nodos": [{"palabra": p, "n": conteo_total[p]} for p in top_25],
        "enlaces": [
            {"a": a, "b": b, "peso": peso} for (a, b), peso in pares.items() if peso >= 2
        ],
    }

    # --- participación: tiempo hablado y cantidad, desde la tabla
    # estructurada (no depende de si se pudo extraer el texto del PDF) ---
    def duracion_a_segundos(d: str | None) -> int:
        if not d or ":" not in d:
            return 0
        mm, ss = d.split(":")
        return int(mm) * 60 + int(ss)

    def _fila_vacia():
        return {"intervenciones": 0, "segundos": 0, "con_texto": 0}

    participacion: dict[str, dict] = defaultdict(_fila_vacia)
    for r in registros:
        p = participacion[r["autoridad_id"]]
        p["intervenciones"] += 1
        p["segundos"] += duracion_a_segundos(r.get("duracion"))
        if r.get("texto"):
            p["con_texto"] += 1

    salida = {
        "top_palabras_por_autoridad": top_palabras_por_autoridad,
        "top_palabras_total": top_palabras_total,
        "tendencia": tendencia,
        "coocurrencia": coocurrencia,
        "participacion": dict(participacion),
        "total_intervenciones": len(registros),
        "total_con_texto": len(con_texto),
        "total_palabras_corpus": sum(len(tokenizar(r["texto"])) for r in con_texto),
    }

    with open(PROCESSED_DIR / "analisis-intervenciones.json", "w") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"Análisis exportado a {PROCESSED_DIR / 'analisis-intervenciones.json'}")
    print(f"  {len(con_texto)} intervenciones con texto, "
          f"{salida['total_palabras_corpus']} palabras útiles")


if __name__ == "__main__":
    main()
