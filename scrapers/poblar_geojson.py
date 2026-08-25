"""Puebla comuna.geojson con los límites administrativos reales de las 15
comunas, vía OpenStreetMap (Nominatim) — datos abiertos bajo licencia ODbL.

No es un scraper semanal: los límites administrativos no cambian, así que
esto se corre una sola vez (o cuando haga falta volver a generar el mapa),
igual que poblar_catalogo.py con los CSV maestros.

Respeta la política de uso de Nominatim (nominatim.org/release-docs/latest/api/Usage-Policy/):
máximo 1 request/segundo, User-Agent identificable con contacto.

Uso: python scrapers/poblar_geojson.py
"""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "db" / "oprc.sqlite"
PROCESSED_DIR = ROOT / "data" / "processed"

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
HEADERS = {"User-Agent": "OPRC-Coquimbo-Observatorio/1.0 (contacto@oprcoquimbo.cl)"}

# tolerancia de Douglas-Peucker en grados (~110m) — de sobra para un mapa
# regional a escala de comuna, reduce el tamaño del GeoJSON entre 10-30x
TOLERANCIA_SIMPLIFICACION = 0.001


def _distancia_punto_segmento(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    proyeccion = (ax + t * dx, ay + t * dy)
    return ((px - proyeccion[0]) ** 2 + (py - proyeccion[1]) ** 2) ** 0.5


def _douglas_peucker(puntos: list, tolerancia: float) -> list:
    if len(puntos) < 3:
        return puntos
    dmax, idx = 0.0, 0
    for i in range(1, len(puntos) - 1):
        d = _distancia_punto_segmento(puntos[i], puntos[0], puntos[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > tolerancia:
        izq = _douglas_peucker(puntos[: idx + 1], tolerancia)
        der = _douglas_peucker(puntos[idx:], tolerancia)
        return izq[:-1] + der
    return [puntos[0], puntos[-1]]


def _simplificar_anillo(anillo: list) -> list:
    simplificado = _douglas_peucker(anillo, TOLERANCIA_SIMPLIFICACION)
    return [[round(x, 5), round(y, 5)] for x, y in simplificado]


def _simplificar_geometria(geojson: dict) -> dict:
    if geojson["type"] == "Polygon":
        geojson["coordinates"] = [_simplificar_anillo(anillo) for anillo in geojson["coordinates"]]
    elif geojson["type"] == "MultiPolygon":
        geojson["coordinates"] = [
            [_simplificar_anillo(anillo) for anillo in poligono]
            for poligono in geojson["coordinates"]
        ]
    return geojson


def _buscar_geometria(client: httpx.Client, nombre_comuna: str) -> dict | None:
    resp = client.get(
        f"{NOMINATIM_BASE}/search",
        params={"q": f"{nombre_comuna}, Región de Coquimbo, Chile", "format": "json", "limit": 5},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    candidatos = [r for r in resp.json() if r.get("osm_type") == "relation"]
    if not candidatos:
        return None
    osm_id = candidatos[0]["osm_id"]
    time.sleep(1.1)

    resp = client.get(
        f"{NOMINATIM_BASE}/lookup",
        params={"osm_ids": f"R{osm_id}", "format": "json", "polygon_geojson": 1},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    datos = resp.json()
    if not datos:
        return None
    return datos[0]["geojson"]


def main() -> None:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    comunas = db.execute("SELECT id, nombre FROM comuna ORDER BY nombre").fetchall()

    ahora = datetime.now().isoformat()
    features = []
    with httpx.Client() as client:
        for comuna in comunas:
            try:
                geometria = _buscar_geometria(client, comuna["nombre"])
            except Exception as e:
                print(f"[{comuna['id']}] ERROR: {e}")
                continue
            time.sleep(1.1)

            if geometria is None:
                print(f"[{comuna['id']}] sin geometría encontrada")
                continue

            antes = len(json.dumps(geometria))
            geometria = _simplificar_geometria(geometria)
            despues = len(json.dumps(geometria))
            print(f"[{comuna['id']}] {antes // 1024}KB -> {despues // 1024}KB")

            geojson_str = json.dumps(geometria, ensure_ascii=False)
            db.execute(
                "UPDATE comuna SET geojson = ?, actualizado_en = ? WHERE id = ?",
                (geojson_str, ahora, comuna["id"]),
            )
            features.append(
                {
                    "type": "Feature",
                    "properties": {"id": comuna["id"], "nombre": comuna["nombre"]},
                    "geometry": geometria,
                }
            )

    db.commit()
    db.close()

    coleccion = {"type": "FeatureCollection", "features": features}
    (PROCESSED_DIR / "comunas-geojson.json").write_text(
        json.dumps(coleccion, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n{len(features)}/{len(comunas)} comunas con geometría")
    print("Exportado a comunas-geojson.json")


if __name__ == "__main__":
    main()
