# 01 — Fuentes de Datos Públicos

Catálogo completo de fuentes de datos disponibles para el observatorio. Cada fuente incluye qué datos tiene, cómo acceder, y qué se puede automatizar.

---

## 1. Cámara de Diputados — Datos Abiertos Legislativos

**URL base:** `opendata.camara.cl`
**Documentación:** https://www.camara.cl/transparencia/datosAbiertos.aspx
**Formato:** XML (API REST)
**Licencia:** Sin restricciones de derechos de autor

### Endpoints disponibles

**Votaciones:**
- `retornarVotacionesXAnno` — todas las votaciones de un año
- `retornarVotacionesXProyectoLey` — votaciones de un proyecto específico
- `retornarVotacionDetalle` — detalle completo de una votación (voto de cada diputado)

**Asistencia:**
- `retornarSesionAsistencia` — asistencia por sesión
- `retornarSesionesXAnno` — todas las sesiones de un año
- `retornarSesionesXLegislatura` — sesiones por período legislativo

**Proyectos de ley:**
- `retornarProyectoLey` — detalle de un proyecto
- `retornarTramitesConstitucionales` — estado procesal constitucional
- `retornarTramitesReglamentarios` — estado procesal reglamentario
- `retornarMocionesXAnno` — mociones presentadas por año

### Datos relevantes para OPRC
- Cómo votó cada diputado de la región (distritos 5 y 6)
- Asistencia a sesiones
- Mociones presentadas por diputados de Coquimbo
- Proyectos de ley que afectan a la región

### Automatización
Se puede consumir con requests/httpx en Python, parsear XML con lxml, y correr diariamente.

---

## 2. Senado — Datos Abiertos Legislativos

**URL:** https://www.senado.cl/transparencia/datos-abiertos-legislativos
**Formato:** XML
**Activo desde:** 2012

### Datos disponibles
- Proyectos de ley tramitados en el Congreso
- Votaciones de senadores
- Información de comisiones

### Datos relevantes para OPRC
- Votaciones de los 3 senadores de la Circunscripción de Coquimbo
- Asistencia a sesiones y comisiones
- Mociones presentadas

### Automatización
Similar a la Cámara. Endpoint XML que se puede consumir periódicamente.

---

## 3. InfoProbidad — Declaraciones de Patrimonio e Intereses

**URL:** https://www.infoprobidad.cl
**Operado por:** Consejo para la Transparencia + Contraloría General
**Formato:** Web (scraping necesario, posible sección de datos abiertos)

### Datos disponibles
- Declaraciones de patrimonio: propiedades, vehículos, derechos de agua, participaciones en empresas
- Declaraciones de intereses: actividades profesionales, laborales y de beneficencia
- Datos de cónyuge/pareja y familiares dependientes
- Comparador entre autoridades

### Herramientas del sitio
- Búsqueda individual por nombre
- Comparador entre declaraciones
- Listados por institución
- Visualizaciones y reportes
- Sección de datos abiertos (formato por confirmar)

### Datos relevantes para OPRC
- Evolución patrimonial de cada autoridad de la región
- Posibles conflictos de interés
- Comparativas entre períodos

### Automatización
- Scraping de fichas individuales (Playwright/Selenium)
- Revisar si la sección "Datos Abiertos" ofrece descarga masiva
- Monitorear cambios en declaraciones periódicamente

---

## 4. Portal de Transparencia

**URL:** https://www.portaltransparencia.cl
**Operado por:** Consejo para la Transparencia
**Formato:** Web + posibles descargas

### Datos disponibles por municipalidad (Transparencia Activa)
- Estructura orgánica y personal
- Dotación de personal y remuneraciones
- Presupuesto: ingresos y gastos
- Transferencias y subsidios otorgados
- Actos y resoluciones con efectos sobre terceros
- Contrataciones y compras
- Auditorías y mecanismos de participación ciudadana

### Datos relevantes para OPRC
- Presupuesto de las 15 municipalidades de la región
- Remuneraciones de alcaldes y concejales
- Transferencias y subsidios entregados
- Personal contratado

### Automatización
- Scraping por municipalidad (15 comunas)
- Los datos suelen estar en tablas HTML o PDFs
- Actualización: las municipalidades publican mensualmente

---

## 5. InfoTransparencia — Cumplimiento de Transparencia

**URL:** https://www.infotransparencia.cl
**Operado por:** Consejo para la Transparencia

### Datos disponibles
- Índice de cumplimiento de transparencia activa por organismo
- Evaluaciones periódicas de municipalidades
- Ranking de cumplimiento

### Datos relevantes para OPRC
- ¿Qué tan transparente es cada municipalidad de Coquimbo?
- Evolución del cumplimiento en el tiempo
- Comparativa regional vs nacional

### Automatización
- Scraping del ranking y fichas por institución
- Actualización semestral o anual (según calendario del CPLT)

---

## 6. SERVEL — Datos Electorales

**URL:** https://www.servel.cl/centro-de-datos/estadisticas-de-datos-abiertos-4zg/
**Consulta individual:** https://consulta.servel.cl
**Formato:** Archivos descargables (Excel/CSV)

### Categorías de datos
- Resultados electorales históricos por comuna
- Participación electoral (votantes / habilitados)
- Estadísticas de votantes por región y comuna
- Padrón electoral (datos agregados)

### Datos relevantes para OPRC
- Resultados de elecciones municipales, CORE, parlamentarias y presidenciales en la región
- Participación electoral por comuna
- Tendencias electorales históricas
- Datos para contextualizar el desempeño de autoridades electas

### Automatización
- Descarga periódica de archivos (ante nuevas elecciones o actualizaciones)
- Parsing de Excel/CSV con pandas
- Almacenamiento normalizado en BD

---

## 7. BCN — Biblioteca del Congreso Nacional (Datos Enlazados)

**URL:** https://datos.bcn.cl/es/
**API Ley Chile:** https://www.bcn.cl/leychile/consulta/legislacion_abierta_web_service
**Formato:** Linked Data (RDF/SPARQL), XML

### Datos disponibles
- Legislación vigente y derogada
- Datos territoriales (regiones, comunas, distritos)
- Información de legisladores
- Tramitación de proyectos de ley

### Datos relevantes para OPRC
- Normativa que afecta a la región
- Datos territoriales para mapas
- Cruce legisladores ↔ proyectos ↔ votaciones

### Automatización
- Consultas SPARQL programáticas
- Web service XML para normativa
- Datos estables, actualización según publicación de nuevas leyes

---

## 8. datos.gob.cl — Portal Nacional de Datos Abiertos

**URL:** https://datos.gob.cl
**Formato:** CSV, XLS, JSON (varía por dataset)
**Datasets:** 2.340+ de 271 instituciones

### Datos relevantes
- Buscar datasets de: GORE Coquimbo, municipalidades de la región, SUBDERE
- Presupuestos municipales, inversión regional, subsidios
- Datos de salud, educación, vivienda a nivel comunal

### Automatización
- API CKAN (estándar de datos.gob.cl) para búsqueda y descarga programática
- Filtrar por organización o tema
- Descarga directa de archivos

---

## 9. Chile Abierto

**URL:** https://chileabierto.cl
**Enfoque:** Transparencia y coherencia en datos públicos

### Datos relevantes
- Cruces de datos de transparencia
- Análisis de coherencia entre declaraciones y gestión
- Posible fuente de datos procesados

---

## 10. Gobierno Regional de Coquimbo

**URL:** https://www.gorecoquimbo.cl (verificar)
**Transparencia activa:** obligatoria por ley

### Datos relevantes
- Presupuesto del GORE
- Proyectos de inversión regional (FNDR, etc.)
- Actas del Consejo Regional
- Votaciones de consejeros regionales

### Automatización
- Scraping de actas y resoluciones
- Monitoreo de proyectos aprobados y rechazados

---

## Resumen de viabilidad de automatización

| Fuente           | Método        | Formato    | Frecuencia   | Dificultad |
|------------------|---------------|------------|--------------|------------|
| Cámara Diputados | API REST      | XML        | Diaria       | Baja       |
| Senado           | API REST      | XML        | Diaria       | Baja       |
| InfoProbidad     | Scraping      | HTML       | Mensual      | Media      |
| Transparencia    | Scraping      | HTML/PDF   | Mensual      | Alta       |
| InfoTransparencia| Scraping      | HTML       | Semestral    | Baja       |
| SERVEL           | Descarga      | Excel/CSV  | Por elección | Baja       |
| BCN              | SPARQL/API    | RDF/XML    | Semanal      | Media      |
| datos.gob.cl     | API CKAN      | CSV/JSON   | Variable     | Baja       |
| GORE Coquimbo    | Scraping      | HTML/PDF   | Mensual      | Alta       |
