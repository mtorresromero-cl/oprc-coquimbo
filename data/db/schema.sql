-- Esquema inicial de la base de datos del Observatorio Político Región de Coquimbo.
-- Ver docs/04-modelos-de-datos.md para el diseño y las relaciones.

CREATE TABLE IF NOT EXISTS autoridad (
    id              TEXT PRIMARY KEY,       -- slug: "juan-perez-alcalde-la-serena"
    nombre          TEXT NOT NULL,
    apellido        TEXT NOT NULL,
    nombre_completo TEXT NOT NULL,
    cargo           TEXT NOT NULL,           -- alcalde | concejal | core | diputado | senador | gobernador
    partido         TEXT,
    pacto           TEXT,                    -- coalición electoral
    comuna          TEXT,                    -- NULL para senadores/gobernadora
    distrito        TEXT,                    -- para diputados
    circunscripcion TEXT,                    -- para senadores y CORE
    periodo_inicio  DATE,
    periodo_fin     DATE,
    foto_url        TEXT,
    email           TEXT,
    activo          BOOLEAN DEFAULT TRUE,
    fuente          TEXT,                    -- de dónde se obtuvo el dato
    actualizado_en  DATETIME
);

CREATE TABLE IF NOT EXISTS comuna (
    id              TEXT PRIMARY KEY,       -- slug: "la-serena"
    nombre          TEXT NOT NULL,
    provincia       TEXT NOT NULL,           -- Elqui | Limarí | Choapa
    poblacion       INTEGER,
    superficie_km2  REAL,
    geojson         TEXT,                   -- geometría para el mapa
    actualizado_en  DATETIME
);

CREATE TABLE IF NOT EXISTS votacion_sesion (
    id              TEXT PRIMARY KEY,
    camara          TEXT NOT NULL,           -- camara | senado | core
    fecha           DATE NOT NULL,
    numero_sesion   TEXT,
    tipo            TEXT,                    -- ordinaria | extraordinaria | especial
    proyecto_ley_id TEXT,
    descripcion     TEXT,
    resultado       TEXT,                    -- aprobado | rechazado
    votos_favor     INTEGER,
    votos_contra    INTEGER,
    abstenciones    INTEGER,
    fuente_url      TEXT,
    FOREIGN KEY (proyecto_ley_id) REFERENCES proyecto_ley(id)
);

CREATE TABLE IF NOT EXISTS voto (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    autoridad_id    TEXT NOT NULL,
    sesion_id       TEXT NOT NULL,
    voto            TEXT NOT NULL,           -- favor | contra | abstencion | pareo | ausente | inhabilitado
    fecha           DATE NOT NULL,
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id),
    FOREIGN KEY (sesion_id) REFERENCES votacion_sesion(id),
    UNIQUE(autoridad_id, sesion_id)
);

CREATE TABLE IF NOT EXISTS asistencia (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    autoridad_id    TEXT NOT NULL,
    camara          TEXT NOT NULL,           -- camara | senado | core | concejo
    fecha           DATE NOT NULL,
    numero_sesion   TEXT,
    presente        BOOLEAN NOT NULL,
    justificacion   TEXT,                    -- si ausente, razón si existe
    fuente_url      TEXT,
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id)
);

CREATE TABLE IF NOT EXISTS proyecto_ley (
    id              TEXT PRIMARY KEY,       -- boletín: "12345-06"
    titulo          TEXT NOT NULL,
    descripcion     TEXT,
    fecha_ingreso   DATE,
    estado          TEXT,                    -- en_tramitacion | aprobado | rechazado | archivado
    camara_origen   TEXT,                    -- camara | senado
    tipo            TEXT,                    -- mocion | mensaje
    materia         TEXT,                    -- categoría temática
    relevancia_regional TEXT,               -- por qué importa para Coquimbo
    url_bcn         TEXT,
    actualizado_en  DATETIME
);

CREATE TABLE IF NOT EXISTS mocion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    autoridad_id    TEXT NOT NULL,
    proyecto_ley_id TEXT NOT NULL,
    fecha           DATE NOT NULL,
    rol             TEXT,                    -- autor | coautor
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id),
    FOREIGN KEY (proyecto_ley_id) REFERENCES proyecto_ley(id)
);

-- Resumen de asistencia del período tal como lo publican las fuentes
-- oficiales (camara.cl para diputados, senado.cl para senadores) — totales
-- ya calculados por cada fuente, no derivados de sesiones individuales que
-- alcancemos a scrapear nosotros. Compartida entre ambas cámaras porque el
-- shape es el mismo; camara.cl distingue ausencias justificadas que
-- afectan o no el % (se suman en ausencias_justificadas, ese detalle no se
-- usa en ningún cálculo, solo se muestra el total en la UI).
CREATE TABLE IF NOT EXISTS asistencia_resumen (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    autoridad_id              TEXT NOT NULL,
    camara                    TEXT NOT NULL,           -- camara | senado
    anno                      INTEGER NOT NULL,
    total_sesiones            INTEGER,
    sesiones_computables      INTEGER,
    asistencias               INTEGER,
    ausencias_justificadas    INTEGER,
    ausencias_sin_justificar  INTEGER,
    fuente_url                TEXT,
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id)
);

-- Resumen agregado de la declaración de patrimonio vigente (no itemizado:
-- infoprobidad.cl publica el detalle completo de cada bien/sociedad/deuda,
-- pero seguimos el mismo criterio que personal_municipal — totales
-- comparables entre autoridades, no el detalle línea por línea).
CREATE TABLE IF NOT EXISTS declaracion_patrimonio (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    autoridad_id        TEXT NOT NULL,
    fecha_declaracion   DATE NOT NULL,
    tipo_declaracion    TEXT,               -- ej. "Actualización Periódica (Marzo)"
    cargo_declarado     TEXT,               -- cargo tal como figura en infoprobidad
    organismo           TEXT,
    bienes_inmuebles_n  INTEGER,
    vehiculos_n         INTEGER,
    sociedades_n        INTEGER,
    valores_monto       REAL,
    pasivos_tiene       INTEGER,            -- 0/1
    pasivos_monto       REAL,
    fuente_url          TEXT,
    actualizado_en      DATETIME,
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id)
);

CREATE TABLE IF NOT EXISTS presupuesto_municipal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comuna_id       TEXT NOT NULL,
    anno            INTEGER NOT NULL,
    mes             INTEGER,                -- NULL si es anual
    tipo            TEXT NOT NULL,           -- ingreso | gasto
    categoria       TEXT NOT NULL,           -- clasificación presupuestaria
    subcategoria    TEXT,
    monto           REAL NOT NULL,           -- en pesos chilenos
    fuente_url      TEXT,
    actualizado_en  DATETIME,
    FOREIGN KEY (comuna_id) REFERENCES comuna(id)
);

CREATE TABLE IF NOT EXISTS personal_municipal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comuna_id       TEXT NOT NULL,
    anno            INTEGER NOT NULL,
    mes             INTEGER NOT NULL,
    area            TEXT NOT NULL,           -- municipal | salud | educacion
    tipo_contrato   TEXT NOT NULL,           -- planta | contrata | honorarios
    dotacion        INTEGER NOT NULL,        -- cantidad de personas
    remuneracion_total REAL NOT NULL,        -- suma de remuneración bruta del mes, en pesos
    fuente_url      TEXT,
    actualizado_en  DATETIME,
    FOREIGN KEY (comuna_id) REFERENCES comuna(id)
);

CREATE TABLE IF NOT EXISTS remuneracion_autoridad (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comuna_id       TEXT NOT NULL,
    anno            INTEGER NOT NULL,
    mes             INTEGER NOT NULL,
    cargo           TEXT NOT NULL,           -- ej. "ALCALDE"
    remuneracion_bruta REAL NOT NULL,
    fuente_url      TEXT,
    actualizado_en  DATETIME,
    FOREIGN KEY (comuna_id) REFERENCES comuna(id)
);

CREATE TABLE IF NOT EXISTS transparencia_cumplimiento (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comuna_id       TEXT NOT NULL,
    anno            INTEGER NOT NULL,
    periodo         TEXT,                    -- semestre o evaluación
    puntaje         REAL,                    -- 0-100
    categoria       TEXT,                    -- destacada | cumple | no_cumple
    detalle         TEXT,                    -- JSON con desglose
    fuente_url      TEXT,
    FOREIGN KEY (comuna_id) REFERENCES comuna(id)
);

CREATE TABLE IF NOT EXISTS resultado_electoral (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    eleccion_tipo   TEXT NOT NULL,           -- municipal | core | diputados | senadores | presidencial
    anno            INTEGER NOT NULL,
    comuna_id       TEXT,
    candidato       TEXT NOT NULL,
    partido         TEXT,
    pacto           TEXT,
    votos           INTEGER NOT NULL,
    porcentaje      REAL,
    electo          BOOLEAN,
    cargo           TEXT,                    -- cargo al que postuló
    fuente_url      TEXT,
    FOREIGN KEY (comuna_id) REFERENCES comuna(id)
);

CREATE TABLE IF NOT EXISTS padron_demografico (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada        TEXT NOT NULL,           -- misma jornada que participacion_electoral
    anno           INTEGER NOT NULL,
    comuna_id      TEXT NOT NULL,
    sexo           TEXT NOT NULL,           -- HOMBRES | MUJERES
    rango_etario   TEXT NOT NULL,           -- 18-19 | 20-29 | ... | 80+
    extranjero     BOOLEAN NOT NULL,        -- nacionalidad declarada != CHILE
    votantes       INTEGER NOT NULL,
    FOREIGN KEY (comuna_id) REFERENCES comuna(id)
);

CREATE TABLE IF NOT EXISTS participacion_electoral (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada            TEXT NOT NULL,           -- identifica el día de votación (agrupa varias elecciones simultáneas)
    anno               INTEGER NOT NULL,
    etiqueta           TEXT NOT NULL,           -- descripción legible de la jornada
    tipos_relacionados TEXT,                    -- eleccion_tipo de resultado_electoral vigentes ese día, separados por coma
    comuna_id          TEXT NOT NULL,
    inscritos          INTEGER,
    votantes           INTEGER,
    participacion_pct  REAL,
    FOREIGN KEY (comuna_id) REFERENCES comuna(id)
);

CREATE TABLE IF NOT EXISTS actualizacion_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scraper         TEXT NOT NULL,           -- nombre del scraper
    inicio          DATETIME NOT NULL,
    fin             DATETIME,
    estado          TEXT,                    -- ok | error | sin_cambios
    registros_nuevos INTEGER DEFAULT 0,
    registros_actualizados INTEGER DEFAULT 0,
    error_mensaje   TEXT,
    detalle         TEXT                     -- JSON con info adicional
);

CREATE INDEX IF NOT EXISTS idx_voto_autoridad ON voto(autoridad_id);
CREATE INDEX IF NOT EXISTS idx_voto_fecha ON voto(fecha);
CREATE INDEX IF NOT EXISTS idx_asistencia_autoridad ON asistencia(autoridad_id);
CREATE INDEX IF NOT EXISTS idx_asistencia_fecha ON asistencia(fecha);
CREATE INDEX IF NOT EXISTS idx_patrimonio_autoridad ON declaracion_patrimonio(autoridad_id);
CREATE INDEX IF NOT EXISTS idx_presupuesto_comuna ON presupuesto_municipal(comuna_id, anno);
CREATE INDEX IF NOT EXISTS idx_personal_comuna ON personal_municipal(comuna_id, anno, mes);
CREATE INDEX IF NOT EXISTS idx_remuneracion_autoridad_comuna ON remuneracion_autoridad(comuna_id, anno, mes);
CREATE INDEX IF NOT EXISTS idx_resultado_electoral ON resultado_electoral(anno, eleccion_tipo, comuna_id);
CREATE INDEX IF NOT EXISTS idx_participacion_electoral ON participacion_electoral(anno, comuna_id);
CREATE INDEX IF NOT EXISTS idx_padron_demografico ON padron_demografico(anno, comuna_id);

-- Índices únicos para historización: permiten INSERT ... ON CONFLICT DO
-- UPDATE (upsert) por período real en vez de borrar-todo-y-reinsertar, que
-- destruía cualquier corrida anterior a la última. Con esto, cada semana
-- que aparece un período nuevo (mes/año/declaración) se agrega sin pisar
-- los períodos ya guardados.
CREATE UNIQUE INDEX IF NOT EXISTS ux_personal_municipal
    ON personal_municipal(comuna_id, anno, mes, area, tipo_contrato);
CREATE UNIQUE INDEX IF NOT EXISTS ux_remuneracion_autoridad
    ON remuneracion_autoridad(comuna_id, anno, mes, cargo);
CREATE UNIQUE INDEX IF NOT EXISTS ux_presupuesto_municipal
    ON presupuesto_municipal(comuna_id, anno, tipo, categoria, subcategoria);
CREATE UNIQUE INDEX IF NOT EXISTS ux_declaracion_patrimonio
    ON declaracion_patrimonio(autoridad_id, fecha_declaracion);
CREATE UNIQUE INDEX IF NOT EXISTS ux_asistencia
    ON asistencia(autoridad_id, camara, fecha, numero_sesion);
CREATE UNIQUE INDEX IF NOT EXISTS ux_asistencia_resumen
    ON asistencia_resumen(autoridad_id, camara, anno);
CREATE UNIQUE INDEX IF NOT EXISTS ux_participacion_electoral
    ON participacion_electoral(jornada, comuna_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_padron_demografico
    ON padron_demografico(jornada, comuna_id, sexo, rango_etario, extranjero);

CREATE TABLE IF NOT EXISTS gasto_parlamentario (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    autoridad_id    TEXT NOT NULL,           -- mismo id que autoridad.id
    anno            INTEGER NOT NULL,
    mes             INTEGER NOT NULL,
    categoria       TEXT NOT NULL,           -- gastos_operacionales | asesorias_externas | pasajes_aereos | personal_apoyo
    publicado       BOOLEAN NOT NULL,        -- si la Camara ya publico ese mes/categoria (false = pendiente, no es un cero real)
    monto           REAL,
    cantidad        INTEGER,
    detalle         TEXT,                    -- JSON: lista de items ([{concepto,monto}] o [{nombre,monto,...}])
    fuente_url      TEXT,
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gasto_parlamentario
    ON gasto_parlamentario(autoridad_id, anno, mes, categoria);

CREATE TABLE IF NOT EXISTS intervencion_sala (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id       TEXT NOT NULL,           -- id interno de camara.cl (prmid del boletin)
    numero_sesion   INTEGER NOT NULL,
    etiqueta_sesion TEXT NOT NULL,           -- ej. "31ª, martes 9 junio 2026"
    autoridad_id    TEXT,                    -- NULL = sesion revisada, nadie de la region intervino
    tipo            TEXT,                    -- Discurso a favor | Discurso en contra | Incidentes | ...
    detalle         TEXT,                    -- item/boletin sobre el que intervino
    duracion        TEXT,                    -- mm:ss tal como lo publica camara.cl
    texto           TEXT,                    -- texto real de la intervencion (boletin PDF), o NULL si no se pudo extraer
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_intervencion_sala
    ON intervencion_sala(sesion_id, autoridad_id, tipo, detalle);

CREATE TABLE IF NOT EXISTS intervencion_sala_senado (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id       TEXT NOT NULL,           -- ID_SESION de senado.cl
    numero_sesion   INTEGER,                 -- NRO_SESION (puede venir NULL en sesiones especiales)
    etiqueta_sesion TEXT NOT NULL,           -- "NRO_SESION / NRO_LEGISLATURA", ej. "1 / 374"
    fecha           TEXT,                    -- FECHA tal como la publica senado.cl, dd/mm/aaaa
    tag             INTEGER NOT NULL,        -- posición de la intervención dentro de la sesión (.../{sesion_id}/{tag})
    autoridad_id    TEXT,                    -- NULL = sesion revisada, ningun senador de la region intervino
    tema            TEXT,                    -- TEMA de la intervencion
    boletin         TEXT,                    -- BOLETIN del proyecto de ley, si aplica
    texto           TEXT,                    -- TEXTO completo de la intervencion, tal como lo publica senado.cl
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_intervencion_sala_senado
    ON intervencion_sala_senado(sesion_id, tag);
