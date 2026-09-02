# 06 — Bitácora

Registro de investigaciones, decisiones y pendientes que no quedan explícitos
en el código ni en los mensajes de commit — para no perder contexto entre
sesiones. Se actualiza cuando: se investiga algo externo (una fuente de
datos, un repo, un sitio de referencia) y no se termina de usar; se toma una
decisión de diseño con un motivo no obvio; algo queda deliberadamente a
medias o bloqueado; se encuentra y corrige un bug de fondo (causa raíz, no
el detalle del diff).

No es un changelog de cada cambio de código — para eso está `git log`. Es
específicamente lo que se perdería si solo quedara en la conversación.

---

## 2026-09-02 — Votaciones de diputados: solo traía el mes más reciente

**Problema:** el usuario notó que la ficha de diputados mostraba solo ~10-13
votaciones, todas de agosto 2026, aunque la legislatura empezó el 11 de
marzo de 2026.

**Causa raíz:** `votaciones_sala.aspx` (ficha de cada diputado en camara.cl)
filtra por año (`<select>` `ddlAnnos`) y pagina el resto — ambos vía
postback AJAX (ASP.NET `UpdatePanel`), no parámetros de URL. El scraper
original solo leía la página 1 del año por defecto.

**Cómo se confirmó:** camara.cl no era alcanzable desde este entorno
(sandbox) ni desde curl directo — fallo TLS (`ERR_SSL_VERSION_OR_CIPHER_MISMATCH`
/ `SSLV3_ALERT_HANDSHAKE_FAILURE`). Se confirmó la estructura real de la
página (el `<select>` de año + el paginador con postback) usando una copia
archivada en Wayback Machine (`web.archive.org`), sin necesidad de acceso
en vivo.

**Fix:** `scrapers/camara_votaciones.py` ahora selecciona explícitamente
el/los año(s) de la legislatura actual (desde `LEGISLATURA_INICIO_ANNO =
2026`) y recorre todas las páginas del paginador (incluyendo el botón "..."
que carga la siguiente ventana de páginas) antes de extraer los IDs de
votación. Commit `3eae5c2`.

**Diseño del sitio (a pedido del usuario):** el ranking/número de arriba ya
usaba el período completo — no cambió. La lista "Votaciones recientes" no
tenía límite; se acotó a las últimas 10 (`VOTACIONES_RECIENTES_MAX`) y se
corrigió el texto para aclarar que el ranking sí es del período completo.

**Pendiente:** camara.cl empezó a fallar con el mismo error TLS incluso
desde GitHub Actions (ver entrada siguiente) — el fix está desplegado pero
sin verificar contra datos reales todavía.

---

## 2026-09-02 — camara.cl caído / bloqueando TLS (no es un problema nuestro)

Al disparar `actualizar-datos.yml` manualmente para correr el fix de
votaciones, falló en `camara_mociones.py` (un scraper que venía
funcionando bien) con el mismo error SSL que se veía desde el sandbox.
Confirmado que no es específico de este entorno: GitHub Actions tiene red
real y falló igual. Tampoco es un problema general de red (google.com y
otro sitio .cl cargan bien) — es específico de camara.cl.

**Conclusión:** probablemente una caída o cambio de política TLS/WAF
temporal del lado de camara.cl, no algo para arreglar en nuestro código.

**Siguiente paso:** reintentar más tarde (manualmente o esperar el cron
semanal de los lunes). No seguir insistiendo en loop contra un sitio caído.

---

## 2026-09-02 — Regresión: link roto a `/parlamentarios/discursos-senado/`

Al comitear el fix de votaciones (`3eae5c2`) se usó `git add
site/src/pages/parlamentarios/index.astro`, que subió el archivo completo
— incluyendo un bloque de menú del Senado que ya estaba modificado sin
comitear desde antes (parte del trabajo de intervenciones del Senado, ver
más abajo). Ese bloque enlazaba a una página que no existe en producción
todavía, así que quedó un link muerto en vivo (Cloudflare Pages redirige
al home en rutas inexistentes).

**Lección:** al comitear cambios acotados en un archivo que ya tenía otras
modificaciones sin comitear, revisar el diff completo (`git diff --stat` /
`git show`) antes de asumir que el commit solo contiene lo que se acaba de
editar — `git add <archivo>` sube TODO el estado actual del archivo, no
solo el diff de la sesión.

**Fix:** se desactivó el link (mismo patrón visual que el pill "Gasto
parlamentario", con tooltip "Estamos trabajando en eso") hasta que la
página se comitee junto con sus datos. Commit `be6bc4a`.

---

## 2026-09-02 — quieneseljefe.cl y opendata.congreso.cl

El usuario preguntó si se estaba usando código de un repo de GitHub del
creador de quieneseljefe.cl que se había investigado antes en esta misma
sesión — no quedó registro de eso en el código ni en esta bitácora (de ahí
que se perdiera). Investigado de nuevo:

- **quieneseljefe.cl**: sitio de seguimiento de votaciones/gastos/asesores
  de diputados, muy similar en propósito a este proyecto. No se encontró
  repositorio público en GitHub (búsqueda por nombre sin resultados). El
  sitio bloquea fetch directo (403 Forbidden) — no se pudo inspeccionar su
  código ni su "acerca de".
- **opendata.congreso.cl**: portal oficial de datos abiertos del Congreso
  chileno, encontrado en la misma búsqueda. Posible fuente más confiable
  que scrapear las páginas ASP.NET de camara.cl a mano (evitaría el
  problema de paginación/postback y quizás el bloqueo TLS actual). **No
  investigado todavía si cubre votaciones de diputados con el detalle que
  necesitamos** — pendiente de decisión con el usuario sobre si migrar.

---
