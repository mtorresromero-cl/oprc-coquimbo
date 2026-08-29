# 06 — Herramientas Interactivas

Especificaciones para 4 herramientas interactivas que complementan las guías PDF.
Cada una es un componente Astro + JavaScript que consume datos JSON estáticos
generados por los scrapers del proyecto.

---

## Herramienta 1: Buscador de Autoridades ("¿Quién me representa?")

### Qué hace
El usuario ingresa su comuna (o la selecciona de un menú) y ve inmediatamente
todas las autoridades que lo representan: alcalde, concejales, consejeros
regionales, diputados, senadores, y la gobernadora regional. Cada autoridad
muestra nombre, foto (si está disponible), partido, periodo, y links a sus
declaraciones de patrimonio, votaciones y asistencia.

### Datos necesarios
```
src/data/autoridades.json
```
Estructura:
```json
[
  {
    "id": "alcalde-la-serena",
    "nombre": "Nombre Completo",
    "cargo": "Alcalde",
    "comuna": "La Serena",
    "provincia": "Elqui",
    "circunscripcion": "Elqui Costa",
    "distrito": 5,
    "partido": "Partido X",
    "periodo": "2024-2028",
    "foto": "/img/autoridades/alcalde-la-serena.jpg",
    "email": "alcalde@laserena.cl",
    "telefono": "+56 51 2XXXXXX",
    "links": {
      "infoprobidad": "https://infoprobidad.cl/...",
      "transparencia": "https://...",
      "votaciones": "https://..."
    }
  }
]
```

### Fuentes de datos
- Alcaldes y concejales: SERVEL (resultados electorales) + sitios municipales
- Consejeros regionales: SERVEL + GORE Coquimbo
- Diputados: opendata.camara.cl (API XML)
- Senadores: senado.cl/appsenado/index.php?mo=senadores
- Gobernadora: GORE Coquimbo

### Mapeo comuna → autoridades
```
Comuna → Alcalde (1) + Concejales (6-8)
Comuna → Provincia → Circunscripción CORE → Consejeros regionales
Comuna → Distrito (5 o 6) → Diputados
Toda la región → Senadores (3) + Gobernadora (1)
```

Distritos:
- Distrito 5: La Serena, Coquimbo, Andacollo, La Higuera, Paihuano, Vicuña
- Distrito 6: Ovalle, Combarbalá, Monte Patria, Punitaqui, Río Hurtado,
  Illapel, Canela, Los Vilos, Salamanca

Circunscripciones CORE:
- Elqui Costa (4): La Serena, Coquimbo
- Elqui Interior (3): Andacollo, La Higuera, Paihuano, Vicuña
- Limarí (5): Ovalle, Combarbalá, Monte Patria, Punitaqui, Río Hurtado
- Choapa (4): Illapel, Canela, Los Vilos, Salamanca

### Implementación en Astro

Archivo: `src/pages/herramientas/quien-me-representa.astro`

```astro
---
import Layout from '../../layouts/Layout.astro';
import autoridades from '../../data/autoridades.json';

const comunas = [...new Set(autoridades.map(a => a.comuna))].sort();
---

<Layout title="¿Quién me representa?">
  <section class="herramienta">
    <h1>¿Quién me representa?</h1>
    <p>Selecciona tu comuna para ver todas las autoridades que te representan.</p>

    <select id="selector-comuna">
      <option value="">-- Elige tu comuna --</option>
      {comunas.map(c => <option value={c}>{c}</option>)}
    </select>

    <div id="resultados" class="grid-autoridades"></div>
  </section>

  <script define:vars={{ autoridades }}>
    // Mapeos
    const DISTRITOS = {
      5: ['La Serena','Coquimbo','Andacollo','La Higuera','Paihuano','Vicuña'],
      6: ['Ovalle','Combarbalá','Monte Patria','Punitaqui','Río Hurtado',
          'Illapel','Canela','Los Vilos','Salamanca']
    };

    const selector = document.getElementById('selector-comuna');
    const resultados = document.getElementById('resultados');

    selector.addEventListener('change', () => {
      const comuna = selector.value;
      if (!comuna) { resultados.innerHTML = ''; return; }

      const distrito = Object.entries(DISTRITOS)
        .find(([d, comunas]) => comunas.includes(comuna))?.[0];

      const mis = autoridades.filter(a => {
        if (a.cargo === 'Alcalde' || a.cargo === 'Concejal')
          return a.comuna === comuna;
        if (a.cargo === 'Diputado')
          return String(a.distrito) === distrito;
        if (['Senador','Gobernadora Regional'].includes(a.cargo))
          return true; // toda la región
        if (a.cargo === 'Consejero Regional')
          return true; // filtrar por circunscripción
        return false;
      });

      resultados.innerHTML = mis.map(a => `
        <div class="card-autoridad">
          <img src="${a.foto || '/img/placeholder.svg'}" alt="${a.nombre}">
          <h3>${a.nombre}</h3>
          <span class="cargo">${a.cargo}</span>
          <span class="partido">${a.partido}</span>
          <span class="periodo">${a.periodo}</span>
          <div class="links">
            ${a.links?.infoprobidad ? `<a href="${a.links.infoprobidad}">Patrimonio</a>` : ''}
            ${a.links?.votaciones ? `<a href="${a.links.votaciones}">Votaciones</a>` : ''}
          </div>
        </div>
      `).join('');
    });
  </script>
</Layout>
```

### Instrucciones para Claude en VSC
```
1. Crear src/data/autoridades.json con los datos de las 142 autoridades
   (usa el scraper de SERVEL + Cámara + Senado para poblar)
2. Crear src/pages/herramientas/quien-me-representa.astro
3. Crear src/components/CardAutoridad.astro (componente reutilizable)
4. Estilos: grid responsive, cards con foto, nombre, cargo, partido
5. Filtro por comuna con select dropdown
6. Agrupar resultados por nivel: Municipal > Regional > Nacional
7. Mobile-first: cards apiladas en móvil, grid 3 columnas en desktop
```

---

## Herramienta 2: Comparador de Comunas

### Qué hace
Permite seleccionar 2 o 3 comunas de la región y compararlas lado a lado en
indicadores clave: presupuesto total, gasto en personal (%), ejecución
presupuestaria, inversión per cápita, dependencia del FCM, población, y
cumplimiento de transparencia. Incluye gráficos de barras comparativos.

### Datos necesarios
```
src/data/comunas.json
```
Estructura:
```json
[
  {
    "id": "la-serena",
    "nombre": "La Serena",
    "provincia": "Elqui",
    "poblacion": 245000,
    "superficie_km2": 1893,
    "presupuesto": {
      "anio": 2026,
      "ingreso_total": 85000000000,
      "gasto_total": 82000000000,
      "gasto_personal": 42000000000,
      "gasto_personal_pct": 51.2,
      "inversion": 12000000000,
      "inversion_pct": 14.6,
      "fcm_recibido": 15000000000,
      "fcm_dependencia_pct": 17.6,
      "ejecucion_pct": 78.5
    },
    "transparencia": {
      "cumplimiento_pct": 85,
      "ultima_evaluacion": "2025-12",
      "fuente": "CPLT"
    },
    "alcalde": "Nombre del Alcalde",
    "partido_alcalde": "Partido X",
    "concejales_total": 8
  }
]
```

### Fuentes de datos
- Presupuestos: Portal de Transparencia de cada municipalidad + SINIM (Sistema
  Nacional de Información Municipal — sinim.cl)
- Población: INE (Censo + proyecciones)
- Transparencia: CPLT evaluaciones de transparencia activa
- Superficie: BCN datos enlazados

### Implementación en Astro

Archivo: `src/pages/herramientas/comparador-comunas.astro`

Componentes:
- `SelectorComunas.astro` — 2-3 dropdowns para elegir comunas
- `TablaComparativa.astro` — tabla lado a lado con los indicadores
- `GraficoBarras.astro` — Chart.js con barras agrupadas

```astro
---
import Layout from '../../layouts/Layout.astro';
import comunas from '../../data/comunas.json';
---

<Layout title="Comparador de Comunas">
  <section class="herramienta">
    <h1>Comparador de Comunas</h1>
    <p>Selecciona 2 o 3 comunas para comparar sus indicadores.</p>

    <div class="selectores">
      <select id="comuna-1" class="selector-comuna">
        <option value="">Comuna 1</option>
        {comunas.map(c => <option value={c.id}>{c.nombre}</option>)}
      </select>
      <span class="vs">vs</span>
      <select id="comuna-2" class="selector-comuna">
        <option value="">Comuna 2</option>
        {comunas.map(c => <option value={c.id}>{c.nombre}</option>)}
      </select>
      <button id="agregar-tercera">+ Agregar otra</button>
    </div>

    <div id="comparacion" hidden>
      <table id="tabla-comparacion"></table>
      <canvas id="grafico-presupuesto" width="600" height="300"></canvas>
    </div>
  </section>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <script define:vars={{ comunas }}>
    // Lógica de comparación: escuchar cambios en selectores,
    // construir tabla y gráfico Chart.js
  </script>
</Layout>
```

### Indicadores a comparar
| Indicador | Unidad | Interpretación |
|-----------|--------|----------------|
| Presupuesto total | $ CLP | Tamaño del municipio |
| Gasto en personal | % del total | > 60% = bandera roja |
| Ejecución presupuestaria | % | < 50% = preocupante |
| Inversión per cápita | $/habitante | Más alto = más inversión directa |
| Dependencia FCM | % | Más alto = menos autonomía |
| Cumplimiento transparencia | % | Evaluado por CPLT |
| Población | habitantes | Contexto |

### Instrucciones para Claude en VSC
```
1. Crear src/data/comunas.json con datos de las 15 comunas
   (scraper de SINIM + Portal Transparencia + CPLT)
2. Crear src/pages/herramientas/comparador-comunas.astro
3. Implementar tabla comparativa con colores condicionales:
   - Gasto personal > 60%: rojo
   - Ejecución < 50%: rojo
   - Transparencia < 50%: rojo
4. Gráfico Chart.js de barras agrupadas (presupuesto, inversión, personal)
5. Responsive: tabla se convierte en cards apiladas en móvil
6. Botón para agregar/quitar tercera comuna
7. Exportar comparación como imagen (html2canvas) o compartir por URL
```

---

## Herramienta 3: Calculadora de Participación Electoral

### Qué hace
Muestra la participación electoral histórica de cada comuna en las últimas
elecciones (municipales, regionales, parlamentarias, presidenciales). Incluye
tendencias, comparación con el promedio regional y nacional, y datos de votos
nulos/blancos. Permite explorar cuánto pesa el voto de cada comuna.

### Datos necesarios
```
src/data/elecciones.json
```
Estructura:
```json
[
  {
    "tipo": "Municipal",
    "anio": 2024,
    "comuna": "La Serena",
    "inscritos": 180000,
    "votantes": 85000,
    "participacion_pct": 47.2,
    "votos_validos": 82000,
    "votos_nulos": 2000,
    "votos_blancos": 1000,
    "nulos_blancos_pct": 3.5,
    "promedio_regional": 45.8,
    "promedio_nacional": 46.1
  }
]
```

### Fuentes de datos
- SERVEL: servel.cl → Resultados electorales por mesa/comuna
- Datos abiertos SERVEL: datos.servel.cl (cuando disponible)
- BCN: datos enlazados para histórico

### Elecciones a incluir
- Municipales: 2016, 2021, 2024
- Regionales (GORE): 2021, 2024
- Parlamentarias: 2017, 2021
- Presidenciales: 2017, 2021
- Plebiscitos: 2020, 2022, 2023

### Implementación en Astro

Archivo: `src/pages/herramientas/participacion-electoral.astro`

Componentes:
- `SelectorEleccion.astro` — filtro por tipo y año
- `MapaCalor.astro` — mapa simplificado de la región con colores por participación
- `GraficoTendencia.astro` — línea de tendencia por comuna
- `TablaRanking.astro` — ranking de comunas por participación

```astro
---
import Layout from '../../layouts/Layout.astro';
import elecciones from '../../data/elecciones.json';

const tipos = [...new Set(elecciones.map(e => e.tipo))];
const anios = [...new Set(elecciones.map(e => e.anio))].sort();
---

<Layout title="Participación Electoral">
  <section class="herramienta">
    <h1>Participación Electoral en Coquimbo</h1>
    <p>Explora cómo vota tu comuna y compara con el resto de la región.</p>

    <div class="filtros">
      <select id="tipo-eleccion">
        {tipos.map(t => <option value={t}>{t}</option>)}
      </select>
      <select id="anio-eleccion">
        {anios.map(a => <option value={a}>{a}</option>)}
      </select>
    </div>

    <!-- Ranking de comunas -->
    <div id="ranking"></div>

    <!-- Gráfico de tendencia -->
    <canvas id="grafico-tendencia" width="700" height="350"></canvas>

    <!-- Datos destacados -->
    <div id="datos-destacados" class="grid-stats"></div>
  </section>
</Layout>
```

### Métricas clave a mostrar
- Participación (%) por comuna con ranking
- Tendencia histórica (sube/baja)
- Votos nulos + blancos (%) — indicador de descontento
- "Peso del voto": cuántos votantes efectivos por cargo elegido
- Brecha con promedio regional y nacional
- Comuna con mayor/menor participación

### Instrucciones para Claude en VSC
```
1. Crear scraper SERVEL que descargue resultados por comuna
   (src/scrapers/servel_resultados.py)
2. Crear src/data/elecciones.json con histórico desde 2016
3. Crear src/pages/herramientas/participacion-electoral.astro
4. Gráfico Chart.js de líneas (tendencia por comuna seleccionada)
5. Tabla ranking con barras de progreso CSS (sin librería extra)
6. Cards de estadísticas destacadas: mayor participación, menor,
   mayor caída, mayor crecimiento
7. Colores: verde (>60%), amarillo (40-60%), rojo (<40%)
8. Responsive: gráfico se redimensiona, tabla se vuelve scrollable
```

---

## Herramienta 4: Línea de Tiempo Legislativa

### Qué hace
Visualiza los proyectos de ley que afectan a la Región de Coquimbo en una
línea de tiempo interactiva. Muestra en qué etapa está cada proyecto, quién
lo presentó (si es un parlamentario de la región), cómo votaron los
legisladores de Coquimbo, y links al texto completo.

### Datos necesarios
```
src/data/proyectos-ley.json
```
Estructura:
```json
[
  {
    "boletin": "12345-06",
    "titulo": "Modifica ley de aguas para zonas de escasez",
    "resumen": "Prioriza uso doméstico de agua en zonas declaradas de escasez hídrica...",
    "fecha_ingreso": "2025-03-15",
    "tipo": "Moción",
    "autores": ["Diputado X (Coquimbo)", "Diputado Y"],
    "camara_origen": "Cámara de Diputados",
    "etapa_actual": "Segundo trámite constitucional",
    "etapas": [
      {"nombre": "Ingreso", "fecha": "2025-03-15", "completada": true},
      {"nombre": "Comisión (1er trámite)", "fecha": "2025-05-20", "completada": true},
      {"nombre": "Sala Cámara", "fecha": "2025-07-10", "completada": true},
      {"nombre": "Comisión Senado (2do trámite)", "fecha": "2025-09-01", "completada": false},
      {"nombre": "Sala Senado", "fecha": null, "completada": false},
      {"nombre": "Promulgación", "fecha": null, "completada": false}
    ],
    "urgencia": "Simple",
    "temas": ["agua", "medio ambiente", "Coquimbo"],
    "relevancia_regional": "directa",
    "votos_coquimbo": [
      {"parlamentario": "Diputado X", "voto": "a_favor"},
      {"parlamentario": "Diputado Y", "voto": "a_favor"},
      {"parlamentario": "Diputado Z", "voto": "en_contra"}
    ],
    "links": {
      "camara": "https://www.camara.cl/legislacion/ProyectosDeLey/tramitacion.aspx?prmID=12345",
      "bcn": "https://bcn.cl/..."
    }
  }
]
```

### Fuentes de datos
- Cámara de Diputados: opendata.camara.cl (API XML de proyectos y votaciones)
- Senado: senado.cl/appsenado (tramitación)
- BCN: bcn.cl/tramitacion (estado consolidado)

### Criterios de relevancia regional
Un proyecto es relevante para Coquimbo si:
1. Fue presentado por un parlamentario de la región (distritos 5-6, circunscripción 4)
2. Menciona explícitamente a Coquimbo, sus comunas o la región
3. Trata temas críticos regionales: agua/sequía, minería, pesca artesanal,
   agricultura, astronomía/contaminación lumínica, zonas rezagadas
4. Es de interés nacional con impacto regional diferenciado

### Implementación en Astro

Archivo: `src/pages/herramientas/proyectos-de-ley.astro`

Componentes:
- `Timeline.astro` — línea de tiempo vertical con etapas
- `FiltroProyectos.astro` — filtros por tema, autor, etapa, urgencia
- `CardProyecto.astro` — resumen expandible con votos y links
- `VotosCoquimbo.astro` — cómo votó cada parlamentario regional

```astro
---
import Layout from '../../layouts/Layout.astro';
import proyectos from '../../data/proyectos-ley.json';

const temas = [...new Set(proyectos.flatMap(p => p.temas))].sort();
const etapas = [...new Set(proyectos.map(p => p.etapa_actual))];
---

<Layout title="Proyectos de Ley — Región de Coquimbo">
  <section class="herramienta">
    <h1>Proyectos de Ley que afectan a Coquimbo</h1>
    <p>Sigue la tramitación de los proyectos relevantes para la región.</p>

    <div class="filtros">
      <select id="filtro-tema">
        <option value="">Todos los temas</option>
        {temas.map(t => <option value={t}>{t}</option>)}
      </select>
      <select id="filtro-etapa">
        <option value="">Todas las etapas</option>
        {etapas.map(e => <option value={e}>{e}</option>)}
      </select>
      <input type="search" id="buscar" placeholder="Buscar por título o boletín...">
    </div>

    <div id="lista-proyectos">
      {proyectos.map(p => (
        <article class="card-proyecto">
          <div class="header-proyecto">
            <span class="boletin">Boletín {p.boletin}</span>
            <span class={`urgencia urgencia-${p.urgencia.toLowerCase()}`}>
              {p.urgencia}
            </span>
          </div>
          <h3>{p.titulo}</h3>
          <p>{p.resumen}</p>

          <!-- Timeline mini -->
          <div class="timeline-mini">
            {p.etapas.map(e => (
              <div class={`etapa ${e.completada ? 'completada' : ''}`}>
                <span class="dot"></span>
                <span class="nombre">{e.nombre}</span>
              </div>
            ))}
          </div>

          <!-- Votos Coquimbo -->
          <div class="votos-coquimbo">
            <h4>Cómo votaron nuestros parlamentarios:</h4>
            {p.votos_coquimbo?.map(v => (
              <span class={`voto voto-${v.voto}`}>
                {v.parlamentario}: {v.voto === 'a_favor' ? '✓ A favor' :
                  v.voto === 'en_contra' ? '✗ En contra' : '— Ausente'}
              </span>
            ))}
          </div>
        </article>
      ))}
    </div>
  </section>
</Layout>
```

### Instrucciones para Claude en VSC
```
1. Crear scraper Cámara que consuma API XML de proyectos
   (src/scrapers/camara_proyectos.py — ya documentado en 05-scrapers.md)
2. Crear scraper de votaciones por boletín
   (src/scrapers/camara_votaciones.py)
3. Script que filtre proyectos relevantes para Coquimbo
   (src/scripts/filtrar_proyectos_region.py)
4. Crear src/data/proyectos-ley.json con datos procesados
5. Crear src/pages/herramientas/proyectos-de-ley.astro
6. Timeline CSS puro (vertical, dots conectados con línea)
7. Cards expandibles con detalles y votos
8. Filtros combinables (tema + etapa + búsqueda texto)
9. Badge de urgencia con colores:
   - Sin urgencia: gris
   - Simple: azul
   - Suma: naranja
   - Discusión inmediata: rojo
10. Auto-actualización semanal via GitHub Actions
```

---

## Orden de implementación recomendado

| Fase | Herramienta | Dificultad | Datos disponibles | Impacto |
|------|-------------|------------|-------------------|---------|
| 1 | Buscador de autoridades | Baja | Parcial (SERVEL + APIs) | Alto |
| 2 | Comparador de comunas | Media | Parcial (SINIM + CPLT) | Alto |
| 3 | Participación electoral | Media | Alta (SERVEL histórico) | Medio |
| 4 | Línea de tiempo legislativa | Alta | Alta (Cámara API XML) | Alto |

### Fase 1 primero porque:
- Los datos de autoridades son los más fáciles de recopilar
- Es la herramienta que más tráfico genera ("¿quién es mi alcalde?")
- No requiere scrapers complejos (mucho se puede hacer manual al inicio)
- Sirve como base para las demás herramientas

---

## Estructura de archivos en el proyecto

```
src/
├── data/
│   ├── autoridades.json          ← Herramienta 1
│   ├── comunas.json              ← Herramienta 2
│   ├── elecciones.json           ← Herramienta 3
│   └── proyectos-ley.json        ← Herramienta 4
├── pages/
│   └── herramientas/
│       ├── index.astro           ← Índice de herramientas + PDFs
│       ├── quien-me-representa.astro
│       ├── comparador-comunas.astro
│       ├── participacion-electoral.astro
│       └── proyectos-de-ley.astro
├── components/
│   ├── CardAutoridad.astro
│   ├── SelectorComunas.astro
│   ├── TablaComparativa.astro
│   ├── GraficoBarras.astro
│   ├── Timeline.astro
│   └── CardProyecto.astro
├── layouts/
│   └── Layout.astro
└── styles/
    └── herramientas.css
```

---

## Cómo trabajar esto en VS Code con Claude

### Setup inicial
```bash
# En la carpeta del proyecto
cd oprc-coquimbo

# Claude ya tiene el contexto en CLAUDE.md
# Pídele que empiece por la Herramienta 1
```

### Prompts sugeridos para Claude en VSC

**Herramienta 1:**
```
Lee docs/06-herramientas-interactivas.md, sección "Herramienta 1".
Crea el componente Buscador de Autoridades con los archivos indicados.
Empieza por crear src/data/autoridades.json con datos reales
de las 15 comunas usando las fuentes documentadas.
```

**Herramienta 2:**
```
Lee docs/06-herramientas-interactivas.md, sección "Herramienta 2".
Crea el Comparador de Comunas. Necesito los datos de presupuesto
de las 15 comunas. Usa SINIM o Portal Transparencia como fuente.
Incluye Chart.js para los gráficos.
```

**Herramienta 3:**
```
Lee docs/06-herramientas-interactivas.md, sección "Herramienta 3".
Crea la Calculadora de Participación Electoral. Empieza por el
scraper SERVEL para descargar resultados por comuna desde 2016.
```

**Herramienta 4:**
```
Lee docs/06-herramientas-interactivas.md, sección "Herramienta 4".
Crea la Línea de Tiempo Legislativa. Usa el scraper de la Cámara
(docs/05-scrapers.md) para obtener proyectos y filtra los
relevantes para Coquimbo.
```

### Tips para trabajar con Claude en VSC
1. **Un componente a la vez**: no pidas las 4 herramientas juntas
2. **Datos primero**: pide que cree el JSON de datos antes del frontend
3. **Itera**: pide primero una versión funcional mínima, luego mejora
4. **Prueba local**: `npm run dev` después de cada componente
5. **Commit frecuente**: haz commit después de cada herramienta funcional
