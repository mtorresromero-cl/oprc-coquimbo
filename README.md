# OPRC — Observatorio Político Región de Coquimbo

## Qué es este proyecto

Rediseño completo del sitio [oprcoquimbo.cl](https://www.oprcoquimbo.cl), que actualmente está desactualizado y con errores técnicos (WordPress roto, tablas de BD faltantes, PHP deprecado).

El objetivo es reemplazarlo por una plataforma moderna, automatizada y basada en datos abiertos, que permita a cualquier ciudadano hacer seguimiento a las autoridades políticas de la Región de Coquimbo.

## Autoridades que se monitorean

| Cargo                | Cantidad | Fuente principal         |
|----------------------|----------|--------------------------|
| Concejales           | 100      | Transparencia municipal  |
| Alcaldes             | 15       | Transparencia municipal  |
| Consejeros regionales| 16       | GORE Coquimbo            |
| Diputados            | 7        | Cámara de Diputados      |
| Senadores            | 3        | Senado                   |
| Gobernadora regional | 1        | GORE Coquimbo            |

## Estructura del proyecto

```
oprc-coquimbo/
├── README.md                  ← este archivo
├── docs/
│   ├── 01-fuentes-de-datos.md ← todas las fuentes públicas disponibles
│   ├── 02-arquitectura.md     ← stack técnico y pipeline
│   ├── 03-roadmap.md          ← plan de trabajo por fases
│   ├── 04-modelos-de-datos.md ← estructura de la base de datos
│   └── 05-scrapers.md         ← guía de cada scraper/API
├── scrapers/                  ← scripts de recolección de datos
├── data/                      ← datos crudos y procesados
└── site/                      ← código del sitio web
```

## Cómo usar este repo con Claude en VSC

1. Abrí la carpeta `oprc-coquimbo` en VS Code
2. Pedile a Claude que lea los docs en orden (01 → 05)
3. Arrancá por la fase que quieras del roadmap (`docs/03-roadmap.md`)
4. Cada doc tiene contexto suficiente para que Claude pueda implementar directamente

## Links clave

- Sitio actual: https://www.oprcoquimbo.cl
- Portal Transparencia: https://www.portaltransparencia.cl
- SERVEL datos abiertos: https://www.servel.cl/centro-de-datos/estadisticas-de-datos-abiertos-4zg/
- Senado datos abiertos: https://www.senado.cl/transparencia/datos-abiertos-legislativos
- Cámara datos abiertos: https://www.camara.cl/transparencia/datosAbiertos.aspx
- BCN datos enlazados: https://datos.bcn.cl/es/
- datos.gob.cl: https://datos.gob.cl
- InfoProbidad: https://www.infoprobidad.cl
- InfoTransparencia: https://www.infotransparencia.cl
