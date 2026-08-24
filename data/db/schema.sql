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
    camara          TEXT NOT NULL,           -- camara | senado
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
    voto            TEXT NOT NULL,           -- favor | contra | abstencion | pareo | ausente
    fecha           DATE NOT NULL,
    FOREIGN KEY (autoridad_id) REFERENCES autoridad(id),
    FOREIGN KEY (sesion_id) REFERENCES votacion_sesion(id),
    UNIQUE(autoridad_id, sesion_id)
);

CREATE TABLE IF NOT EXISTS asistencia (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    autoridad_id    TEXT NOT NULL,
    camara          TEXT NOT NULL,           -- camara | senado | concejo | core
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

CREATE TABLE IF NOT EXISTS declaracion_patrimonio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    autoridad_id    TEXT NOT NULL,
    tipo            TEXT NOT NULL,           -- patrimonio | intereses
    fecha           DATE NOT NULL,
    bienes_inmuebles    TEXT,               -- JSON array
    vehiculos           TEXT,               -- JSON array
    derechos_agua       TEXT,               -- JSON array
    participaciones     TEXT,               -- JSON array (empresas)
    valor_total_estimado REAL,
    actividades         TEXT,               -- JSON array
    url_fuente      TEXT,
    hash_contenido  TEXT,                   -- para detectar cambios
    actualizado_en  DATETIME,
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
