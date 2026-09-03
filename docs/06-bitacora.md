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

## 2026-09-03 — Cierre real de la saga camara.cl: se abandona camara.cl directo, se pasa a quieneseljefe.cl

Cierre definitivo de todo lo registrado abajo (2026-09-02, "El fix de
www.camara.cl..." y sus entradas siguientes). Tercer intento de la
noche/madrugada: el segundo run de GitHub Actions (`33708344824`)
tampoco terminó — `camara_votaciones.py` superó las 6 horas y lo cortó
el timeout por defecto del job (no hubo error de código, simplemente no
alcanzó a terminar; se perdió también lo que sí había funcionado antes
en esa corrida — senado, mociones, asistencia — porque el commit final
es uno solo al terminar todo el workflow).

**Se abandona camara.cl como fuente directa para votaciones y
asistencia de diputados.** El usuario propuso usar
[quieneseljefe.cl](https://quieneseljefe.cl) en su lugar, señalando qué
datos muestra (asistencia con detalle de sesiones, votaciones con
boletín/fecha/resultado, gastos). Investigado y confirmado viable:

- Fetchable con `curl_cffi impersonate="chrome"` igual que camara.cl
  (`WebFetch` normal da 403, pero eso no bloquea el scraper).
- Usa el MISMO id numérico interno que camara.cl (`prmId`/`/diputado/{id}`),
  así que `DIPUTADOS_COQUIMBO` no cambió.
- Cada diputado tiene una sola página HTML estática con su historial
  COMPLETO de votos (`#dp-vote-list .dp-vote-item`, boletín + fecha +
  voto + resumen que distingue general/particular) y de asistencia
  (`#asi-view-list .dp-asi-row`, con estado presente/ausente/próxima).
  7 peticiones en vez de la fase de descubrimiento paginada completa
  que exigía camara.cl.
- El detalle agregado de cada votación (resultado + tally) sigue
  necesitando una petición por votación única
  (`/votacion/{id}/{slug}`, clases `.vdt-outcome-title` y
  `.vdt-dch-count`/`.vdt-dch-label`) — eso no cambió, pero ya no hay
  paginación de descubrimiento por delante.

**Resultado real:** `camara_asistencia.py` y `camara_votaciones.py`
reescritos completos. Corridos localmente: **asistencia en ~10
segundos** (7 páginas), **votaciones en unos minutos** (7 páginas +
71 detalles de votación únicos, 0 errores) — contra las +6 horas sin
terminar de antes.

**Bug encontrado en el camino (mismo patrón que el usuario ya había
notado en asistencia):** quieneseljefe.cl incluye sesiones/votos desde
enero 2026 (cola de la legislatura anterior), antes del inicio real de
la legislatura actual (11 de marzo 2026). Se agregó el filtro
`fecha < LEGISLATURA_INICIO` en ambos scrapers — asistencia quedó en 63
sesiones computables por diputado (antes incluía ~84, de enero), y
votaciones quedó en 46 votaciones reales (antes 71, de las cuales 25
eran de enero-febrero).

**Pérdidas reales de calidad frente a camara.cl directo, documentadas
en el docstring de cada scraper:**
- Asistencia: ya no se distingue ausencia justificada de injustificada
  (quieneseljefe.cl no lo publica) — todo queda como "sin justificar".
- Votaciones: la categoría "Abstención" ahora es la "No vota" de
  quieneseljefe.cl (probablemente mezcla abstención + inhabilitado +
  dispensado). No se guarda `numero_sesion` (esa fuente no lo expone en
  el detalle de la votación).

Se mantiene `gasto_parlamentario.py` sin cambios — ya funciona bien
contra camara.cl directo (verificado el 2026-09-02), y quieneseljefe.cl
no expone los montos de gasto como texto plano (se cargan por JS/API
aparte, no vale la pena migrarlo).

**⚠️ PENDIENTE (no resuelto, usado quieneseljefe.cl "por urgencia"):**
el usuario fue explícito en que esto es un parche, no la solución
definitiva — hay que retomar y resolver el scraping directo a camara.cl
para votaciones y asistencia de diputados cuando haya tiempo para
hacerlo bien (más lento no debería ser sinónimo de "no funciona": la
fase de descubrimiento paginada se puede optimizar, por ejemplo
recorriendo un solo diputado para descubrir IDs en vez de los 7 — ver
la nota de eficiencia ya agregada más abajo, en la entrada del mismo
día, que quedó sin probarse). Mientras tanto: no se cita
quieneseljefe.cl en ningún texto público del sitio — el link "Fuente
oficial" en la UI apunta a la URL reconstruida de camara.cl (mismo id
numérico en ambos sitios), nunca a quieneseljefe.cl directamente.

---

## 2026-09-02 — El fix de www.camara.cl SÍ funcionó, pero el commit se perdió por un choque de pushes

Cierre (parcial) de la saga de camara.cl de hoy. El run `33640782889`
(el que iba a validar en producción el fix de `www.camara.cl` de
`camara_votaciones.py`) terminó con `conclusion: failure` — pero
**no por el scraper**: los 15 pasos de scraping, incluido
`camara_votaciones.py`, terminaron en `success` real (no enmascarado
por `continue-on-error`, se confirmó con el log completo). El único
paso que falló fue el último, "Commit datos actualizados":

```
[main 3159b88] datos: actualización automática 2026-09-02
 5 files changed, 652 insertions(+), 204 deletions(-)
 ! [rejected]        main -> main (fetch first)
error: failed to push some refs...
```

**Causa raíz:** el workflow arrancó a las 14:14 con un checkout viejo de
`main`. Mientras corría (tardó ~5 horas por los otros scrapers, no por
camara_votaciones.py que terminó a las 17:06), esta misma sesión hizo
varios commits y pushes a `main` (todo el trabajo de prensa regional y
densidad poblacional). Al llegar al commit final, git rechazó el push
porque el remoto ya había avanzado — el commit local `3159b88` con los
datos reales (652 inserciones, consistente con un historial completo,
no solo agosto) quedó atrapado en el runner efímero y se perdió para
siempre cuando terminó, sin forma de recuperarlo.

**Lección para la próxima vez que se dispare manualmente un workflow
largo:** si se va a seguir trabajando y comiteando en `main` mientras un
workflow de varias horas corre en paralelo, hay riesgo real de choque
en el push final — no es solo teórico, pasó. Si se sabe que se van a
hacer más commits durante la espera, considerar disparar el workflow
al final de la sesión, no al principio.

**Corrección de la acción tomada:** se disparó el workflow completo
(`33679386782`) pero el usuario preguntó, con razón, si hacía falta
repetir TODO el paquete (~5h) solo para confirmar el fix de camara.cl,
cuando ese fix solo toca 3 de los 8 scrapers del workflow — el resto
(transparencia_municipal, personal_municipal, infoprobidad,
core_coquimbo, delincuencia_cead) no tiene nada que ver y sumó ~2h
extra en el intento anterior. Se canceló ese run
(`gh run cancel 33679386782`) y en su lugar se corrieron
`camara_mociones.py` y `camara_asistencia.py` directo en este entorno
(rápidos, ~1 min cada uno — 77 filas nuevas de asistencia, 0 mociones
nuevas) y `camara_votaciones.py` en segundo plano (el lento, ~2h45min
por el sitio de la Cámara, no por el runner). Al terminar se comitea y
pushea todo junto manualmente, sin pasar por GitHub Actions.
**Pendiente real:** confirmar que `camara_votaciones.py` complete y
verificar `votaciones-camara.json` (registros y meses desde marzo
2026).

**Bug de fondo encontrado y corregido (el usuario preguntó "llevamos 9
horas en esto, es excesivo para 7 diputados"):** el scraper no tenía
forma de saber qué votaciones ya había traído en corridas anteriores —
`recolectar()` volvía a pedir la página de detalle de CADA votación
descubierta, todas las veces, sin importar si ya estaba guardada en la
base. Eso no es solo el costo del backfill de hoy (~6 meses de
historial perdido por el bug original): **sin este fix, cada corrida
semanal futura iba a repetir el mismo recorrido completo desde marzo
2026 para siempre**, cada vez más lento a medida que se acumula
historial, en vez de traer solo lo nuevo de esa semana. Se agregó un
filtro que consulta `votacion_sesion` al empezar y salta el fetch de
detalle para cualquier `vid` ya guardado (el resultado de una votación
de sala es definitivo una vez cerrada, no hace falta re-pedirlo). No se
tocó la corrida que ya estaba en curso en background — el fix aplica
recién a partir de la próxima ejecución (la semanal por cron, o
cualquier corrida manual futura).

**Dos hallazgos más, esta vez sí obligaron a parar la corrida en curso
(que igual no había guardado nada todavía, cero costo hundido real):**

1. **Falta distinguir voto "general" de voto "particular".** El usuario
   preguntó cómo lo muestra quieneseljefe.cl — se pudo fetchear ese
   sitio con `curl_cffi impersonate="chrome"` (el mismo truco de
   camara.cl; con `WebFetch` normal da 403). Confirmado comparando el
   boletín 18189-14 en ambos sitios: cada proyecto tiene UN voto
   general (campo "Artículo:" vacío en camara.cl) y CERO o más votos
   particulares (uno por artículo/indicación con "votación separada"
   solicitada, campo "Artículo:" con el texto de qué se vota).
   quieneseljefe.cl los muestra como registros separados pero con una
   etiqueta clara "General"/"Particular" + el texto del artículo en los
   particulares. Se agregaron las columnas `etapa` y `articulo` a
   `votacion_sesion` (`ALTER TABLE` a la base ya existente + actualizado
   `schema.sql`) y se captura ese campo en `_parsear_detalle()`.

2. **Bug real preexistente, no relacionado con lo anterior:** al probar
   el parseo contra páginas reales para verificar el punto 1, `_tally()`
   (la función que lee "A Favor / En Contra / Abstención") fallaba en
   el 100% de las páginas probadas — tanto en el voto general (89863)
   como en los particulares (89864, 89865). Causa: camara.cl entrega
   los `<th>` de encabezado como hijos directos de `<table>`, SIN
   envolverlos en un `<tr>` (HTML inválido pero es lo que el sitio
   manda) — `th.find_parent("tr")` nunca encontraba nada, así que
   `_parsear_detalle()` devolvía `None` y esa votación se contaba como
   error sin guardar nada, en silencio. Esto significa que **la corrida
   de ~2h45min de esta tarde probablemente no guardó ninguna votación
   real** (o casi ninguna) pese al `stats: success` — el commit perdido
   de antes (652 inserciones) probablemente venía sobre todo de otros
   scrapers del mismo run, no de `camara_votaciones.py`. No se pudo
   confirmar porque ese commit nunca llegó a pushearse. Corregido:
   ahora se busca el `<table>` contenedor completo y se leen sus `<td>`
   en orden de documento, sin depender de si están agrupados en `<tr>`
   o no. Verificado con las 3 páginas reales (general + 2 particulares)
   antes de relanzar — las 3 ahora parsean bien.

Se limpiaron las 13 filas viejas de `votacion_sesion` (eran del bug
original, sin `etapa`/`articulo`) para que la corrida completa las
vuelva a traer con los campos nuevos, en vez de saltárselas por el
filtro de "ya conocidas" del punto anterior. Relanzado el backfill
completo en background con ambos fixes aplicados.

---

## 2026-09-02 — Densidad poblacional: nueva herramienta + contexto en Delincuencia

**Auditoría de datos pedida por el usuario ("¿gasto parlamentario e
intervenciones en sala están correctos?"):** se revisó con consultas
reales (no solo conteo de filas) — 0 duplicados exactos, los nulos de
`gasto-parlamentario.json` son exactamente `pasajes_aereos` y
`asesorias_externas` (categorías que camara.cl no publica con monto,
documentado en el propio scraper), los 3 senadores sin gasto es porque
el scraper está scopeado a los 7 diputados a propósito (dice "gasto de
los 7 diputados" en su docstring). `intervenciones-sala.json` cubre los
7 diputados y 3 senadores completos, sesiones desde el inicio real de
la legislatura (18 de marzo 2026); los pocos registros sin texto son
todos "Homenaje"/"Acuerdos y Resoluciones" (sin discurso propio por
diseño). **Importante:** no hay tests reales en `scrapers/` (cero
funciones `def test_`) — el CI en verde solo valida lint + build del
sitio, no la corrección de los datos. La única forma real de verificar
es consultar los JSON/DB directamente, como se hizo acá.

**Nueva fuente de datos — densidad poblacional:** el usuario pasó
`https://bastianoleah.shinyapps.io/densidad_comunas/` (una app Shiny,
no fetcheable directo — solo muestra un spinner de carga). Se encontró
el repo real detrás, `bastianolea/densidad_poblacional_comunas`, con
`datos/superficies_dpa_2023.csv` (superficie real por comuna, DPA 2023
de SUBDERE). Documentado en `data/catalogo/NOTAS.md`. La suma de las 15
comunas (40.587,79 km²) coincide con la superficie oficial conocida de
la región (~40.580 km²) — dato verificado, no solo copiado.

El campo `superficie_km2` en el schema de `comuna` **ya existía** (se
había anticipado antes de esta sesión) pero estaba sin llenar (`null`
en todas las filas) — se llenó ahora. `scrapers/poblar_catalogo.py`
actualizado para leerlo desde `comunas.csv`.

**Nueva herramienta `/herramientas/densidad/`:** ranking de las 15
comunas por densidad (hab/km²), mismo patrón visual que el comparador
de Delincuencia (barras + `COLOR_COMUNA`). Y se agregó la densidad como
**dato de contexto** (no reemplaza la tasa) en `/herramientas/delincuencia/`
— tanto en el tooltip del gráfico de líneas como en el ranking de
"Comparar comunas": ayuda a explicar por qué una comuna rural con pocos
casos puede tener una tasa que salta mucho de un año a otro (denominador
poblacional chico), caso real visible con Paihuano (tasa muy alta, 3.1
hab/km² — territorio disperso).

**Trampa evitada al correr `poblar_catalogo.py`:** el script reexporta
TODOS los JSON individuales de las 142 autoridades (con `actualizado_en`
recién generado) cada vez que corre, aunque solo se haya tocado
`comunas.csv` — eso generó ~143 archivos "modificados" que en realidad
solo cambiaban de timestamp, cero contenido real. Se revirtieron con
`git checkout` antes de comitear, dejando solo los cambios reales
(comunas.csv/json, la DB, y el código).

Verificado con Playwright, cero errores de consola.

---

## 2026-09-02 — Prensa regional: nota sobre Coquimbo, fix Mi Radio, y banner en portada

**"Coquimbo" domina "Comunas más mencionadas" — investigado y es real,
no un bug:** de las 460 apariciones de la palabra "coquimbo" en el
corpus, 224 (49%) están en contexto "Región de Coquimbo" / "Gobierno
Regional de Coquimbo", no la comuna. A nivel de artículo: de los 173
artículos que mencionan "coquimbo", 58 (un tercio) SOLO la mencionan
como nombre de la región, nunca como comuna. Es ambigüedad real del
lenguaje (la comuna capital comparte nombre con la región) — no se
intentó desambiguar automáticamente (es un problema de NLP real, no de
substring), se dejó una nota explicando esto bajo el gráfico en
`prensa.astro`.

**"Miradio" → "Mi Radio"** (con espacio, nombre real de la radio) —
mismo patrón que el fix de "Radio Montecarlo": renombrado en
`scrapers/prensa_rss.py` y en las 10 filas ya guardadas en la base.

**Banner de Prensa regional en la portada** (`site/src/pages/index.astro`,
entre "Destacados" y "Explorar los datos"): a diferencia del banner de
Delincuencia (ícono + texto), el usuario pidió explícitamente **sin
ícono** — una ilustración HTML que sugiera "palabras, un gráfico, un
diario". Se armó una mini maqueta de diario (tarjeta blanca rotada, con
líneas de texto simuladas y un mini-gráfico de barras) más 3 palabras
reales (las 3 más usadas del corpus, no decorativas) flotando alrededor
en distintos tamaños/rotaciones. Bug encontrado y corregido antes de
comitear: las palabras flotantes quedaban parcialmente tapadas por la
tarjeta blanca (que se dibuja después en el DOM, con más z-index
implícito) porque el contenedor era muy angosto para la tarjeta que
tenía adentro — se agrandó el contenedor y se movieron las palabras a
las esquinas exteriores; verificado sin superposición con
`bounding_box()` de Playwright, no solo a ojo.

**Limpieza de tipos:** `AnalisisPrensa` en `site/src/lib/datos.ts`
todavía declaraba `menciones_por_autoridad` (ya no existe en el JSON
desde el commit anterior) y no declaraba `top_palabras_por_semana` ni
`tendencia_por_medio` (que sí se usan hace rato en `prensa.astro`) —
corregido de paso.

Verificado con Playwright (desktop y mobile), cero errores de consola.

---

## 2026-09-02 — Prensa regional: se saca "Autoridades más mencionadas" (decisión del usuario) + duplicados de El Día

**"Autoridades más mencionadas" se eliminó del sitio.** Tras dos rondas
de arreglos al emparejamiento de nombres (nombre completo exacto, luego
2 candidatos de nombre corto), el usuario seguía viendo números bajos
poco creíbles para un período de 6 semanas y decidió sacar el bloque en
vez de seguir parchando: "la idea era buena, pero no funciona". Motivo
de fondo (no solo de nombres): mucha prensa local nombra a una
autoridad una sola vez al principio de la nota y después dice solo "el
alcalde" o "la autoridad" — ningún heurístico de coincidencia de texto
puede resolver esa correferencia sin NLP real (que está fuera de
alcance acá). Se sacó por completo: el bloque de la UI, el cálculo de
`menciones_por_autoridad` en `scrapers/analisis_prensa.py` (con los 2
candidatos de nombre corto que se habían agregado hoy mismo), y las
menciones a "autoridades" en las descripciones de la página. Queda
`menciones_por_comuna` nomás (nombre de comuna es un match mucho más
estable, sin este problema). La pestaña "Menciones" pasó a llamarse
"Comunas".

**Duplicados reales en Diario El Día:** el usuario preguntó si una
noticia que aparece en más de uno de los 4 feeds de El Día se cuenta
doble. Investigado: no es por compartir feeds (eso ya dedupea por URL),
pero se encontraron 2 casos reales de la MISMA noticia republicada al
día siguiente con una URL nueva (ID numérico distinto, mismo título) —
esas sí quedaban como dos filas separadas y duplicaban su conteo de
palabras. Se agregó deduplicación por (medio, título normalizado) en
`analisis_prensa.py` antes de tokenizar, quedándose con la fecha más
antigua. 291 → 289 artículos. La explicación principal de por qué El
Día tiene tantas palabras sigue siendo la real: se le leen 4 feeds RSS
temáticos (política/región/país/opinión) mientras que a cada uno de los
otros 24 medios se le lee 1 solo feed general, así que naturalmente
junta ~4x más artículos en la muestra — eso no es un bug, es la
estructura de la fuente.

**"Radio Monte Carlo" → "Radio Montecarlo"** (junto, como el dominio
`radiomontecarlo.cl` y el nombre real de la radio) — corregido en
`scrapers/prensa_rss.py` y en las 10 filas ya guardadas en la base.

Verificado con Playwright en las 7 pestañas, cero errores de consola.

---

## 2026-09-02 — Prensa regional: menciones seguían fallando para nombres compuestos + El Día contaba como 3-4 medios

**Segunda vuelta del bug de menciones:** después del primer fix (nombre
corto = primer nombre + segundo-a-último token), el usuario notó que el
alcalde de Coquimbo no aparecía pese a que Coquimbo es por lejos la
comuna más mencionada (173 noticias). Investigado: su nombre completo es
"Alí Manouchehri Moghadam Kashan Lobos" (5 tokens) — la prensa lo llama
"Alí Manouchehri" (confirmado buscando en el texto crudo), pero el
heurístico A (primer nombre + segundo-a-último token) daba "Alí Kashan",
que no aparece nunca. Mismo problema con el gobernador regional,
"Cristóbal Juliá De La Vega" -> prensa dice "Cristóbal Juliá", el
heurístico A daba "Cristóbal La". En ambos casos el apellido paterno
real es el token justo después del (único) nombre de pila, no el
segundo-a-último — pero eso solo se puede saber con apellidos
compuestos de 3+ palabras, que el heurístico A no contempla.

**Fix:** se agregó un segundo candidato de nombre corto ("B" = primer
nombre + segundo token), verificado por separado contra colisiones
(solo 2 de 142: "Denis Cortés Aguilera/Vargas", "Sergio Alfredo Pérez
Pacheco/Gahona Salazar" — ambos casos raros donde dos personas
distintas comparten primer nombre + segundo nombre). Una autoridad
cuenta como mencionada si aparece su nombre completo, O el candidato A
(si es único), O el candidato B (si es único). Resultado: 43 → 50
autoridades con mención, y ahora sí aparecen el alcalde de Coquimbo (5)
y el gobernador regional (8). Ver `_nombre_corto_a`/`_nombre_corto_b` en
`scrapers/analisis_prensa.py`. **Lección:** con apellidos compuestos o
de origen no español, ningún heurístico posicional único cubre todos
los casos — conviene probar varios candidatos independientes en vez de
afinar uno solo.

**"Diario El Día" contaba como 3-4 medios distintos:** el usuario notó
que aparecía repetido ("País", "Política", "Región") y preguntó por qué
tenía tantas más palabras que el resto — no es que publique más noticias
como medio, es que le leemos 4 feeds RSS temáticos (política/región/
país/opinión) mientras que a cada uno de los otros 24 medios solo se le
lee 1 feed general. Eso le da automáticamente ~4x más artículos en la
muestra (55 vs ~10 de los demás). Se renombraron los 4 feeds a un mismo
nombre de fuente ("Diario El Día") en `scrapers/prensa_rss.py`, se
actualizaron las 55 filas ya guardadas en la base con un `UPDATE`
directo (no hizo falta re-scrapear, el texto ya estaba), y se
recalculó el análisis. La asimetría de volumen se mantiene (es real,
no un bug) pero ahora es 1 medio contando como 1, no como 3-4. Los
textos con el número hardcodeado "28 medios" (portada de herramientas,
encabezado y botón de la página de prensa) se corrigieron a
`{medios.length}` o a texto sin número, para que no quede desactualizado
la próxima vez que cambie la lista de fuentes.

Verificado con Playwright en las 7 pestañas, cero errores de consola.

---

## 2026-09-02 — Prensa regional: bug real en menciones + retoques de UI pedidos por el usuario

**Bug de fondo encontrado y corregido:** `menciones_por_autoridad` buscaba
solo el nombre completo de 4 partes ("Juan Carlos Alfaro Aravena") como
substring del texto — pero la prensa casi nunca escribe así, escribe "el
alcalde Juan Alfaro" o solo "Alfaro". Resultado: apenas 6 de 142
autoridades activas tenían alguna mención en 291 artículos, la mayoría
con 1 sola. El usuario lo notó al ver conteos de 1 y preguntar cómo se
calculaba. Se agregó un "nombre corto" (primer nombre + apellido
paterno) como alternativa de búsqueda, pero **solo cuando ese nombre
corto identifica a una única autoridad activa** — se verificó
programáticamente: de 142 activas, solo 2 pares colisionan ("Denis
Cortés", "Juan Castillo"), esos quedan con el nombre completo exacto
nomás para no confundir personas. Resultado: 6 → 43 autoridades con
mención, con nombres que tienen sentido (alcaldes de comunas grandes
arriba del ranking). Ver `scrapers/analisis_prensa.py`.

**Retoques de UI (los otros 4 puntos del feedback):**
- Menciones y Palabras más usadas ahora muestran el rango de fechas
  analizado (ya existía `rangoTotalTexto`, solo faltaba usarlo ahí).
- El número de menciones de comuna se veía partido en dos líneas cuando
  llegaba a 3 dígitos (Coquimbo, 173) — el `<span>` no tenía
  `whitespace-nowrap` y era muy angosto (`w-20`); ahora `w-24` +
  `whitespace-nowrap`.
- "Palabras más usadas": el `<select>` de medio se reemplazó por una
  barra lateral de botones (columna izquierda en desktop, chips con
  scroll horizontal en mobile) — pedido explícito del usuario.
- "Comparar palabras": ya no viene nada marcado por defecto (antes se
  pre-seleccionaban 3) — ahora se muestra un mensaje ("elige al menos
  una palabra") hasta que el usuario marca algo.
- "Top palabras de una semana, por medio" (barras apiladas): el hover
  usaba el `title` nativo del navegador (lento, feo, sin estilo); ahora
  tiene el mismo tooltip custom que el resto de los gráficos de la
  página (medio + cantidad).

**Decisión de diseño — Tendencia semanal pasó a ser un bump chart real:**
el usuario pidió ideas para que el gráfico de líneas (que mostraba
frecuencia cruda) se viera menos "aburrido". Se le presentaron 3
opciones (bump chart de ranking, mismo gráfico pulido con curvas, o
tarjetas con mini-sparklines) y eligió el bump chart — que además es
literalmente lo que había pedido desde el principio del proyecto
("gráfico de tendencia (bump chart)"), solo que la primera
implementación terminó siendo un gráfico de magnitud por error de
interpretación. Ahora el eje Y es el lugar (1° a 8°) que ocupa cada
palabra esa semana entre las 8 seguidas, no su frecuencia — las líneas
se cruzan cuando una palabra le gana el lugar a otra. La frecuencia real
se conserva en el tooltip. Empates de frecuencia se resuelven
alfabéticamente para que el ranking 1..8 quede siempre completo sin
lugares repetidos (verificado, sin efecto visible raro en las 9 semanas
de datos actuales).

Verificado con Playwright en las 7 pestañas, cero errores de consola.

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

**Fase 4 (hecha, `/herramientas/prensa/`):** página nueva, clon casi
exacto del layout de `/parlamentarios/discursos/` (misma nube de
palabras y red de coocurrencia en canvas, ambas genéricas — no dependían
del concepto de "diputado" así que se reutilizaron sin cambios de
lógica, solo de datos de entrada). La única pestaña realmente nueva es
"Menciones" (autoridades y comunas más mencionadas), que no existe en
`prensa_chile` de Bastián — es la parte propia de un observatorio
regional. Verificado con Playwright en las 4 pestañas, sin errores de
consola. Página de 80KB.

**Proyecto de prensa regional completo (4 fases) por ahora.** Pendiente
real para más adelante: decidir la cadencia de actualización (¿diaria
vía un workflow nuevo, o semanal junto con el resto?), y si vale la pena
scrapear el archivo histórico de cada medio en vez de depender solo de
lo que cada RSS trae disponible (~10 noticias recientes por fuente).

**Corrección (mismo día): la Fase 4 NO estaba completa.** El usuario
había propuesto 6 módulos concretos (tendencia en gráfico de líneas,
comparar palabras elegidas, nube por semana, top palabras por semana
por medio en barras apiladas, un concepto elegido en el tiempo por
medio, co-ocurrencia) más "Menciones" como aporte propio del
observatorio — 8 en total. La primera versión de `/herramientas/prensa/`
solo tenía 4 pestañas y la de "Tendencia" era una matriz tipo
heat-map, no el gráfico de líneas pedido. El usuario lo notó
("no es lo que me habías propuesto... no muestra la tendencia de
palabras en gráfico"). Se corrigió la tendencia a un SVG de líneas real
(top-8 palabras, paleta fija de 8 colores, `lunesDeSemanaISO()` para
mostrar rango de fechas real en vez de "Sem 31"). Más tarde el usuario
volvió a pegar la lista completa de 6 módulos y preguntó directo "¿esto
es lo propuesto, esta todo?" — autoevaluación honesta: faltaban 4 de 6
(comparar palabras, nube por semana, barras por medio, concepto por
medio en el tiempo). Se construyeron los 4 en `scrapers/analisis_prensa.py`
(nuevos campos `top_palabras_por_semana` y `tendencia_por_medio`) y en
`prensa.astro` (7 pestañas final: Menciones, Palabras más usadas,
Tendencia, Comparar palabras, Nube por semana, Por medio, Red de
palabras). "Por medio" tiene dos vistas: barras apiladas por semana
(top-5 medios + "Otros" en gris, no un color por cada uno de los ~27
medios) y el concepto elegido en el tiempo separado por medio (redibujo
client-side porque cada palabra tiene su propia escala Y). Build
verificado (210 páginas) y Playwright en las 7 pestañas sin errores de
consola. **Ahora sí, completo: los 6 módulos de Bastián + Menciones.**

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
