"""Fase 2 de análisis de prensa regional — texto completo de cada noticia.

Recorre las filas de `prensa_articulo` con `texto_completo IS NULL`,
visita la página real y extrae el cuerpo del artículo. El texto se usa
SOLO para calcular estadísticas (nube de palabras, tendencias,
co-ocurrencia) — nunca se expone públicamente. Por eso `exportar_json()`
no hace nada: este scraper escribe únicamente en la base de datos, nunca
en un JSON que el sitio pueda servir. Es la misma decisión de "analizar
sin republicar" que la Fase 1, pero aplicada estructuralmente, no solo
como política — no existe ningún camino de código que saque el texto
completo de la BD hacia afuera.

Extracción genérica con selectores en cascada, porque los 28 sitios no
comparten plantilla (varios WordPress con temas distintos, El
Observatodo parece Drupal). Probado manualmente contra 5 sitios
representativos el 2026-09-02: `<article>` funciona en la mayoría, pero
El Ovallino tiene una clase más precisa (`td-post-content`, tema
"Newspaper" de tagDiv) y El Observatodo no tiene `<article>` en absoluto
(usa `class="content content-node"`, típico de Drupal).
"""

import re
import sqlite3
import time
from datetime import datetime

from base import BaseScraper
from bs4 import BeautifulSoup

SLEEP_ENTRE_PETICIONES = 1.5
LOTE_MAXIMO = 300  # por corrida, para no demorar horas de una sola vez

# clases conocidas, en orden de precisión — la primera que exista y
# tenga contenido real gana, antes de caer al <article> genérico
CLASES_PRECISAS = [
    "td-post-content",  # tema "Newspaper" (tagDiv) — El Ovallino y variantes
    "entry-content",  # WordPress genérico
    "post-content",
    "article-content",
    "single-content",
    "content-node",  # Drupal — El Observatodo
]

RUIDO = [
    re.compile(r"\d+\s*minutos?\s*de\s*lectura", re.IGNORECASE),
    re.compile(r"^Publicado\s+hace\s+.+$", re.IGNORECASE | re.MULTILINE),
    # bloque de metadatos del tema (fecha + "Agregar <Medio>" + "Por
    # <Medio>") que varias plantillas insertan en medio del cuerpo del
    # artículo — sin esto, el nombre del propio medio queda repetido en
    # cada una de sus noticias e infla artificialmente su frecuencia de
    # palabras, el mismo tipo de sesgo por auto-mención que ya se
    # encontró y corrigió en las intervenciones del Senado
    re.compile(r"\nel\n.+?\n\|\n.+?\n\|\nAgregar [^\n]+\nPor\n[^\n]+\n"),
    re.compile(r"^Compartir$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Agregar$", re.IGNORECASE | re.MULTILINE),
]


def _mejor_div_generico(soup: BeautifulSoup):
    """Último recurso: el <div> con más párrafos directos — sirve para
    plantillas que no calzan con ninguna clase ni etiqueta conocida."""
    mejor, mejor_largo = None, 0
    for div in soup.find_all("div"):
        parrafos = div.find_all("p", recursive=False)
        if len(parrafos) < 3:
            continue
        largo = len(div.get_text(strip=True))
        if largo > mejor_largo:
            mejor, mejor_largo = div, largo
    return mejor


def extraer_texto(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    texto = None

    for clase in CLASES_PRECISAS:
        el = soup.find(class_=clase)
        if el and len(el.get_text(strip=True)) > 200:
            texto = el.get_text("\n", strip=True)
            break

    if texto is None:
        article = soup.find("article")
        if article and len(article.get_text(strip=True)) > 200:
            texto = article.get_text("\n", strip=True)

    if texto is None:
        generico = _mejor_div_generico(soup)
        if generico:
            texto = generico.get_text("\n", strip=True)

    if not texto:
        return None
    for patron in RUIDO:
        texto = patron.sub("", texto)
    texto = re.sub(r"\n{2,}", "\n", texto).strip()
    return texto or None


class ScraperPrensaTexto(BaseScraper):
    nombre = "prensa_texto"
    frecuencia = "diaria"

    def recolectar(self) -> list[dict]:
        self.db.row_factory = sqlite3.Row
        filas = self.db.execute(
            """
            SELECT id, fuente, url FROM prensa_articulo
            WHERE texto_completo IS NULL
            ORDER BY fecha DESC LIMIT ?
            """,
            (LOTE_MAXIMO,),
        ).fetchall()

        registros = []
        for fila in filas:
            try:
                resp = self.client.get(fila["url"], timeout=20, follow_redirects=True)
                resp.raise_for_status()
                texto = extraer_texto(resp.text)
            except Exception as e:
                print(f"  [{fila['fuente']}] ERROR id={fila['id']}: {e}", flush=True)
                self.stats["errores"] += 1
                time.sleep(SLEEP_ENTRE_PETICIONES)
                continue

            if texto is None:
                print(
                    f"  [{fila['fuente']}] sin texto extraído, id={fila['id']}: {fila['url']}",
                    flush=True,
                )
                self.stats["errores"] += 1
            else:
                registros.append({"id": fila["id"], "texto": texto})
            time.sleep(SLEEP_ENTRE_PETICIONES)
        return registros

    def procesar(self, registros: list[dict]) -> list[dict]:
        return registros

    def guardar(self, registros: list[dict]) -> None:
        ahora = datetime.now().isoformat()
        for r in registros:
            self.db.execute(
                "UPDATE prensa_articulo SET texto_completo = ?, actualizado_en = ? WHERE id = ?",
                (r["texto"], ahora, r["id"]),
            )
            self.stats["nuevos"] += 1
        self.db.commit()

    def exportar_json(self) -> None:
        pass  # deliberado: el texto completo nunca se exporta, ver docstring


if __name__ == "__main__":
    scraper = ScraperPrensaTexto()
    scraper.ejecutar()
    print("Estadísticas:", scraper.stats)
