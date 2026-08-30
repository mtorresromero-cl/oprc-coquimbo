# 07 — Herramienta Electoral Completa

## Problema actual

La página `/herramientas/participacion-electoral/` solo muestra porcentajes
de participación. Tenemos datos electorales completos desde 1989 a 2025 y
la página debe mostrar TODO: resultados, candidatos, votos, padrones y
comparaciones por comuna.

## Qué debe tener la herramienta electoral

La página actual de participación debe expandirse (o reemplazarse) con una
herramienta electoral completa que tenga estas secciones:

---

## SECCIÓN 1: Resultados Electorales

### Qué mostrar
Para cada elección, mostrar los **resultados completos**: quién ganó, cuántos
votos sacó cada candidato, porcentaje, partido, y si fue electo o no.

### Tipos de elección a cubrir
- **Presidenciales**: 1989, 1993, 1999, 2005, 2009, 2013, 2017, 2021
  (incluir segunda vuelta cuando aplique)
- **Parlamentarias (Diputados)**: desde 1989, distritos que correspondan
  a la Región de Coquimbo (hoy distritos 5 y 6, antes otros números)
- **Parlamentarias (Senadores)**: circunscripción Coquimbo, cada 8 años
  con renovación parcial
- **Municipales (Alcaldes)**: desde 1992, las 15 comunas
- **Municipales (Concejales)**: desde 1992, las 15 comunas
- **Consejeros Regionales (CORE)**: desde 2013 (elección directa)
- **Gobernadores Regionales**: 2021, 2024
- **Plebiscitos**: 1988, 2020, 2022, 2023

### Estructura de datos para resultados
```json
{
  "eleccion": {
    "tipo": "Alcalde",
    "anio": 2024,
    "fecha": "2024-10-27",
    "segunda_vuelta": false
  },
  "territorio": {
    "comuna": "La Serena",
    "provincia": "Elqui",
    "distrito": 5,
    "circunscripcion": "Elqui Costa"
  },
  "padron": {
    "inscritos": 185432,
    "votantes": 92716,
    "participacion_pct": 50.0,
    "votos_validos": 89543,
    "votos_nulos": 2100,
    "votos_blancos": 1073
  },
  "candidatos": [
    {
      "nombre": "Candidato A",
      "partido": "Partido X",
      "pacto": "Pacto Y",
      "votos": 45230,
      "porcentaje": 50.5,
      "electo": true,
      "incumbente": false
    },
    {
      "nombre": "Candidato B",
      "partido": "Independiente",
      "pacto": null,
      "votos": 35120,
      "porcentaje": 39.2,
      "electo": false,
      "incumbente": true
    }
  ]
}
```

### Componente de resultados — diseño

```
┌──────────────────────────────────────────────────────────┐
│  ALCALDE · La Serena · 2024                              │
│  ──────────────────────────────────────────               │
│                                                          │
│  ✓ Candidato A ████████████████████░░░░░░  50.5%  45,230│
│    Partido X · Pacto Y                                   │
│                                                          │
│    Candidato B ███████████████░░░░░░░░░░░  39.2%  35,120│
│    Independiente                                         │
│                                                          │
│    Candidato C ████░░░░░░░░░░░░░░░░░░░░░  10.3%   9,193│
│    Partido Z · Pacto W                                   │
│                                                          │
│  ──────────────────────────────────────────               │
│  Padrón: 185,432 · Votantes: 92,716 (50.0%)             │
│  Válidos: 89,543 · Nulos: 2,100 · Blancos: 1,073        │
└──────────────────────────────────────────────────────────┘
```

Cada candidato tiene una **barra horizontal proporcional** con color del
partido/pacto. El candidato electo se marca con ✓ y se destaca visualmente.

---

## SECCIÓN 2: Explorador por Comuna

### Qué mostrar
Seleccionas una comuna y ves **toda su historia electoral**: todos los
alcaldes que ha tenido, todos los concejales, evolución del padrón,
participación histórica, y qué partidos han dominado.

### Página por comuna
Ruta: `/herramientas/electoral/comuna/[slug]/`

```
┌──────────────────────────────────────────────────────────┐
│  HISTORIA ELECTORAL DE LA SERENA                         │
│                                                          │
│  📊 Padrón actual: 185,432 inscritos                     │
│  📈 Crecimiento padrón desde 1989: +120%                 │
│  🗳️ Participación promedio: 52.3%                        │
│                                                          │
│  ── ALCALDES ──────────────────────────────               │
│  2024-2028  Candidato A (Partido X)                      │
│  2021-2024  Candidato B (Independiente)                  │
│  2016-2021  Candidato C (Partido Y)                      │
│  2012-2016  Candidato D (Partido Z)                      │
│  ...hasta 1992                                           │
│                                                          │
│  ── ÚLTIMA ELECCIÓN MUNICIPAL (2024) ──────              │
│  [Tabla completa de resultados con barras]                │
│                                                          │
│  ── EVOLUCIÓN PARTICIPACIÓN ──────────────               │
│  [Gráfico de línea 1989-2025]                            │
│                                                          │
│  ── DOMINIO POR PARTIDO ─────────────────                │
│  [Gráfico de áreas apiladas por elección]                │
└──────────────────────────────────────────────────────────┘
```

---

## SECCIÓN 3: Comparador Electoral entre Comunas

### Qué mostrar
Seleccionas 2-3 comunas y comparas lado a lado: participación, padrón,
partido dominante, resultados de la última elección, tendencias.

### Métricas a comparar
| Métrica | Descripción |
|---------|-------------|
| Padrón | Inscritos totales y crecimiento |
| Participación | % en última elección + tendencia |
| Votos nulos/blancos | % (indicador de descontento) |
| Partido dominante alcaldía | Qué partido ha ganado más veces |
| Competitividad | Diferencia entre 1° y 2° lugar |
| Concejales por partido | Distribución actual |

---

## SECCIÓN 4: Padrón Electoral

### Qué mostrar
Evolución del padrón electoral por comuna desde 1989. Con el cambio a
inscripción automática (2012) hay un salto enorme que debe marcarse.

### Datos
```json
{
  "comuna": "La Serena",
  "padron_historico": [
    {"anio": 1989, "inscritos": 68000, "tipo_inscripcion": "voluntaria"},
    {"anio": 1993, "inscritos": 75000, "tipo_inscripcion": "voluntaria"},
    {"anio": 2012, "inscritos": 155000, "tipo_inscripcion": "automatica"},
    {"anio": 2024, "inscritos": 185432, "tipo_inscripcion": "automatica"}
  ]
}
```

### Visualización
- Gráfico de línea con marca vertical en 2012 ("Inscripción automática")
- Tabla con crecimiento absoluto y porcentual entre elecciones
- Ranking de comunas por tamaño de padrón

---

## SECCIÓN 5: Plebiscitos

### Qué mostrar
Resultados de los plebiscitos con datos por comuna: 1988 (Sí/No),
2020 (Apruebo/Rechazo), 2022 (Apruebo/Rechazo), 2023 (A favor/En contra).

### Diseño
Cada plebiscito como card con barras de resultado por comuna.
Mapa de calor simplificado mostrando cómo votó cada comuna.

---

## NAVEGACIÓN PROPUESTA

La herramienta electoral completa debería tener pestañas o subrutas:

```
/herramientas/electoral/                    ← Vista general + últimas elecciones
/herramientas/electoral/resultados/         ← Buscar por tipo de elección y año
/herramientas/electoral/comuna/[slug]/      ← Historia de una comuna
/herramientas/electoral/comparador/         ← Comparar 2-3 comunas
/herramientas/electoral/padron/             ← Evolución del padrón
/herramientas/electoral/plebiscitos/        ← Resultados de plebiscitos
```

O bien, una sola página con pestañas/tabs que carguen cada sección
dinámicamente (más simple para Astro estático).

### Opción recomendada: Tabs en una página
```
/herramientas/participacion-electoral/

[Resultados] [Por Comuna] [Comparar] [Padrón] [Plebiscitos] [Participación]
```

La pestaña "Participación" conserva lo que ya existe hoy.
Las demás se agregan con el contenido nuevo.

---

## ESTRUCTURA DE ARCHIVOS DE DATOS

Los datos electorales deben organizarse así para que sean manejables:

```
src/data/electoral/
├── metadata.json                 ← Lista de todas las elecciones
├── padron/
│   └── padron_historico.json     ← Padrón por comuna y año
├── presidenciales/
│   ├── 1989.json
│   ├── 1993.json
│   └── ...2021.json
├── diputados/
│   ├── 1989.json
│   └── ...2025.json
├── senadores/
│   ├── 1989.json
│   └── ...2021.json
├── alcaldes/
│   ├── 1992.json
│   └── ...2024.json
├── concejales/
│   ├── 1992.json
│   └── ...2024.json
├── core/
│   ├── 2013.json
│   └── ...2024.json
├── gobernador/
│   ├── 2021.json
│   └── 2024.json
└── plebiscitos/
    ├── 1988.json
    ├── 2020.json
    ├── 2022.json
    └── 2023.json
```

Cada archivo JSON sigue la estructura de la Sección 1.

---

## COMPONENTES ASTRO A CREAR

```
src/components/electoral/
├── ResultadoEleccion.astro       ← Card con barras de resultado
├── BarraCandidato.astro          ← Barra horizontal proporcional
├── SelectorEleccion.astro        ← Dropdown tipo + año
├── SelectorComuna.astro          ← Dropdown de las 15 comunas
├── TablaResultados.astro         ← Tabla expandible de candidatos
├── GraficoPadron.astro           ← Chart.js línea de padrón
├── GraficoPartidos.astro         ← Chart.js áreas apiladas
├── TimelineAlcaldes.astro        ← Línea de tiempo de alcaldes
├── ComparadorElectoral.astro     ← Comparación lado a lado
├── CardPlebiscito.astro          ← Resultado de plebiscito
└── TabsElectoral.astro           ← Navegación por pestañas
```

---

## PROMPT PARA CLAUDE EN VSC

Copia y pega esto en Claude en VSC:

```
Lee el archivo docs/07-herramienta-electoral-completa.md completo.

La página actual en src/pages/herramientas/participacion-electoral/
solo muestra participación. Necesito expandirla para que sea una
herramienta electoral COMPLETA con todos los datos que ya tenemos
desde 1989 a 2025.

Tenemos los datos electorales en [INDICAR DÓNDE ESTÁN TUS JSONs].

Necesito que:

1. REORGANICES los datos en src/data/electoral/ según la estructura
   del documento (un JSON por tipo de elección y año)

2. AGREGUES pestañas/tabs a la página actual:
   - Resultados: selector de tipo de elección + año, muestra
     candidatos con barras horizontales proporcionales
   - Por Comuna: seleccionar comuna, ver toda su historia electoral
     (alcaldes, evolución padrón, participación)
   - Comparar: elegir 2-3 comunas y ver lado a lado
   - Padrón: evolución del padrón por comuna con gráfico
   - Plebiscitos: resultados del 88, 2020, 2022, 2023 por comuna
   - Participación: lo que ya existe hoy

3. CREES los componentes de src/components/electoral/ uno por uno

4. Cada candidato debe mostrarse con barra horizontal coloreada,
   nombre, partido, votos y porcentaje. El electo se marca.

Empieza por la pestaña de Resultados — es la más importante.
No borres la funcionalidad de participación que ya existe,
solo agrégala como una pestaña más.
```

---

## COLORES POR PARTIDO (para las barras de candidatos)

```javascript
const COLORES_PARTIDOS = {
  // Oficialismo actual
  'Frente Amplio':        '#E53E3E',
  'Partido Comunista':    '#C53030',
  'Partido Socialista':   '#E91E63',
  'PPD':                  '#2196F3',
  'Partido Radical':      '#7B1FA2',
  'Democracia Cristiana': '#4CAF50',

  // Oposición
  'RN':                   '#1565C0',
  'UDI':                  '#0D47A1',
  'Evópoli':              '#42A5F5',
  'Partido Republicano':  '#FF6F00',

  // Otros
  'Independiente':        '#9E9E9E',
  'Partido de la Gente':  '#FF9800',
  'Partido Humanista':    '#66BB6A',
  'Partido Ecologista':   '#2E7D32',

  // Históricos
  'Concertación':         '#1976D2',
  'Alianza':              '#283593',
  'Chile Vamos':          '#1565C0',
  'Apruebo Dignidad':     '#D32F2F',

  // Default
  'default':              '#78909C'
};
```

---

## NOTAS IMPORTANTES PARA LA IMPLEMENTACIÓN

1. **No borres lo existente**: la funcionalidad de participación que ya
   está debe conservarse como una pestaña más

2. **Datos progresivos**: si los JSONs son muy grandes, considera
   lazy-loading por pestaña (cargar datos solo cuando el usuario
   abre esa sección)

3. **Responsive obligatorio**: las barras de candidatos y tablas
   deben funcionar en móvil

4. **Histórico pre-2012**: antes de 2012 la inscripción era voluntaria,
   eso afecta las comparaciones de participación. Marcar visualmente

5. **Distritos cambiaron**: los distritos de la región cambiaron entre
   elecciones (antes de 2017 eran distintos). Los datos deben reflejarlo

6. **Concejales**: son muchos candidatos por comuna. Mostrar tabla
   colapsable, expandible al hacer clic

7. **SEO**: cada comuna debería tener su propia URL si es posible
   (`/electoral/comuna/la-serena/`) para que sea indexable
