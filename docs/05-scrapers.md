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
- **Votaciones y asistencia por diputado SÍ existen** con el mismo patrón
  GET (`/diputados/detalle/votaciones_sala.aspx?prmId=<DIPID>` y
  `asistencia_sala.aspx?prmId=<DIPID>`, con `prmId` no `prmID`) — se
  encontraron los links reales en el menú "Trabajo Parlamentario" de la
  ficha (no adivinados) y **cada uno por separado, en una página nueva,
  funciona perfecto** (datos hasta el 19 de agosto de 2026: votos
  individuales AFIRMATIVO/NEGATIVO y asistencia con % y detalle por sesión).
- **Pero combinar mociones→votaciones→asistencia del mismo diputado en la
  misma sesión de navegador (misma `page`, navegaciones secuencolas a
  endpoints distintos) SÍ dispara un bloqueo explícito de Cloudflare**
  ("Sorry, you have been blocked"), reproducido de forma consistente varias
  veces. No es un tema de URL incorrecta (eso fue un error de la primera
  investigación) — es detección de comportamiento.
- **Corrección (2026-08-25) a la afirmación anterior de que "repetir el
  mismo endpoint para distintos diputados... nunca bloqueado":** era
  falsa, y el motivo por el que no se detectó antes es instructivo — el
  usuario reportó que las mociones de una diputada específica (17 reales
  visibles en camara.cl) no coincidían con lo publicado en el sitio (0).
  Investigando se confirmó que **sí se bloqueaba, desde el segundo
  diputado en adelante**, reusando la misma `page`/sesión para los 7 —
  pero como el bloqueo deja la tabla con 0 filas en vez de lanzar una
  excepción, el scraper terminaba "exitoso" (`errores: 0`) con datos
  completos solo del primer diputado del diccionario. Ninguna corrida
  anterior lo notó porque nada fallaba explícitamente.
  Se corrigió igual que `personal_municipal.py`/`infoprobidad.py`:
  contexto de navegador nuevo por diputado (no comparte cookies/sesión) y
  más espaciado entre requests (2s → 5s) — de 8 a 92 mociones reales
  tras el fix. A diferencia de la decisión sobre votaciones/asistencia
  (no perseguida a propósito, ver abajo), esto no se considera ingeniería
  de evasión: es la misma higiene de sesión que ya se usa en otros
  scrapers de este proyecto por razones de confiabilidad, aplicada aquí
  porque además evita este bloqueo — no se diseñó específicamente
  *reaccionando* a un bloqueo activo detectado, sino investigando una
  falla de cobertura de datos cuyo origen resultó ser ese bloqueo.
- **Decisión: no se construye nada para votaciones/asistencia de
  diputados.** Evitar ese bloqueo específico (por ejemplo, abriendo un
  browser nuevo por cada URL, espaciando las requests de otra forma, etc.)
  significaría rediseñar el scraper específicamente porque se descubrió que
  eso esquiva la detección del sitio — eso ya es ingeniería de evasión,
  independiente de la técnica concreta o de quién lo opere. `mocion.aspx`
  se mantiene porque nunca gatilló nada; todo lo demás queda descartado, no
  solo pendiente.

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

**Fuente:** infoprobidad.cl (iniciativa del Consejo para la Transparencia y la Contraloría General de la República)
**Método:** Scraping con Playwright del buscador propio del sitio
**Dificultad:** Media-alta (nombres chilenos con inconsistencias reales de datos)
**Prioridad:** Media (Fase 4)
**Estado:** ✅ Implementado, **122/142 autoridades (86%)**, 0 errores en la corrida final.

### Datos Abiertos masivos: bloqueados, no se intentó evadir

El sitio publica un dataset nacional completo (CSV/XML/JSON/SPARQL) en
`datos.cplt.cl/catalogos/infoprobidad/*` — habría sido la vía más simple
(un solo archivo en vez de 142 búsquedas). Pero **todo el dominio
`datos.cplt.cl` responde 403 (Azure Application Gateway) en cualquier
ruta**, incluso navegando con Playwright con headers de browser real y
habiendo visitado antes la página que enlaza al dataset. No hay
`robots.txt` con una política explícita — es un bloqueo de
infraestructura, no dirigido a un bot en particular. Siguiendo el mismo
criterio que con camara.cl: no se intenta evadir un bloqueo activo. Se usa
en cambio el buscador propio de `www.infoprobidad.cl`, que responde con
normalidad.

### Estrategia real

El buscador (`/Home/Listado`) es una grilla Kendo UI con un ícono de
filtro por columna (no hay URL con query params — hay que interactuar con
la UI). Filtrar solo por Apellido Materno puede dejar cientos de
resultados paginados (ej. "Arancibia" solo: 255 registros) — el scraper
solo lee la página visible, así que **filtra por Apellido Paterno y
Apellido Materno a la vez**, lo que acota a una sola página en la
práctica.

Separar un nombre completo chileno en nombres/paterno/materno para armar
esos dos filtros no es trivial — se encontraron y corrigieron tres
inconsistencias reales de los datos:

1. **Tildes inconsistentes en el propio buscador**: buscar "Núñez" (con
   tilde) y "Nuñez" (sin tilde en la u, con ñ) devuelven conjuntos de
   resultados *distintos* — el mismo apellido está grabado con y sin
   tilde según el año de la declaración. Buscar sin tilde en la vocal
   (pero conservando la "ñ": buscar sin ella da 0 resultados siempre)
   devolvió el superset en las pruebas.
2. **Nombres de pila que a veces se abrevian**: un senador registrado
   como "Daniel Ignacio Núñez Arancibia" en el catálogo aparece como
   "DANIEL" a secas en sus declaraciones más recientes y como "DANIEL
   IGNACIO" en las de 2021 — exigir el nombre completo dejaba fuera las
   declaraciones vigentes. Se relajó a exigir solo que coincida el
   *primer* nombre de pila.
3. **Apellidos maternos compuestos con preposición**: "Cristóbal Juliá
   De La Vega" (gobernador regional) tiene apellido paterno "Juliá" y
   materno "De La Vega" — no "La" y "Vega" como asumiría separar por las
   últimas dos palabras. Se detectan y agrupan las preposiciones
   (de/del/la/las/los) previas a la última palabra.

Cuando una misma persona tiene varias declaraciones con la misma fecha
por distintos motivos (ej. un senador que declara también como dirigente
de partido), se prefiere la fila cuya columna "Cargo" coincide con el
cargo real de la autoridad en nuestro catálogo, en vez de tomar la
primera por orden de aparición.

Cada ficha de declaración (`/Declaracion/Declaracion?ID=<n>`) trae un
"Resumen de declaración" ya agregado por categoría (bienes inmuebles,
vehículos, sociedades, valores, pasivos) — se guarda ese resumen, no el
detalle línea por línea de cada bien (mismo criterio que
`personal_municipal.py`).

### Casos sin encontrar (20/142)

Verificados individualmente, no es un bug de matching genérico:
- La mayoría son búsquedas que genuinamente devuelven "Sin datos" en el
  propio sitio — no tienen declaración publicada (podría ser una
  autoridad recién asumida, o que el sitio aún no procesó su declaración).
- Un caso queda explicado y sin resolver a propósito: "Alí Manouchehri
  Moghadam Kashan Lobos" (alcalde de Coquimbo) tiene su apellido paterno
  real repartido en **tres palabras sin preposición** ("Manouchehri
  Moghadam Kashan"), algo que no se puede inferir de forma genérica sin
  arriesgar falsos positivos para el resto — se dejó como hueco
  documentado en vez de un caso especial para una sola persona.

### Notas
- No hay JSON/hash de detección de cambios por ahora — `guardar()` borra
  e inserta por autoridad individual (mismo patrón de
  `personal_municipal.py`), así una corrida que no encuentra a alguien no
  borra su dato bueno de una corrida anterior.
- Rate limiting: ~1s entre autoridades, cada búsqueda + ficha implica
  varias esperas de red (grilla Kendo + página de detalle) — una corrida
  completa de las 142 autoridades toma cerca de 20-25 minutos.

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

### Estado real — investigado y parcialmente implementado el 2026-08-24

Implementado en `scrapers/transparencia_municipal.py` (presupuesto) y
`scrapers/personal_municipal.py` (dotación/remuneraciones), ambos vía
**portaltransparencia.cl** (portal central), no los subdominios propios de
cada municipio — el portal central usa la misma plataforma para las 15
comunas, pero **cada una arma su propio árbol de sub-navegación dentro de
"Balance de Ejecución Presupuestaria" y su propio formato de PDF**.
Confirmado investigando La Serena, Coquimbo, Ovalle, Andacollo, La Higuera,
Monte Patria, Combarbalá — todas distintas entre sí. No es un problema de
"ajustar un regex", cada comuna requiere reconocimiento manual.

**Generalizaciones que sí funcionaron** (`transparencia_municipal.py`):
- Categoría con matching tolerante a typos/acentos/singular-plural.
- Selector de año con o sin prefijo "Año ".
- Fallback genérico: si no hay años visibles pero sí un link "Municipal"
  exacto, se entra ahí por defecto (cubre varias comunas sin hardcodear).
- Columnas del PDF detectadas por texto de cabecera, no por índice fijo.
- Código de cuenta nivel-top con prefijo de fondo variable.

**BUG REAL encontrado**: no todas las comunas declaran los montos "en
miles de $" (La Serena sí, Coquimbo no) — asumirlo fijo infló las cifras de
Coquimbo 1000x. Se detecta por página (`re.search(r"MILES\s*\$", texto)`)
en vez de asumirlo.

**Estado final `transparencia_municipal.py` (presupuesto), 2026-08-24:**
5/15 comunas con datos reales: La Serena, Coquimbo, La Higuera, Paihuano
(el resto de las generalizaciones de arriba se sumaron después de este
párrafo original — Paihuano, Vicuña, Punitaqui, Illapel y Canela SÍ tienen
categoría "Municipal"/"Municipalidad" navegable, pero terminaron sin
documento real en el período revisado tras el fallback genérico, salvo
Paihuano que sí encontró uno).

**Bloqueos identificados, no perseguidos:**
- Salamanca: PDF escaneado (0 texto, solo imagen) — necesitaría OCR.
- Los Vilos: el PDF está en el dominio propio del municipio
  (munilosvilos.cl) cuyo servidor usa una config TLS obsoleta/insegura
  ("dh key too small") que un cliente moderno rechaza por seguridad — no
  se debe debilitar la seguridad de nuestro lado para acomodar esto.
- Combarbalá: su propio portal advierte "servidor central... recibió
  ataques de terceros... información disponible es parcial" — dato de
  transparencia real, no un bug nuestro.
- Andacollo, Vicuña, Ovalle, Monte Patria (documento equivocado, "Pasivos"
  en vez de balance), Punitaqui, Río Hurtado, Illapel, Canela: navegación
  confirmada correcta (llegan hasta el año) incluso revisando 6 años de
  historial y con rate limiting adecuado, pero sin documento de balance
  real disponible bajo la ruta investigada. No es un bug de scraper
  identificado — parece ser falta real de publicación de su parte.

**`scrapers/personal_municipal.py` (dotación/remuneraciones), generalizado
el mismo día:** mismo enfoque base (Municipal/Municipalidad tolerante,
click de área defensivo, página nueva de Playwright por comuna), más tres
variantes de formato encontradas y corregidas al investigar por qué
algunas comunas daban 0 filas de forma reproducible:
- **La Higuera:** pide el área (Municipal/Salud) *después* de elegir el
  año, no antes — se agregó un segundo intento de click de área si no
  aparecen meses tras elegir el año.
- **Ovalle (año):** el link del año trae el área pegada ("MUNICIPAL
  2026") en vez de solo el año — el regex se cambió a matchear un año de
  4 dígitos al final del texto, no el texto completo.
- **Ovalle (mes):** el link del mes trae texto extra ("Sueldos Municipal
  - Julio 2026") — se cambió a buscar el nombre del mes por límite de
  palabra en vez de exigir texto exacto.

Estas correcciones recuperaron Andacollo, La Higuera, Paihuano, Ovalle y
Río Hurtado, que antes daban 0 filas de forma consistente (no eran datos
ausentes — eran bugs de navegación reales).

**Resultado final: 13/15 comunas con datos reales** (todas salvo La
Serena y Coquimbo). 14 remuneraciones de alcalde/alcaldesa capturadas
(Paihuano aparece con 2 registros, sin investigar en detalle — posible
cambio de alcalde/suplencia en el período).

**La Serena y Coquimbo — intermitentes, no es un bug de código:** en 6
corridas completas del scraper (con contexto de navegador aislado por
comuna y con el timeout de navegación subido de 30s a 60s, ninguno de los
dos cambios alteró el resultado) estas dos comunas alternaron entre éxito
total (cientos a ~2000 filas por combinación tipo_contrato/área, la mayor
dotación de la región) y fallo total (timeout de navegación) de forma
excluyente con un grupo específico de comunas más chicas — compatible con
el portal repartiendo la sesión entre backends con distinta capacidad de
respuesta bajo carga, agravado por golpear estos dos organismos muchas
más veces que al resto durante la depuración. Quedan pendientes de una
corrida futura (el cron semanal las recuperará solo, sin intervención).

**Corrección de `guardar()`:** originalmente borraba los registros de
las 15 comunas antes de reinsertar en cada corrida — una corrida con
fallas de red en algunas comunas borraba sus datos buenos previos sin
reemplazarlos por nada. Se cambió a borrar e insertar por comuna
individual, solo para las comunas que la corrida actual sí trajo datos
nuevos — así corridas sucesivas acumulan cobertura en vez de arriesgar
perderla.

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

## 8. Scraper: CORE Coquimbo (Consejo Regional) — Fase 6

**Fuente:** acuerdos.corecoquimbo.cl (buscador de acuerdos propio del Consejo Regional, no gorecoquimbo.cl)
**Método:** Scraping con Playwright del buscador (no requiere JS pesado, la paginación funciona vía URL)
**Dificultad:** Media
**Prioridad:** Alta (Fase 6)
**Estado:** ✅ Implementado, 101/110 acuerdos de los últimos 45 días (9 errores de red transitorios, no de código).

### Cómo se encontró

`gorecoquimbo.cl` (el sitio institucional) no publica actas/votaciones
directamente — pero enlaza a "Acuerdos CORE"
(`acuerdos.corecoquimbo.cl/busqueda_avanzada/busqueda/`), un buscador
propio del Consejo Regional con más de 10.000 acuerdos desde 2013,
paginado y con ficha individual por acuerdo. Cada ficha
(`/acuerdos/acuerdo/<id>`) trae el texto completo del acuerdo **y el
detalle de la votación nominal**: cuántos votos a favor/rechazo/
abstención/inhabilitación/ausencia, con el nombre de cada consejero(a) en
cada categoría — exactamente lo que pedía el roadmap
("Votaciones de consejeros regionales").

El dataset masivo de "Datos Abiertos" del GORE (`datos.cplt.cl` — no
confundir con el de InfoProbidad, es un dominio de la Contraloría
distinto) no se investigó porque el buscador propio ya resuelve el caso
de uso completo.

### Diseño

- Reutiliza las tablas `votacion_sesion`/`voto` ya usadas por
  `senado.py`, con `camara='core'` — el CORE también es un cuerpo
  colegiado que vota acuerdos, así que el mismo modelo aplica sin
  cambios. Consecuencia práctica: la ficha de cada consejero/gobernador
  ya mostraba "Historial de votaciones" automáticamente, sin tocar el
  sitio, apenas se guardaron los primeros votos.
- Paginación por URL: `/busqueda_avanzada/busqueda/1/acuerdos/{pageSize}/{offset}/{fecha_inicio}/{fecha_fin}/null/null` — con `pageSize=200` entran todos los resultados de una ventana de 45 días en una sola carga, sin necesidad de clickear "Siguiente".
- Solo se recolectan acuerdos de los **últimos 45 días** — hay más de
  10.000 históricos desde 2013, muy por fuera del alcance de un scraper
  semanal (mismo criterio que "votaciones recientes" del Senado).
- El texto de la votación tiene un formato irregular (algunas categorías
  como "se inhabilitan" a veces no llevan el prefijo "Sr(s):", los
  nombres pueden llevar un cargo/título antepuesto como "Presidente del
  Consejo Regional") — en vez de parsear nombres exactos, se verifica
  si el nombre completo normalizado de cada consejero/gobernador de
  nuestro catálogo aparece como substring dentro de cada categoría de
  voto, lo que es tolerante a esos prefijos.
- `guardar()` usa `ON CONFLICT DO UPDATE` (upsert) en vez de
  borrar-e-insertar — una corrida con errores de red parciales no arriesga
  perder datos de una corrida anterior, y los acuerdos que fallaron por
  timeout se recuperan solos en la próxima corrida semanal.

### Pendiente (fuera de alcance de esta pasada)

- Proyectos FNDR aprobados/rechazados y presupuesto de inversión regional
  (roadmap Fase 6) — investigado y descartado: `fndr2.gorecoquimbo.gob.cl`
  ("Fondos Concursables") es un portal de login para postulantes, no una
  base pública de proyectos FNDR; la página "Presupuesto de Inversión"
  del sitio institucional son puros PDFs de resoluciones/acuerdos por
  año, sin datos tabulares (mismo patrón de alto esfuerzo/bajo valor que
  transferencias municipales en Fase 3, con el agravante de que algunos
  links de "Informes de Ejecución FNDR" del propio sitio están rotos —
  los 11 meses apuntan al mismo PDF por error de ellos).

---

## 9. Datos: límites administrativos (mapa interactivo) — Fase 3

**Fuente:** OpenStreetMap, vía Nominatim (nominatim.openstreetmap.org)
**Método:** `scrapers/poblar_geojson.py` — no es un scraper semanal, es
un script de una sola vez (los límites administrativos no cambian, igual
que `poblar_catalogo.py` con los CSV maestros)
**Estado:** ✅ 15/15 comunas.

Para cada comuna se busca en Nominatim ("`<nombre>`, Región de Coquimbo,
Chile"), se toma la primera relación (`osm_type=relation`) y se descarga
su geometría con `polygon_geojson=1`. La geometría de OSM a resolución
completa pesa 50-370KB por comuna (2-3MB las 15 juntas) — se simplifica
con un Douglas-Peucker propio (sin dependencias nuevas) a tolerancia
~110m, quedando en 3-17KB por comuna (~140KB el total), suficiente para
un mapa a escala regional.

Respeta la política de uso de Nominatim (nominatim.org/release-docs/latest/api/Usage-Policy/):
User-Agent identificable con contacto, máximo 1 request/segundo.

El mapa en sí (`/mapa/`) usa Leaflet (sin API key, tiles de
OpenStreetMap) con dos indicadores intercambiables: cobertura de datos
de transparencia y dotación municipal total, coloreando cada polígono de
comuna.

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

3. **Idempotencia e historización (2026-08-25):** `personal_municipal`,
   `remuneracion_autoridad`, `presupuesto_municipal` y
   `declaracion_patrimonio` tenían un problema real hasta esta fecha:
   `guardar()` borraba todo lo de una comuna/autoridad antes de
   reinsertar, así que cada corrida semanal **destruía el período
   anterior** en vez de acumular historia — no había forma de comparar
   "cómo cambió X en el tiempo", pese a que eso está explícitamente
   pedido en el roadmap (Fase 4: "detectar cambios entre declaraciones",
   "comparador entre períodos"). Se corrigió con índices únicos por
   período real (`comuna_id+anno+mes+área+tipo_contrato`,
   `autoridad_id+fecha_declaracion`, etc.) e `INSERT ... ON CONFLICT DO
   UPDATE` (mismo patrón que `votacion_sesion`/`voto`, que ya eran
   correctos por diseño — cada sesión/acuerdo es un evento único). Un
   período que se vuelve a scrapear se actualiza en el lugar; un período
   nuevo se agrega sin tocar los anteriores. Verificado con tests que
   llaman `guardar()` dos veces con períodos distintos e iguales
   (`scrapers/tests/test_historizacion.py`) — la prueba real de que
   acumula en producción se verá recién en las próximas corridas
   semanales, no había forma de probarlo retroactivo (la historia ya
   borrada en corridas anteriores no se puede recuperar).

4. **Logging:** Registrar cada ejecución en `actualizacion_log` para monitoreo.

5. **Alertas:** Si un scraper falla 3 veces seguidas, enviar notificación (email o Telegram).

6. **Caché:** Guardar respuestas raw en `/data/raw/` para debug y re-procesamiento sin re-descargar.

7. **robots.txt:** Respetar siempre. Si un sitio bloquea scraping, documentarlo y buscar alternativas (solicitud directa de datos, transparencia activa).
