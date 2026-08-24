# 03 — Roadmap por Fases

Plan de trabajo incremental. Cada fase entrega algo funcional y usable.

---

## Fase 0 — Setup del proyecto (1-2 días)

### Entregables
- [ ] Repo en GitHub inicializado
- [ ] Estructura de carpetas creada
- [ ] Python virtualenv + `requirements.txt` con dependencias base
- [ ] Proyecto Astro inicializado en `/site`
- [ ] Base de datos SQLite con esquema inicial
- [ ] GitHub Actions workflow básico (solo lint/test)
- [ ] `.env.example` con variables necesarias

### Instrucciones para Claude
> "Leé `docs/02-arquitectura.md` y `docs/04-modelos-de-datos.md`. Inicializá el proyecto Python con las dependencias, creá el esquema SQLite, y configurá el proyecto Astro con Tailwind."

---

## Fase 1 — Catálogo de autoridades (3-5 días)

### Objetivo
Tener una base de datos completa con todas las autoridades de la región y un sitio mínimo que las muestre.

### Tareas
- [ ] Crear el catálogo maestro de autoridades manualmente (JSON/CSV)
  - 15 alcaldes con comuna, partido, período
  - 100 concejales con comuna, partido
  - 16 consejeros regionales con circunscripción, partido
  - 7 diputados con distrito, partido
  - 3 senadores con circunscripción, partido
  - 1 gobernadora regional
- [ ] Scraper SERVEL: importar resultados de la última elección municipal (2024) y parlamentaria
- [ ] Poblar la BD con el catálogo
- [ ] Sitio web: página principal con listado de autoridades
- [ ] Sitio web: ficha individual por autoridad (datos básicos)
- [ ] Sitio web: filtros por tipo de cargo, comuna, partido
- [ ] Deploy inicial

### Instrucciones para Claude
> "Leé `docs/04-modelos-de-datos.md`. Creá un script que genere el catálogo de autoridades de la Región de Coquimbo a partir de los datos de SERVEL. Después creá las páginas en Astro para mostrarlas."

---

## Fase 2 — Datos legislativos automatizados (1-2 semanas)

### Objetivo
Automatizar la recolección de votaciones y asistencia de diputados y senadores.

### Tareas
- [ ] Scraper Cámara de Diputados:
  - [ ] `retornarVotacionesXAnno` — votaciones del año en curso
  - [ ] `retornarVotacionDetalle` — voto de cada diputado
  - [ ] `retornarSesionAsistencia` — asistencia a sesiones
  - [ ] `retornarMocionesXAnno` — mociones presentadas
- [ ] Scraper Senado:
  - [ ] Votaciones de senadores de Coquimbo
  - [ ] Asistencia a sesiones
- [ ] Pipeline: parseo XML → normalización → guardado en BD
- [ ] GitHub Actions: cron semanal para actualizar
- [ ] Sitio web: dashboard de votaciones por diputado/senador
  - Gráfico de asistencia (% presente vs ausente)
  - Historial de votaciones (a favor / en contra / abstención)
  - Mociones presentadas
- [ ] Sitio web: página de votaciones recientes con contexto

### Instrucciones para Claude
> "Leé `docs/05-scrapers.md` sección 'Cámara de Diputados'. Implementá el scraper que consume la API XML, parsea las votaciones, y las guarda en la BD. Después creá los componentes Astro para visualizarlas."

---

## Fase 3 — Transparencia municipal (2-3 semanas)

### Objetivo
Recopilar datos de transparencia de las 15 municipalidades.

### Tareas
- [ ] Scraper Portal Transparencia:
  - [ ] Presupuesto municipal (ingresos y gastos)
  - [ ] Dotación de personal y remuneraciones
  - [ ] Transferencias y subsidios
- [ ] Scraper InfoTransparencia:
  - [ ] Índice de cumplimiento por municipalidad
- [ ] Normalización de datos (formatos varían entre municipalidades)
- [ ] Sitio web: dashboard municipal
  - Comparativa de presupuestos entre comunas
  - Ranking de transparencia
  - Detalle por comuna
- [ ] Sitio web: mapa interactivo de la región
  - GeoJSON de las 15 comunas
  - Color por indicador (presupuesto, transparencia, etc.)

### Instrucciones para Claude
> "Implementá el scraper para el Portal de Transparencia, empezando con 2-3 municipalidades piloto (La Serena, Coquimbo, Ovalle). Después generalizá a las 15."

---

## Fase 4 — Patrimonio y probidad (1-2 semanas)

### Objetivo
Incorporar declaraciones de patrimonio e intereses.

### Tareas
- [ ] Scraper InfoProbidad:
  - [ ] Declaraciones de patrimonio de autoridades de la región
  - [ ] Declaraciones de intereses
  - [ ] Detectar cambios entre declaraciones
- [ ] Sitio web: sección de probidad por autoridad
  - Resumen de patrimonio declarado
  - Comparador entre períodos
  - Alertas de cambios significativos

### Instrucciones para Claude
> "Investigá la estructura de InfoProbidad.cl usando Playwright. Creá un scraper que extraiga las declaraciones de las autoridades de Coquimbo."

---

## Fase 5 — Newsletter y alertas (1 semana)

### Objetivo
Publicación automática de un boletín semanal.

### Tareas
- [ ] Template de email (HTML responsive)
- [ ] Script que genera el boletín a partir de los datos nuevos de la semana:
  - Votaciones destacadas
  - Cambios en patrimonio
  - Proyectos de ley relevantes
  - Actualizaciones presupuestarias
- [ ] Integración con Resend (o Buttondown)
- [ ] Formulario de suscripción en el sitio
- [ ] GitHub Actions: envío automático los viernes

### Instrucciones para Claude
> "Creá un script Python que genere un resumen semanal en HTML a partir de los datos en la BD, y lo envíe vía la API de Resend."

---

## Fase 6 — Gobierno Regional y CORE (2 semanas)

### Objetivo
Incorporar datos del Gobierno Regional y Consejo Regional.

### Tareas
- [ ] Scraper GORE Coquimbo:
  - [ ] Actas del Consejo Regional
  - [ ] Proyectos FNDR aprobados/rechazados
  - [ ] Presupuesto regional
- [ ] Sitio web: sección CORE
  - Votaciones de consejeros regionales
  - Proyectos de inversión por comuna
  - Dashboard de ejecución presupuestaria

---

## Fase 7 — Análisis y contenido avanzado (continuo)

### Ideas para desarrollo continuo
- [ ] Índice propio de desempeño por autoridad (ponderando asistencia, votaciones, transparencia, patrimonio)
- [ ] Análisis de redes sociales de autoridades
- [ ] Generación automática de reportes con IA (resúmenes de sesiones, análisis de tendencias)
- [ ] API pública del observatorio para que otros puedan consumir los datos
- [ ] Integración con redes sociales (publicar automáticamente en X/Twitter)
- [ ] Comparativas con otras regiones

---

## Priorización sugerida

```
IMPACTO ALTO + ESFUERZO BAJO → Hacer primero
├── Fase 0: Setup
├── Fase 1: Catálogo de autoridades
└── Fase 2: Datos legislativos (API disponible)

IMPACTO ALTO + ESFUERZO MEDIO
├── Fase 5: Newsletter
└── Fase 4: Patrimonio

IMPACTO ALTO + ESFUERZO ALTO
├── Fase 3: Transparencia municipal
└── Fase 6: GORE y CORE

DESARROLLO CONTINUO
└── Fase 7: Análisis avanzado
```
