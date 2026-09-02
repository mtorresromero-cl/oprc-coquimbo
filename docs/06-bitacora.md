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

## 2026-09-02 — Análisis de prensa regional: plan y Fase 1 (descubrimiento RSS)

Nuevo proyecto grande, inspirado en `prensa_chile` de Bastián Olea pero
para la Región de Coquimbo. Decisión explícita del usuario: **se analiza
el texto completo de cada noticia, pero nunca se republica** — solo
estadísticas derivadas (nube de palabras, tendencias, co-ocurrencia),
igual que ya se hace con los discursos de diputados/senadores. Eso
resuelve de entrada el problema de derechos de autor que sí tendría
guardar y mostrar el texto crudo.

**28 fuentes**, provistas directamente por el usuario (las usa en Clave
Política, otro proyecto suyo) — confirmadas funcionando el 2026-09-02:
15 de la "Red Comunales" (un medio por comuna, ver el mapeo completo en
`scrapers/prensa_rss.py`) + 13 medios regionales externos (Diario El Día
con 4 feeds temáticos, El Ovallino, radios, etc.). Dos dominios usan "ñ"
(elvicuñense.cl, elvileño.cl) — se codifican a punycode a mano en la
config, Python no lo hace solo vía httpx.

**Plan en 4 fases:**
1. **Descubrimiento (hecho, `scrapers/prensa_rss.py`)** — recorre los 28
   RSS, guarda título/url/fecha/fuente/comuna/extracto en
   `prensa_articulo`. 295 noticias reales en la primera corrida, 0
   errores. No baja el texto completo todavía (`texto_completo` queda
   NULL).
2. **Texto completo (pendiente)** — por cada fila con `texto_completo
   IS NULL`, visitar la página real y extraer el cuerpo. Probado
   manualmente contra El Coquimbano: el texto está en una etiqueta
   `<article>` sin clase específica, con algo de ruido de plantilla
   ("Compartir", "X minutos de lectura") que hay que limpiar. Como
   todos son WordPress, un extractor genérico + limpieza de ruido
   común debería cubrir la mayoría; puede necesitar ajustes por sitio.
3. **Análisis (pendiente)** — reutilizar el tokenizador/stopwords de
   `analisis_intervenciones.py` (ya sirve para esto, es genérico). Los
   módulos que tiene Bastián en `prensa_chile` (todos vistos en vivo el
   2026-09-02): palabras más frecuentes por semana (tendencia), nube de
   palabras por semana, frecuencia de un término elegido en el tiempo,
   desglose de palabras/menciones por medio, y correlación entre
   términos (co-ocurrencia) — los dos últimos (nube y co-ocurrencia) ya
   tenemos el código hecho para discursos, se puede adaptar. Además,
   propio de un observatorio regional y que Bastián no hace: menciones
   por autoridad y por comuna.
4. **Página nueva en el sitio** — pendiente hasta tener fases 2 y 3.

**Pendiente de decisión:** frecuencia de corrida real (`prensa_rss.py`
queda con `frecuencia = "diaria"` como intención, pero
`actualizar-datos.yml` solo corre semanal — falta decidir si se agrega
un workflow nuevo diario o se deja semanal por ahora).

**Fase 2 (hecha, `scrapers/prensa_texto.py`):** 293/295 con texto
extraído, 2 fallos transitorios de red (quedan `texto_completo IS NULL`,
se reintentan solos la próxima corrida). El extractor genérico
(selectores en cascada + `<article>` + heurística de último recurso)
funcionó en los 5 sitios probados a mano.

**Bug real encontrado y corregido — mismo patrón que Núñez en el
Senado:** la primera corrida dejaba un bloque de metadatos de plantilla
incrustado en medio del cuerpo del artículo ("Agregar `<Medio>` / Por
`<Medio>`"), presente en 15 de las 18 fuentes con este problema (todas
las de la Red Comunales comparten plantilla). Sin limpiarlo, el nombre
del propio medio se repite en cada una de sus noticias e infla
artificialmente su frecuencia de palabras — el mismo tipo de sesgo por
auto-mención ya encontrado y corregido antes en las intervenciones del
Senado (ver más arriba). El primer intento de regex era demasiado
rígido (asumía un solo formato de fecha, "Mes Día, Año"); algunas
fuentes usan el orden inverso ("Día Mes Año"). Corregido con un patrón
más flexible sobre la estructura completa del bloque, no el formato de
fecha exacto — se aplicó primero contra el texto ya guardado (sin
volver a bajar nada de la red) para confirmar cobertura completa antes
de dejarlo en el scraper para las próximas corridas.

**Segundo bug de extracción, encontrado recién al correr la Fase 3
(análisis):** "comunales" salía como la palabra #1 del corpus completo
(2194 veces) y "interesar"/"hace"/"semanas" también aparecían con
conteos absurdos. Causa: el selector genérico `<article>` de las 15
fuentes de la Red Comunales incluye el widget "Te puede/podría
interesar" (enlaces a otras noticias) Y el breadcrumb de categoría
("Comunales"), repetidos varias veces dentro del mismo `<article>` —
no es ruido de plantilla en una franja fija como el bug anterior, sino
contenido de navegación mezclado con el cuerpo real. Se investigó el
HTML crudo con el inspector (no adivinando) y se encontró que las 15
fuentes comparten tema WordPress "MH Magazine / MVP", con el cuerpo
real aislado en `id="mvp-content-body"` — mucho más preciso que
`<article>`. Se agregó ese id como selector de máxima prioridad y se
volvió a extraer las 150 filas de la Red Comunales (146 con éxito, 4
fallos transitorios). Resultado: 130.324 → 84.071 palabras útiles en el
corpus (~35% era ruido) y las palabras más frecuentes ahora son
contenido real ("coquimbo", "salud", "vecinos", "comunidad"), no
artefactos de plantilla.

**Lección:** un conteo de palabras "demasiado alto para ser real" es la
señal más clara de que queda ruido de extracción — vale la pena mirar
el ranking de palabras más usadas como chequeo de calidad después de
cada extracción nueva, no solo revisar una muestra de texto a mano.

---

## 2026-09-02 — Nueva herramienta: Delincuencia (CEAD), bloqueado el scraping en vivo

A partir de una idea del catálogo de apps de Bastián Olea Herrera
(bastianolea.github.io/shiny_apps), se agregó `/herramientas/delincuencia/`:
tasa de casos policiales por cada 10.000 habitantes, por comuna y tipo de
delito, 2010-2025.

**CEAD en vivo está bloqueado, causa desconocida — distinto al caso de
camara.cl de más arriba.** `cead.minsegpublica.gob.cl` devuelve 403
"Maximum request file upload" para TODO (hasta un GET a la portada, hasta
con Playwright/Chromium real) — no es el mismo patrón que camara.cl (que
resultó ser un dominio roto): acá ni siquiera hay un dominio alternativo
obvio que probar (se intentó `cead.spd.gov.cl`, no existe). No se investigó
más a fondo — ya se gastó gran parte del día en el problema de camara.cl y
no vale la pena repetir ese patrón. Queda documentada la técnica exacta de
scraping (POST a `get_estadisticas_delictuales.php`, con los parámetros de
familia/grupo/subgrupo de delito) por si se retoma más adelante desde otra
red.

**Mientras tanto, los datos se importan desde un snapshot público de
terceros**, no un scraping propio: `scrapers/delincuencia_cead.py` descarga
el parquet ya limpio de `bastianolea/delincuencia_chile` (mismo dato
oficial de CEAD, él sí logró scrapearlo) y lo filtra a las 15 comunas de la
Región de Coquimbo. Es una fuente pública con atribución clara en la propia
página, pero vale tenerlo presente: no es scraping propio verificable línea
por línea como el resto del proyecto — es confiar en el trabajo de otro
sobre la misma fuente oficial.

**De paso, se agregó población real a `comunas.csv`** (Censo 2024, INE,
sumada desde el dataset tabulado de `bastianolea/censo_poblacion_consultar`)
— el campo `poblacion` existía en el schema desde antes pero nunca se había
poblado. Ver nota en `data/catalogo/NOTAS.md` sobre el error de doble
conteo que se cometió y corrigió al calcularla (las filas "Total" de sexo y
edad se sumaban junto con el desglose real, inflando ~4x).

---

## 2026-09-02 — CAUSA RAÍZ REAL: `camara.cl` sin `www` está roto en Cloudflare

Después de todo lo de las entradas anteriores (bloqueo por IP, huella
TLS, JA3/JA4, HTTP/3 — todas descartadas una a una con evidencia), la
causa real resultó mucho más simple: **el dominio "pelado" `camara.cl`
(sin `www`) tiene una configuración TLS rota en Cloudflare** —
`dig camara.cl TYPE65` no tiene registro HTTPS/SVCB, mientras que
`www.camara.cl` sí lo tiene (ALPN `h2`, hints de IP normales). Probado
directo:

```
curl https://camara.cl/       -> 000 (falla el handshake TLS)
curl https://www.camara.cl/   -> 403 (TLS ok, solo un WAF normal)
```

Y con curl_cffi (impersonate=chrome) contra `www.camara.cl`, las tres
URLs que fallaban todo el día devuelven 200 con contenido real (tabla,
`ddlAnnos`, paginador, IDs de votación reales) — desde el mismo sandbox
que llevaba fallando desde la mañana. **Nunca fue un bloqueo de IP, de
huella TLS, ni de comportamiento — todos los scrapers apuntaban al
dominio equivocado.**

Todos los scrapers de camara.cl usaban `https://camara.cl/...` menos
`gasto_parlamentario.py` (que ya usaba `www.camara.cl` desde su
creación, commit `68f22d8` — por eso su docstring hablaba de la técnica
correcta sin saber que además tenía la URL correcta). Corregido en
`camara_votaciones.py`, `camara_mociones.py` y `camara_asistencia.py`
(ahora los tres usan `www.camara.cl`).

**Por qué el navegador del usuario sí funcionaba:** casi seguro porque
al escribir "camara.cl" en la barra de direcciones, o desde un
bookmark/historial viejo, el navegador ya tenía cacheado un redirect a
`www.camara.cl` de una visita anterior, o Chrome/Safari simplemente
agregan `www.` automáticamente en algunos casos — nunca llegaba a
intentar conectarse al dominio roto.

**Corrección importante — esto ya se lo habían dicho a Claude antes:**
el usuario ya había indicado en una sesión anterior que había que usar
`www.camara.cl`, y esa indicación se perdió (mismo patrón que
quieneseljefe.cl y la solución de curl_cffi de `gasto_parlamentario.py`
— información real que el usuario ya había dado, no recordada por no
estar escrita en ningún lado). No fue un hallazgo nuevo de esta sesión:
fue redescubrir, con casi un día completo de investigación de más, algo
que ya se sabía. Motivo de más para el hábito de esta bitácora.

**Lección para la próxima vez:** cuando algo falla igual desde todo
entorno posible (sandbox, CI, red residencial) pero funciona en el
navegador, antes de sospechar de fingerprinting/bloqueos exóticos,
comparar directamente `curl` contra las dos variantes obvias del
dominio (con y sin `www`, http y https) — habría ahorrado casi un día
completo de investigación.

---

## 2026-09-02 — Descartada la hipótesis de IP/red: falla hasta desde el Mac del usuario

El usuario corrió `scrapers/test_camara_conectividad.py` desde su propio
Mac (misma red donde su navegador SÍ carga camara.cl sin problema).
**httpx, curl_cffi (impersonate=chrome) y curl del sistema fallaron los
tres, con el mismo `SSLV3_ALERT_HANDSHAKE_FAILURE`** — idéntico al error
visto desde este sandbox y desde GitHub Actions.

Esto descarta por completo la hipótesis anterior (bloqueo por reputación
de IP de nube/CI): si fuera un tema de IP, la red doméstica del usuario
—que su navegador usa sin problema— no debería fallar. La variable que
sí distingue "funciona" de "no funciona" es el **cliente**: un navegador
real (Chrome/Safari interactivo) pasa, pero CUALQUIER herramienta
automatizada probada hasta ahora falla — incluida curl_cffi, que
específicamente imita la huella TLS de Chrome y aun así no basta.

**Hipótesis actual (más fuerte que las anteriores, pero no confirmada):**
camara.cl/Cloudflare aplica fingerprinting TLS (JA3/JA4) lo bastante
estricto como para detectar incluso herramientas que imitan la huella de
Chrome — algo conocido en la práctica (curl_cffi es una herramienta
pública, sus firmas eventualmente se agregan a listas de detección).
Motores de navegador reales (no solo la huella TLS, sino el stack HTTP/2
completo) sí pasarían; ningún cliente HTTP de librería lo ha logrado
hasta ahora, ni siquiera desde una IP residencial limpia.

**Pendiente:** probar Playwright (Chromium real, no una librería HTTP)
desde una red que no sea sandbox/GitHub Actions — sería la prueba
definitiva de si el problema es "cualquier automatización" o
específicamente "huella TLS insuficiente en clientes no-navegador".

---

## 2026-09-02 — El fix de curl_cffi NO resolvió el bloqueo (corrección importante)

Tras horas de espera, se re-disparó `actualizar-datos.yml` (run
`33622660812`). **`camara_mociones.py`, `camara_asistencia.py` Y
`camara_votaciones.py` (curl_cffi) fallaron los tres, con el mismo error
TLS (`ERR_SSL_VERSION_OR_CIPHER_MISMATCH`), casi al mismo segundo.**
`mociones.aspx` y `asistencia_sala.aspx` son GET simples, sin ninguna
interacción/postback — y fallaron igual que `votaciones_sala.aspx`. Esto
descarta las dos hipótesis anteriores (patrón de interacción específico,
huella TLS de Playwright vs curl_cffi): el bloqueo es contra camara.cl
completo, a nivel de red/TLS, desde la IP de GitHub Actions — curl_cffi
con `impersonate="chrome"` NO lo esquiva.

**Error propio al reportar esto (correguido en la conversación, no
solo acá):** al revisar `gh run view --json jobs -q '.conclusion'` los
tres pasos mostraban `"success"` — se interpretó erróneamente como que
sí habían funcionado. La razón real es que `continue-on-error: true`
(agregado hoy mismo, ver entrada del workflow) hace que GitHub reporte
`conclusion: success` en el step aunque el script haya fallado de
verdad — el log crudo (`gh run view --log`) sí mostraba el traceback y
`Process completed with exit code 1` en los tres. Lección: con
`continue-on-error`, `conclusion` no basta para saber si un paso
realmente funcionó — hay que mirar el log o el campo `outcome`.

**Implicación seria:** dado que ni Playwright (mociones/asistencia,
scrapers que llevaban semanas funcionando) ni curl_cffi con huella TLS
de navegador real lograron pasar, y que esto pasa igual muchas horas
después del primer bloqueo, es probable que Cloudflare esté bloqueando
directamente el rango de IPs de los runners de GitHub Actions (no una
huella de cliente ni un patrón de interacción) — algo que ningún cambio
de scraper por sí solo puede resolver. La única vía real sería correr el
scraper desde una IP no bloqueada (ej. el VPS propio que ya se usa para
otros proyectos, ver `reference_vps_infra` en la memoria) en vez de
GitHub Actions.

**Pendiente:** decidir con el usuario si vale la pena investigar mover
la ejecución de los scrapers de camara.cl fuera de GitHub Actions, o
seguir esperando/reintentando periódicamente por si el bloqueo se
levanta solo.

---

## 2026-09-02 — camara_votaciones.py reescrito con curl_cffi (sin Playwright)

Aplicada la técnica de `gasto_parlamentario.py` (ver entrada anterior):
`recolectar()` ya no usa Playwright — usa `curl_cffi` (`impersonate=
"chrome"`) para GET/POST directos, con el mismo ritmo conservador
(`SLEEP_ENTRE_PETICIONES=4.0` + backoff en 403/429). Los postbacks
ASP.NET (selector de año, paginador) se simulan armando el POST de
formulario a mano (VIEWSTATE + EVENTTARGET + valores actuales de cada
`<select>`), sin ejecutar JS.

El parseo de `votacion_detalle.aspx` se tradujo de Playwright
(`page.locator("body").inner_text()` + una función JS para las
secciones) a BeautifulSoup (`get_text("\n", strip=True)` + selectores
CSS) **manteniendo las mismas expresiones regulares ya validadas
manualmente el 2026-08-25** — el conteo de A Favor/En Contra/Abstención
se cambió a lectura directa de celdas `<td>` en vez de un regex sobre
texto con tabs (más robusto, no depende de que `get_text` reproduzca
tabs entre celdas igual que `innerText()`).

**Verificado sin tocar camara.cl** (el sitio sigue en enfriamiento):
todas las funciones nuevas (`_estado_formulario`, `_seleccionar_anno`,
`_avanzar_pagina`, `_recolectar_ids_de_pagina`, `_tally`, `_secciones`,
`_parsear_detalle`) se probaron con HTML sintético que replica la
estructura real confirmada antes vía Wayback Machine (selects
`ddlAnnos`, paginador `div.paginacion` con postback, tabla `table.tabla`,
secciones `section.section.group`). `ruff check` y `pytest` pasan.

**Pendiente real:** esto NO reemplaza una prueba contra el sitio real.
Falta correrlo contra camara.cl de verdad — cuando el bloqueo se enfríe,
probar primero con un solo diputado y un solo año antes del recorrido
completo de los 7, y confirmar que el HTML sintético usado para probar
coincide con el real (los campos de fecha en particular: la regex
original asume formato "DD MES AAAA" sin la palabra "de" en medio — no
confirmado contra el sitio real todavía, solo heredado del código
anterior).

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

**Corrección:** el usuario confirmó que el sitio carga bien normalmente
(no está caído) — la conclusión original de "caída/outage" era incorrecta
y quedó escrita sin haberlo verificado con el usuario primero. Hipótesis
correcta: Cloudflare está bloqueando a nivel TLS específicamente las IPs
de infraestructura en la nube (este sandbox y los runners de GitHub
Actions), no a navegadores normales — muchos WAF bloquean por reputación
de rango de IP (datacenter/cloud) independiente del user-agent o
comportamiento. Esto es más grave que un problema temporal: si Cloudflare
bloquea el rango de IPs de GitHub Actions específicamente, el scraper NO
podría volver a funcionar solo "esperando" — necesitaría correr desde una
IP no bloqueada (ej. un servidor propio/VPS en vez de runners de GitHub).

**Pendiente:** confirmar si es realmente un bloqueo por rango de IP
(no un problema de TLS/cipher del cliente) y, si lo es, evaluar mover la
ejecución del scraper fuera de GitHub Actions.

**Corrección 2 — la solución ya existía en este mismo repo y se perdió
otra vez:** el usuario ya había pasado esta misma situación el
2026-08-31 (ver commit `68f22d8`, `scrapers/gasto_parlamentario.py`) y
dio la solución en esa sesión — pero, igual que con quieneseljefe.cl, no
quedó registrada en la bitácora (no existía todavía) y se perdió al
compactarse la conversación. El usuario tuvo que repetirla molesto.

Lo que dice ese commit, textual: **Playwright dispara un bloqueo por IP
con suficiente uso** ("hoy ya se gatilló un bloqueo por IP a fuerza de
las pruebas con Playwright"). La solución probada y funcionando es
**dejar de usar Playwright por completo y usar `curl_cffi` con
`impersonate="chrome"`** (huella TLS de navegador real, sin llamadas
AJAX con headers `XMLHttpRequest`/`X-MicrosoftAjax` que Cloudflare
detecta) — confirmada contra un scraper público real,
`github.com/jahadd/Analisis_congreso_Chile`. Ya está implementada y
funcionando en `gasto_parlamentario.py`; `camara_votaciones.py`,
`camara_mociones.py` y `camara_asistencia.py` **siguen en Playwright**,
expuestos al mismo riesgo.

Es muy probable que el bloqueo de hoy sea el mismo tipo (IP, por
rate-limit), posiblemente reforzado por mis propias pruebas repetidas
hoy contra camara.cl (curl, WebFetch, Playwright x2, más el job de
GitHub Actions) — sin necesariamente ser un bloqueo distinto al de
Cloudflare por reputación de IP en la nube.

**Pendiente:** reescribir `camara_votaciones.py` con la misma técnica de
`gasto_parlamentario.py` (curl_cffi + impersonate chrome, sin
Playwright) en vez de seguir usando Playwright para el fix de
paginación. No volver a golpear camara.cl hoy — dejar enfriar el
bloqueo actual antes de probar de nuevo (mismo criterio que el 08-31).

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
