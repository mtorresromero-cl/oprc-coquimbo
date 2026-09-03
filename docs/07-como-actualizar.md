# 07 — Cómo actualizar el sitio (guía práctica)

Guía paso a paso para las dos cosas que normalmente hay que hacer: **subir un
artículo/noticia al blog** y **actualizar los datos** (votaciones, gastos,
delincuencia, etc.). No repite lo que ya está en `02-arquitectura.md` o
`05-scrapers.md` — es la versión "qué hago hoy, paso a paso".

## 0. Dónde está todo

- **Repositorio (editar código, datos, blog, disparar actualizaciones):** https://github.com/mtorresromero-cl/oprc-coquimbo — entrar con la cuenta de GitHub `migueltorresromero`.
- **Sitio en vivo:** https://www.oprcoquimbo.cl — ya es el sitio nuevo (Astro), el dominio real quedó apuntado a Cloudflare Pages.
- **URL alternativa (mismo sitio, dominio de Cloudflare Pages):** https://oprc-coquimbo.pages.dev

Sobre credenciales: no hay contraseña de "editor" del sitio — todo se
edita subiendo archivos al repositorio de GitHub (sección 3). Lo único
con credenciales propias es la cuenta de GitHub (acceso al repo) y la
cuenta de Cloudflare (dueña del dominio y del proyecto Pages, por si
hay que tocar DNS o certificados) — esas las administra directamente
quien tenga acceso a esas cuentas, no quedan en este repositorio.

---

## 1. Subir un artículo al blog

Los artículos son archivos de texto (Markdown), no se editan desde una web
tipo WordPress — se editan como archivos en el repositorio de GitHub.

**Dónde están:** `site/src/content/blog/`, uno por artículo.

**Cómo se llama el archivo:** `AAAA-MM-DD-titulo-corto.md` (la fecha al
principio es solo convención de orden, no decide la fecha publicada — esa
va adentro del archivo).

**Formato de un artículo** (copiar la estructura de cualquier archivo
existente en esa carpeta):

```markdown
---
titulo: "Título del artículo, puede llevar un emoji"
fecha: 2026-09-03
resumen: "1-2 frases que aparecen en la lista de artículos y en redes."
autor: "OPRC"
imagenDestacada: "/blog/AAAA-MM-DD-titulo-corto/destacada.webp"
---

Acá va el cuerpo del artículo, en Markdown normal: `## Subtítulos`,
**negrita**, listas numeradas, enlaces `[texto](url)`, etc.
```

**La imagen destacada:** se sube como archivo a `site/public/blog/AAAA-MM-DD-titulo-corto/destacada.webp`
(mismo nombre de carpeta que en `imagenDestacada:`). Si no tienes el archivo
en `.webp`, cualquier imagen sirve — conviene convertirla para que pese menos,
pero no es obligatorio.

**Cómo publicarlo:** agregar el archivo `.md` (y la imagen) y subirlo a
`main` en GitHub (ver sección 3, "cómo llega un cambio a producción" — es
el mismo proceso que cualquier otro cambio del sitio). No hace falta tocar
código ni correr nada — Astro lee esa carpeta automáticamente al construir
el sitio.

---

## 2. Actualizar los datos (votaciones, gastos, asistencia, delincuencia, etc.)

Los datos **no se cargan a mano** — los trae un programa (scraper) desde la
fuente oficial (camara.cl, senado.cl, transparencia municipal, etc.) y los
deja listos en `data/processed/*.json`, que es lo que lee el sitio.

### Cómo actualizarlos (la forma normal)

**Ya es automático.** Todos los lunes a las 9am (hora de Chile) corre solo,
sin que nadie tenga que hacer nada — ver
[Actions → Actualizar datos](https://github.com/mtorresromero-cl/oprc-coquimbo/actions/workflows/actualizar-datos.yml)
en GitHub para ver el historial de corridas.

### Cómo actualizarlos manualmente, fuera de ese horario

1. Ir a esa misma página de Actions: **Actions → Actualizar datos → Run workflow → Run workflow** (botón verde, rama `main`).
2. Corre en los servidores de GitHub — se puede cerrar la pestaña, el navegador, o el computador, y sigue corriendo solo.
3. Tarda **varias horas** (~3 horas es lo normal) — la mayor parte es el scraper de votaciones de la Cámara, que a propósito va lento (una petición cada pocos segundos) para no ser bloqueado por el sitio de la Cámara.
4. Cuando termina, el propio workflow hace un commit a `main` con los datos nuevos ("datos: actualización automática AAAA-MM-DD") y el sitio se reconstruye y despliega solo (ver sección 3).

**Ojo:** si en el medio alguien más hace un commit a `main` (por ejemplo, un cambio de diseño), el commit automático de datos puede fallar al final por conflicto de git ("rejected, fetch first"). Si eso pasa, los datos scrapeados se pierden (quedaban solo en el servidor temporal de GitHub) y hay que volver a correr el workflow. Por eso: evitar pushear a `main` mientras este workflow está corriendo, si se puede.

### Qué trae cada scraper (por si un dato específico no aparece)

| Scraper | Qué trae |
|---|---|
| `senado.py` / `senado_asistencia.py` / `senado_mociones.py` | Votos, asistencia y mociones de los 3 senadores de la región |
| `camara_mociones.py` / `camara_asistencia.py` / `camara_votaciones.py` | Lo mismo para los 7 diputados |
| `transparencia_municipal.py` | Datos de los 15 municipios vía Ley de Transparencia |
| `personal_municipal.py` | Dotación municipal |
| `infoprobidad.py` | Declaraciones de patrimonio e intereses |
| `core_coquimbo.py` | Votos y asistencia del Consejo Regional |
| `delincuencia_cead.py` | Casos policiales por comuna |

Detalle técnico de cada uno (de dónde saca el dato, por qué está hecho así) en `docs/05-scrapers.md`.

### Actualizar el catálogo de autoridades (nombres, fotos, cargos)

Eso NO lo trae un scraper — vive en `data/catalogo/` como archivos CSV
editables a mano (`autoridades.csv`, `comunas.csv`). Si cambia un alcalde,
un concejal renuncia, etc., se edita ese CSV directamente y después se corre
`python scrapers/poblar_catalogo.py` para que se refleje en
`data/processed/`.

---

## 3. Cómo llega un cambio a producción (para todo: blog, datos, diseño, código)

El sitio se despliega solo — no hay un botón de "publicar" aparte.

1. El cambio (el archivo del blog, un ajuste de código, lo que sea) se sube a la rama `main` del repositorio en GitHub.
2. Eso dispara automáticamente el workflow **`lint-test.yml`** (Actions → mismo lugar que el de datos): revisa que el código no tenga errores, construye el sitio (`npm run build`) y lo despliega a Cloudflare Pages.
3. En unos 1-2 minutos el cambio ya está visible en el sitio en vivo.

**Repositorio:** https://github.com/mtorresromero-cl/oprc-coquimbo
**Ver despliegues / builds:** https://github.com/mtorresromero-cl/oprc-coquimbo/actions

---

## 4. Resumen ultra-corto

- **¿Quiero publicar una noticia?** → archivo nuevo en `site/src/content/blog/`, subirlo a `main`.
- **¿Quiero traer datos nuevos ya?** → Actions → "Actualizar datos" → Run workflow. Esperar unas horas.
- **¿Cambió un alcalde/concejal?** → editar `data/catalogo/autoridades.csv`, correr `poblar_catalogo.py`, subir a `main`.
- **¿Cómo veo si ya se publicó?** → https://github.com/mtorresromero-cl/oprc-coquimbo/actions (verde = listo, unos 1-2 min después de subir a `main`).
