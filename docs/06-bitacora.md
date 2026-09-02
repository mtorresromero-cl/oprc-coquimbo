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

El usuario recordaba haber encontrado antes, buscando en GitHub, "la
solución para scrapear la cámara, que no bloquea nada". Se probó
`https://github.com/GTamayo` (perfil que el usuario creyó recordar): son
9 repos de ejercicios de data science, ninguno relacionado — no es la
fuente. Búsqueda más amplia en GitHub (código + repos) encontró dos
proyectos reales relacionados, ninguno es "la" solución exacta:

- **`fguinez/quevotaron`** (viejo, inactivo): en vez de recorrer la ficha
  de cada diputado, lee el listado general
  `https://www.camara.cl/legislacion/sala_sesiones/votaciones.aspx` con
  `requests.get()` simple — sin Playwright, sin clicks/postback. Pero solo
  trae "las últimas 20 votaciones" (`get_votaciones_recientes`), sin
  manejo de historial completo ni paginación de esa página. Vale la pena
  probar ese endpoint central como mecanismo de descubrimiento más simple
  y sin interacción — pero no resuelve el historial completo por sí solo,
  y al ser un proyecto abandonado no hay garantía de que ese endpoint siga
  respondiendo igual hoy.
- **`faal2026/observatorio-diputados`** (activo, actualizado 2026-08-31,
  propósito casi idéntico al nuestro): no cubre votaciones individuales en
  absoluto — solo sesiones/mociones/acuerdos/resoluciones/asistencia vía
  el servicio SOAP oficial (`WSSala.asmx`, `WSLegislativo.asmx`, no
  `wscamaradiputados.asmx`). Consistente con lo que ya documentamos:
  `getVotaciones_Boletin`/`getVotacion_Detalle` no publican datos para
  2026 en el servicio que sí probamos.

**No se encontró la solución exacta que el usuario recordaba.**

**Relevante para el fix de hoy:** revisando `docs/05-scrapers.md` se
confirmó que la decisión original (2026-08-25) de leer solo la página 1
de `votaciones_sala.aspx` **fue deliberada, no un descuido** — para no
repetir el patrón de interacción (clicks/postback en selectores y
paginador) que gatilló un bloqueo de Cloudflare en el formulario de
búsqueda del sitio. El fix de hoy (commit `3eae5c2`) sí interactúa con el
selector de año y el paginador — repite exactamente el patrón que se
había evitado a propósito. No se ha podido probar porque camara.cl sigue
caído (ver entrada anterior). **Pendiente: cuando el sitio vuelva, probar
con un solo diputado primero (no los 7 de una) y confirmar que no
dispara bloqueo antes de asumir que el fix es seguro en producción.**

---
