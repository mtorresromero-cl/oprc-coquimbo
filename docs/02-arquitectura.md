# 02 — Arquitectura Técnica

## Visión general

```
┌─────────────────────────────────────────────────────────┐
│                     FUENTES DE DATOS                     │
│  Cámara · Senado · InfoProbidad · Transparencia · SERVEL │
│  BCN · datos.gob.cl · GORE Coquimbo                     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   CAPA DE RECOLECCIÓN                    │
│           Python (scrapers + API clients)                │
│        Ejecutados por GitHub Actions (cron)              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   CAPA DE DATOS                          │
│          SQLite (dev) / PostgreSQL (prod)                │
│     Archivos JSON procesados en /data                    │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                 CAPA DE PRESENTACIÓN                     │
│              Astro (sitio estático + SSR)                │
│         Gráficos: Chart.js o D3.js                      │
│         Mapas: Leaflet + GeoJSON región                  │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                      DEPLOY                              │
│     Vercel / Cloudflare Pages / Netlify (gratis)         │
│     Rebuild automático ante push a main                  │
└─────────────────────────────────────────────────────────┘
```

---

## Stack recomendado

### Lenguajes y frameworks

| Componente       | Tecnología         | Por qué                                      |
|------------------|--------------------|----------------------------------------------|
| Scrapers         | Python 3.11+       | Mejor ecosistema para scraping y datos        |
| HTTP client      | httpx              | Async, moderno, mejor que requests            |
| Scraping HTML    | BeautifulSoup4     | Simple y robusto para HTML estático           |
| Scraping dinámico| Playwright         | Para sitios que requieren JS (InfoProbidad)   |
| Parsing XML      | lxml               | Rápido para APIs XML (Cámara, Senado)         |
| Datos            | pandas             | Limpieza y transformación                     |
| Base de datos    | SQLite → PostgreSQL| SQLite para dev, Postgres en producción       |
| ORM              | SQLModel           | Simple, basado en SQLAlchemy + Pydantic       |
| Sitio web        | Astro              | Rápido, genera estático, fácil de hostear     |
| UI components    | Tailwind CSS       | Utility-first, sin overhead                   |
| Gráficos         | Chart.js           | Simple y liviano para dashboards              |
| Mapas            | Leaflet            | Open source, sin API key                      |
| CI/CD            | GitHub Actions     | Gratis para repos públicos                    |
| Deploy           | Vercel             | Gratis tier, deploy automático                |
| Newsletter       | Resend             | API simple, 3k emails/mes gratis              |

### Alternativa más simple (si el equipo es chico)

Si no hay un equipo de desarrollo dedicado, se puede simplificar:

| Componente       | Alternativa simple | Ventaja                                       |
|------------------|--------------------|-----------------------------------------------|
| Sitio web        | Hugo               | Aún más simple, solo Markdown + templates     |
| Base de datos    | JSON files          | Sin servidor, versionables en Git            |
| Gráficos         | Mermaid / SVG      | Sin JS runtime                                |
| Newsletter       | Buttondown          | Soporta Markdown, RSS automático             |

---

## Pipeline de datos

### Flujo de un scraper típico

```
1. GitHub Actions dispara el cron (ej: todos los lunes 8am)
2. Script Python se ejecuta:
   a. Consulta la fuente (API o scraping)
   b. Parsea la respuesta
   c. Compara con datos existentes (detecta cambios)
   d. Guarda datos nuevos en /data y en la BD
   e. Si hay cambios relevantes, genera un "evento"
3. Si hubo cambios:
   a. Se regenera el sitio (Astro build)
   b. Se despliega automáticamente
   c. Opcionalmente se envía un tweet/newsletter
```

### Estructura de archivos de datos

```
data/
├── raw/                    ← datos crudos descargados
│   ├── camara/
│   │   ├── votaciones_2024.xml
│   │   └── votaciones_2025.xml
│   ├── senado/
│   ├── servel/
│   └── transparencia/
├── processed/              ← datos limpios y normalizados
│   ├── autoridades.json    ← catálogo maestro
│   ├── votaciones.json
│   ├── asistencia.json
│   ├── patrimonio.json
│   └── presupuestos.json
└── db/
    └── oprc.sqlite         ← base de datos local
```

---

## GitHub Actions — Ejemplo de workflow

```yaml
# .github/workflows/update-data.yml
name: Actualizar datos

on:
  schedule:
    - cron: '0 12 * * 1'  # Todos los lunes a las 9am Chile
  workflow_dispatch:        # También manual

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r scrapers/requirements.txt
      - run: python scrapers/run_all.py
      - name: Commit datos actualizados
        run: |
          git config user.name "OPRC Bot"
          git config user.email "bot@oprcoquimbo.cl"
          git add data/
          git diff --staged --quiet || git commit -m "datos: actualización automática $(date +%Y-%m-%d)"
          git push

  build:
    needs: scrape
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
        working-directory: site
      - run: npm run build
        working-directory: site
      - name: Deploy
        uses: # acción de deploy según hosting
```

---

## Hosting y costos

Todo el stack puede funcionar con tiers gratuitos:

| Servicio          | Tier gratuito                        |
|-------------------|--------------------------------------|
| GitHub            | Repos públicos ilimitados            |
| GitHub Actions    | 2,000 min/mes para repos públicos    |
| Vercel            | 100GB bandwidth, builds ilimitados   |
| Cloudflare Pages  | Ilimitado para sitios estáticos      |
| Resend            | 3,000 emails/mes                     |
| SQLite            | Archivo local, sin costo             |

---

## Seguridad y consideraciones legales

- Todos los datos son **públicos por ley** (Ley 20.285 de Transparencia)
- Las APIs legislativas son **explícitamente abiertas** y sin restricción de licencia
- Respetar `robots.txt` en los sitios que lo tengan
- Incluir rate limiting en scrapers (no más de 1 request/segundo)
- Atribuir fuentes en el sitio
- No almacenar datos personales más allá de lo que las fuentes publican
