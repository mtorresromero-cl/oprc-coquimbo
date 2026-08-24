# CLAUDE.md — Contexto para Claude en VSC

## Qué es este proyecto

Rediseño del Observatorio Político Región de Coquimbo (oprcoquimbo.cl). El sitio actual es un WordPress roto. Lo reemplazamos por una plataforma moderna basada en datos abiertos.

## Documentación

Leé los docs en este orden antes de implementar:

1. `docs/01-fuentes-de-datos.md` — De dónde vienen los datos
2. `docs/02-arquitectura.md` — Stack técnico y pipeline
3. `docs/03-roadmap.md` — Plan de trabajo por fases (cada fase tiene instrucciones específicas para vos)
4. `docs/04-modelos-de-datos.md` — Esquema SQL completo de la BD
5. `docs/05-scrapers.md` — Guía de implementación de cada scraper

## Convenciones

- **Python**: 3.11+, type hints, docstrings en español
- **Scrapers**: heredar de `BaseScraper` en `scrapers/base.py`
- **Rate limiting**: nunca más de 1 req/s por fuente
- **BD**: SQLite en `data/db/oprc.sqlite`, esquema en doc 04
- **Datos procesados**: JSON en `data/processed/`
- **Sitio web**: Astro + Tailwind en `site/`
- **Commits**: en español, prefijos `datos:`, `scraper:`, `site:`, `docs:`

## Estado actual

El proyecto está en fase de documentación. La estructura está lista para empezar la Fase 0 del roadmap (setup técnico).

## Cómo empezar

Decile a Claude: "Leé docs/03-roadmap.md y empecemos con la Fase 0"
