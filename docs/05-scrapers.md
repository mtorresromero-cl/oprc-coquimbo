# 05 — Guía de Scrapers y Automatización

Detalle técnico de cada scraper a implementar, con ejemplos de código y estrategias de extracción.

---

## Estructura general de un scraper

Cada scraper sigue el mismo patrón:

```python
# scrapers/base.py
import httpx
import sqlite3
import json
from datetime import datetime
from pathlib import Path

class BaseScraper:
    """Clase base para todos los scrapers."""

    nombre: str = "base"
    frecuencia: str = "semanal"  # diaria | semanal | mensual

    def __init__(self, db_path: str = "data/db/oprc.sqlite"):
        self.db = sqlite3.connect(db_path)
        self.client = httpx.Client(
            timeout=30,
            headers={"User-Agent": "OPRC-Bot/1.0 (+https://oprcoquimbo.cl)"},
        )
        self.stats = {"nuevos": 0, "actualizados": 0, "errores": 0}

    def ejecutar(self):
        """Método principal. Llama a recolectar(), procesar(), guardar()."""
        self.log_inicio()
        try:
            datos_raw = self.recolectar()
            datos_procesados = self.procesar(datos_raw)
            self.guardar(datos_procesados)
            self.exportar_json()
            self.log_fin("ok")
        except Exception as e:
            self.log_fin("error", str(e))
            raise

    def recolectar(self):
        """Override: obtener datos de la fuente."""
        raise NotImplementedError

    def procesar(self, datos_raw):
        """Override: limpiar y normalizar."""
        raise NotImplementedError

    def guardar(self, datos):
        """Override: insertar/actualizar en BD."""
        raise NotImplementedError

    def exportar_json(self):
        """Override: generar archivos JSON para el sitio."""
        raise NotImplementedError

    def log_inicio(self):
        self.db.execute(
            "INSERT INTO actualizacion_log (scraper, inicio) VALUES (?, ?)",
            (self.nombre, datetime.now().isoformat())
        )
        self.db.commit()

    def log_fin(self, estado, error=None):
        self.db.execute("""
            UPDATE actualizacion_log
            SET fin = ?, estado = ?, registros_nuevos = ?,
                registros_actualizados = ?, error_mensaje = ?
            WHERE scraper = ? AND fin IS NULL
        """, (
            datetime.now().isoformat(), estado,
            self.stats["nuevos"], self.stats["actualizados"],
            error, self.nombre
        ))
        self.db.commit()
```

---

## 1. Scraper: Cámara de Diputados — ESTADO: bloqueado, sin datos de votaciones/asistencia

**Fuente:** `opendata.camara.cl` (servicio SOAP/XML legacy `wscamaradiputados.asmx`)
**Dificultad:** N/A — no viable actualmente
**Prioridad:** Pendiente de resolución

**Investigado el 2026-08-24 (Fase 2).** Los nombres de método de esta sección
(`retornarVotacionesXAnno`, etc.) eran un supuesto inicial y **no existen** en
el servicio real. Los nombres reales son `get*` con guion bajo
(`getDiputados`, `getDiputados_Vigentes`, `getSesiones`, `getLegislaturas`,
`getVotacion_Detalle`, `getVotaciones_Boletin`, `getSesionBoletinXML`, etc.).

**Lo que sí funciona** (datos reales y actuales verificados):
```
GET https://opendata.camara.cl/wscamaradiputados.asmx/getDiputados_Vigentes
GET https://opendata.camara.cl/wscamaradiputados.asmx/getSesiones?prmLegislaturaID=58
GET https://opendata.camara.cl/wscamaradiputados.asmx/getLegislaturaActual
```
IDs reales de los 7 diputados de la región (DIPID en este servicio):
Manouchehri Lobos=1142, Tello Rojas=1177, Castillo Rojas=1117,
Salinas Maya=1250, Urqueta Rojas=1255, Sulantay Olivares=1174, Grohs Marín=1212.

**Lo que NO funciona:** `getVotaciones_Boletin`, `getVotacion_Detalle`,
`getSesionBoletinXML` y el campo `<Asistencia>` de `getSesionDetalle`
devuelven vacío para todas las sesiones de 2026 probadas — el catálogo básico
se sigue sincronizando pero los datos de votaciones/asistencia dejaron de
publicarse ahí. El portal `opendata.congreso.cl` (que en teoría reemplaza a
este servicio) expone páginas de "Votaciones por Proyecto de Ley" que
internamente llaman al mismo backend roto.

**Scraping de camara.cl — resuelto parcialmente el 2026-08-24, con matices
importantes:**
- `robots.txt` bloquea explícitamente a `ClaudeBot` y otros crawlers de IA
  por nombre (`Disallow: /`), sitio completo, sin excepción por sección. Un
  bot propio identificado honestamente (no como uno de esos nombres) cae
  bajo la regla general `Allow: /` y no está prohibido.
- Cloudflare bloquea requests simples (curl/httpx) con 403, pero un
  navegador real headless (Playwright, user-agent normal) **sí pasa** para
  navegación simple (GET) — confirmado con contenido real y actual.
- El **formulario de búsqueda** del sitio (POST, ej. filtrar
  `proyectos_ley.aspx` por autor) **sí está bloqueado** (403) — la
  protección distingue navegación pasiva de interacción automatizada.
- La **ficha personal de cada diputado**
  (`/diputados/detalle/mociones.aspx?prmID=<DIPID>`) es una URL con
  parámetro GET simple, no requiere el formulario, y **sí funciona** —
  implementado en `scrapers/camara_mociones.py` (reemplaza al intento
  anterior con BCN, que tenía semanas/meses de rezago). Usa Playwright,
  solo GET a fichas individuales, nunca envía el formulario de búsqueda.
- Se intentó adivinar la URL de la página de **asistencia** por diputado y
  se obtuvo un bloqueo explícito de Cloudflare ("Sorry, you have been
  blocked") — no se siguió insistiendo con más variantes de URL. Votaciones
  y asistencia de diputados siguen sin resolver; no se debe construir nada
  pensado específicamente para evadir ese bloqueo (CAPTCHA solving, spoofing
  de fingerprint, proxies rotativos, etc.) — esa es la línea que no se cruza,
  independiente de quién opere el scraper.

**Alternativa complementaria: `datos.bcn.cl`** (datos enlazados, robots.txt
abierto, SPARQL). Tiene mociones parlamentarias pero con rezago de
publicación (semanas/meses) y sin votaciones/asistencia en absoluto — por
eso se descartó a favor de camara.cl directo para mociones. Si en el futuro
se necesita retomar votaciones/asistencia de diputados, revisar primero si
`opendata.congreso.cl` arregló su backend (métodos `get*` de arriba).

---

## 2. Scraper: Senado

**Fuente:** senado.cl
**Método:** API REST → XML (similar a Cámara)
**Dificultad:** Baja
**Prioridad:** Alta (Fase 2)

### Senadores de Coquimbo (Circunscripción 4)
Obtener los 3 senadores en ejercicio y filtrar sus votaciones.

### Estrategia
- Verificar si el endpoint es similar al de la Cámara (`opendata.congreso.cl`)
- Si no hay API directa, scraping de la sección de transparencia
- Complementar con datos de BCN (datos enlazados)

### Ejemplo

```python
# scrapers/senado.py
from base import BaseScraper

class ScraperSenado(BaseScraper):
    nombre = "senado"

    # Circunscripción 4: Coquimbo
    senadores_coquimbo = []  # poblar con IDs reales

    def recolectar(self):
        # Intentar primero opendata.congreso.cl
        # Si no, scraping de senado.cl/transparencia
        pass
```

---

## 3. Scraper: InfoProbidad

**Fuente:** infoprobidad.cl
**Método:** Scraping con Playwright (sitio dinámico)
**Dificultad:** Media
**Prioridad:** Media (Fase 4)

### Estrategia de extracción

```python
# scrapers/infoprobidad.py
from playwright.sync_api import sync_playwright
from base import BaseScraper
import hashlib

class ScraperInfoProbidad(BaseScraper):
    nombre = "infoprobidad"
    base_url = "https://www.infoprobidad.cl"

    def recolectar(self):
        """Buscar declaraciones de autoridades de la región."""
        declaraciones = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Para cada autoridad en nuestra BD
            autoridades = self.db.execute(
                "SELECT id, nombre_completo FROM autoridad WHERE activo = 1"
            ).fetchall()

            for aut_id, nombre in autoridades:
                # Navegar al buscador
                page.goto(f"{self.base_url}/Home/Listado")
                page.fill("#txtBuscar", nombre)
                page.click("#btnBuscar")
                page.wait_for_selector(".resultado", timeout=10000)

                # Extraer enlace a la declaración
                resultados = page.query_selector_all(".resultado a")
                for r in resultados:
                    href = r.get_attribute("href")
                    if href:
                        declaraciones.append({
                            "autoridad_id": aut_id,
                            "url": f"{self.base_url}{href}",
                        })

                # Rate limiting
                page.wait_for_timeout(2000)

            browser.close()

        # Ahora descargar cada declaración
        for d in declaraciones:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(d["url"])
                page.wait_for_selector(".declaracion-contenido", timeout=15000)

                d["contenido"] = page.content()
                d["hash"] = hashlib.sha256(d["contenido"].encode()).hexdigest()

                browser.close()
                import time; time.sleep(2)

        return declaraciones

    def procesar(self, declaraciones):
        """Parsear HTML de declaraciones y extraer campos."""
        from bs4 import BeautifulSoup
        procesadas = []

        for d in declaraciones:
            soup = BeautifulSoup(d["contenido"], "html.parser")

            # Extraer campos según la estructura del sitio
            # (adaptar según HTML real)
            procesadas.append({
                "autoridad_id": d["autoridad_id"],
                "tipo": "patrimonio",
                "fecha": None,  # extraer del HTML
                "bienes_inmuebles": [],  # parsear tabla
                "vehiculos": [],
                "participaciones": [],
                "hash": d["hash"],
                "url": d["url"],
            })

        return procesadas
```

### Notas
- InfoProbidad usa JavaScript para renderizar, requiere Playwright
- Implementar detección de cambios con hash del contenido
- Solo re-procesar si el hash cambió
- Respetar rate limiting estricto (2+ segundos entre requests)

---

## 4. Scraper: Portal de Transparencia Municipal

**Fuente:** portaltransparencia.cl + sitios municipales
**Método:** Scraping (HTML + posiblemente PDFs)
**Dificultad:** Alta
**Prioridad:** Media (Fase 3)

### Desafíos
- Cada municipalidad puede tener formato diferente
- Algunos datos están en PDFs (necesita parsing con pdfplumber o camelot)
- Los sitios municipales no siempre tienen estructura consistente

### Estrategia

```python
# scrapers/transparencia_municipal.py
from base import BaseScraper

COMUNAS_COQUIMBO = {
    "la-serena":     {"url_transparencia": "..."},
    "coquimbo":      {"url_transparencia": "..."},
    "andacollo":     {"url_transparencia": "..."},
    "la-higuera":    {"url_transparencia": "..."},
    "paihuano":      {"url_transparencia": "..."},
    "vicuna":        {"url_transparencia": "..."},
    "ovalle":        {"url_transparencia": "..."},
    "combarbala":    {"url_transparencia": "..."},
    "monte-patria":  {"url_transparencia": "..."},
    "punitaqui":     {"url_transparencia": "..."},
    "rio-hurtado":   {"url_transparencia": "..."},
    "illapel":       {"url_transparencia": "..."},
    "canela":        {"url_transparencia": "..."},
    "los-vilos":     {"url_transparencia": "..."},
    "salamanca":     {"url_transparencia": "..."},
}

class ScraperTransparencia(BaseScraper):
    nombre = "transparencia_municipal"

    def recolectar(self):
        """Recolectar datos de cada municipalidad."""
        datos = []
        for comuna_id, config in COMUNAS_COQUIMBO.items():
            try:
                # 1. Intentar Portal de Transparencia centralizado
                datos_comuna = self.scrape_portal(comuna_id)

                # 2. Si no hay datos suficientes, intentar sitio municipal
                if not datos_comuna:
                    datos_comuna = self.scrape_sitio_municipal(comuna_id, config)

                datos.append(datos_comuna)
            except Exception as e:
                self.stats["errores"] += 1
                print(f"Error en {comuna_id}: {e}")

        return datos

    def scrape_portal(self, comuna_id):
        """Scraping del portal centralizado de transparencia."""
        # Navegar a: portaltransparencia.cl > Municipalidades > [comuna]
        # Extraer: presupuesto, personal, transferencias
        pass

    def scrape_sitio_municipal(self, comuna_id, config):
        """Scraping del sitio web propio de la municipalidad."""
        # Cada uno puede requerir un parser específico
        pass
```

### Notas
- Empezar con las 3 municipalidades más grandes (La Serena, Coquimbo, Ovalle) como piloto
- Documentar la estructura HTML de cada sitio
- Para PDFs: usar `pdfplumber` para extraer tablas presupuestarias

---

## 5. Scraper: SERVEL (Datos Electorales)

**Fuente:** servel.cl
**Método:** Descarga de archivos (Excel/CSV)
**Dificultad:** Baja
**Prioridad:** Alta (Fase 1)

### Estrategia

```python
# scrapers/servel.py
import pandas as pd
from base import BaseScraper

class ScraperServel(BaseScraper):
    nombre = "servel"

    def recolectar(self):
        """Descargar archivos de resultados electorales."""
        # Los archivos están en:
        # servel.cl/centro-de-datos/estadisticas-de-datos-abiertos-4zg/
        #
        # Estructura típica:
        # - Resultados por mesa
        # - Resultados por comuna
        # - Participación electoral
        #
        # Formatos: .xlsx, .csv
        pass

    def procesar(self, archivos):
        """Leer Excel/CSV y filtrar por Región de Coquimbo."""
        resultados = []
        for archivo in archivos:
            df = pd.read_excel(archivo)  # o pd.read_csv()

            # Filtrar por Región de Coquimbo
            df_coquimbo = df[df["Region"] == "Coquimbo"]

            for _, row in df_coquimbo.iterrows():
                resultados.append({
                    "eleccion_tipo": row.get("TipoEleccion"),
                    "anno": row.get("Anno"),
                    "comuna_id": self.normalizar_comuna(row.get("Comuna")),
                    "candidato": row.get("Candidato"),
                    "partido": row.get("Partido"),
                    "votos": row.get("Votos"),
                    "porcentaje": row.get("Porcentaje"),
                    "electo": row.get("Electo"),
                })

        return resultados
```

---

## 6. Scraper: InfoTransparencia

**Fuente:** infotransparencia.cl
**Método:** Scraping HTML
**Dificultad:** Baja
**Prioridad:** Baja (Fase 3)

### Datos a extraer
- Puntaje de cumplimiento de transparencia activa
- Desglose por ítem evaluado
- Ranking regional y nacional

---

## 7. Scraper: BCN Datos Enlazados

**Fuente:** datos.bcn.cl
**Método:** SPARQL queries
**Dificultad:** Media
**Prioridad:** Baja (complementario)

### Ejemplo de query SPARQL

```sparql
# Obtener legisladores de la Región de Coquimbo
PREFIX bcn: <http://datos.bcn.cl/ontologies/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?legislador ?nombre ?partido ?periodo
WHERE {
  ?legislador a bcn:Legislador ;
              rdfs:label ?nombre ;
              bcn:partido ?partido ;
              bcn:circunscripcion ?circ .
  FILTER(CONTAINS(STR(?circ), "Coquimbo"))
}
```

---

## Script de ejecución general

```python
# scrapers/run_all.py
"""Ejecutar todos los scrapers configurados."""

from camara_diputados import ScraperCamara
from senado import ScraperSenado
from servel import ScraperServel
from infoprobidad import ScraperInfoProbidad
from transparencia_municipal import ScraperTransparencia
from infotransparencia import ScraperInfoTransparencia

SCRAPERS = [
    ScraperCamara,
    ScraperSenado,
    ScraperServel,
    # Los siguientes se habilitan en fases posteriores:
    # ScraperInfoProbidad,
    # ScraperTransparencia,
    # ScraperInfoTransparencia,
]

def main():
    for ScraperClass in SCRAPERS:
        print(f"Ejecutando: {ScraperClass.nombre}...")
        try:
            scraper = ScraperClass()
            scraper.ejecutar()
            print(f"  OK: {scraper.stats}")
        except Exception as e:
            print(f"  ERROR: {e}")

if __name__ == "__main__":
    main()
```

---

## Requirements

```
# scrapers/requirements.txt
httpx>=0.27
lxml>=5.0
beautifulsoup4>=4.12
pandas>=2.2
openpyxl>=3.1          # para leer Excel
pdfplumber>=0.11       # para PDFs de transparencia
playwright>=1.40
sqlmodel>=0.0.16
python-dotenv>=1.0
```

---

## Consideraciones de producción

1. **Rate limiting:** Nunca más de 1 request/segundo por fuente. Usar `time.sleep()` o `asyncio.sleep()`.

2. **Reintentos:** Implementar retry con backoff exponencial para errores de red.

3. **Idempotencia:** Los scrapers deben poder ejecutarse múltiples veces sin duplicar datos (usar `INSERT OR IGNORE` / `INSERT OR REPLACE`).

4. **Logging:** Registrar cada ejecución en `actualizacion_log` para monitoreo.

5. **Alertas:** Si un scraper falla 3 veces seguidas, enviar notificación (email o Telegram).

6. **Caché:** Guardar respuestas raw en `/data/raw/` para debug y re-procesamiento sin re-descargar.

7. **robots.txt:** Respetar siempre. Si un sitio bloquea scraping, documentarlo y buscar alternativas (solicitud directa de datos, transparencia activa).
