import fs from 'node:fs';
import path from 'node:path';

export interface Autoridad {
	id: string;
	nombre: string;
	apellido: string;
	nombre_completo: string;
	cargo: string;
	partido: string | null;
	pacto: string | null;
	comuna: string | null;
	distrito: string | null;
	circunscripcion: string | null;
	periodo_inicio: string | null;
	periodo_fin: string | null;
	foto_url: string | null;
	email: string | null;
	activo: number;
	fuente: string | null;
	actualizado_en: string | null;
}

export interface Comuna {
	id: string;
	nombre: string;
	provincia: string;
	poblacion: number | null;
	superficie_km2: number | null;
	geojson: string | null;
	actualizado_en: string | null;
}

export interface Voto {
	autoridad_id: string;
	voto: string;
}

export interface VotacionSesion {
	id: string;
	camara: string;
	fecha: string;
	numero_sesion: string | null;
	descripcion: string | null;
	resultado: string | null;
	votos_favor: number | null;
	votos_contra: number | null;
	abstenciones: number | null;
	fuente_url: string | null;
	votos: Voto[];
}

export interface Mocion {
	autoridad_id: string;
	fecha: string;
	rol: string;
	boletin: string;
	titulo: string;
	estado?: string;
	url_bcn: string;
}

export interface PresupuestoItem {
	comuna_id: string;
	anno: number;
	tipo: string;
	categoria: string;
	subcategoria: string;
	monto: number;
	fuente_url: string;
}

export interface PersonalItem {
	comuna_id: string;
	anno: number;
	mes: number;
	area: string;
	tipo_contrato: string;
	dotacion: number;
	remuneracion_total: number;
	fuente_url: string;
}

export interface RemuneracionAutoridad {
	comuna_id: string;
	anno: number;
	mes: number;
	cargo: string;
	remuneracion_bruta: number;
	fuente_url: string;
}

export interface DeclaracionPatrimonio {
	autoridad_id: string;
	fecha_declaracion: string;
	tipo_declaracion: string | null;
	cargo_declarado: string | null;
	organismo: string | null;
	bienes_inmuebles_n: number;
	vehiculos_n: number;
	sociedades_n: number;
	valores_monto: number;
	pasivos_tiene: number;
	pasivos_monto: number;
	fuente_url: string;
}

export interface AsistenciaResumen {
	autoridad_id: string;
	camara: 'camara' | 'senado';
	// año calendario para diputados (camara.cl); número de legislatura para
	// senadores (senado.cl no reporta por año calendario) — no comparar
	// directamente entre cámaras, usar etiquetaPeriodoAsistencia().
	anno: number;
	total_sesiones: number;
	sesiones_computables: number;
	asistencias: number;
	ausencias_justificadas: number;
	ausencias_sin_justificar: number;
	fuente_url: string;
}

export function etiquetaPeriodoAsistencia(r: AsistenciaResumen): string {
	return r.camara === 'senado' ? `Legislatura ${r.anno}` : String(r.anno);
}

export interface AsistenciaSesionDiputado {
	autoridad_id: string;
	fecha: string;
	numero_sesion: string;
	presente: number;
	justificacion: string | null;
	fuente_url: string;
}

import autoridadesRaw from '../../../data/processed/autoridades.json';
import comunasRaw from '../../../data/processed/comunas.json';
import votacionesRaw from '../../../data/processed/votaciones.json';
import votacionesCoreRaw from '../../../data/processed/votaciones-core.json';
import votacionesCamaraRaw from '../../../data/processed/votaciones-camara.json';
import mocionesRaw from '../../../data/processed/mociones.json';
import mocionesSenadoresRaw from '../../../data/processed/mociones-senadores.json';
import presupuestoRaw from '../../../data/processed/presupuesto-municipal.json';
import personalRaw from '../../../data/processed/personal-municipal.json';
import remuneracionAutoridadRaw from '../../../data/processed/remuneracion-autoridad.json';
import declaracionesPatrimonioRaw from '../../../data/processed/declaracion-patrimonio.json';
import asistenciaResumenDiputadosRaw from '../../../data/processed/asistencia-resumen-diputados.json';
import asistenciaResumenSenadoresRaw from '../../../data/processed/asistencia-resumen-senadores.json';
import asistenciaDiputadosRaw from '../../../data/processed/asistencia-diputados.json';

export const autoridades: Autoridad[] = autoridadesRaw as Autoridad[];
export const comunas: Comuna[] = comunasRaw as Comuna[];
export const votaciones: VotacionSesion[] = votacionesRaw as VotacionSesion[];
export const votacionesCore: VotacionSesion[] = votacionesCoreRaw as VotacionSesion[];
export const votacionesCamara: VotacionSesion[] = votacionesCamaraRaw as VotacionSesion[];
export const mociones: Mocion[] = [
	...(mocionesRaw as Mocion[]),
	...(mocionesSenadoresRaw as Mocion[]),
];
export const presupuesto: PresupuestoItem[] = presupuestoRaw as PresupuestoItem[];
export const personal: PersonalItem[] = personalRaw as PersonalItem[];
export const remuneracionAutoridad: RemuneracionAutoridad[] = remuneracionAutoridadRaw as RemuneracionAutoridad[];
export const declaracionesPatrimonio: DeclaracionPatrimonio[] =
	declaracionesPatrimonioRaw as DeclaracionPatrimonio[];
export const asistenciaResumen: AsistenciaResumen[] = [
	...(asistenciaResumenDiputadosRaw as AsistenciaResumen[]),
	...(asistenciaResumenSenadoresRaw as AsistenciaResumen[]),
];
export const asistenciaDiputados: AsistenciaSesionDiputado[] =
	asistenciaDiputadosRaw as AsistenciaSesionDiputado[];

export function presupuestoDeComuna(comunaId: string) {
	return presupuesto.filter((p) => p.comuna_id === comunaId);
}

export function personalDeComuna(comunaId: string) {
	// personal ahora acumula histórico (varios meses por comuna) — se
	// muestra solo el período más reciente, si no se sumarían dotación y
	// remuneraciones de distintos meses. personal ya viene ordenado
	// anno DESC, mes DESC desde el scraper, así que el primer registro de
	// la comuna define el período vigente.
	const deComuna = personal.filter((p) => p.comuna_id === comunaId);
	const vigente = deComuna[0];
	if (!vigente) return [];
	return deComuna.filter((p) => p.anno === vigente.anno && p.mes === vigente.mes);
}

export function remuneracionAutoridadDeComuna(comunaId: string) {
	return remuneracionAutoridad.filter((r) => r.comuna_id === comunaId);
}

export interface ComparativaMunicipal {
	comuna_id: string;
	nombre: string;
	periodoPersonal: string | null;
	dotacionTotal: number;
	remuneracionTotal: number;
	dotacionPlanta: number;
	dotacionContrata: number;
	dotacionHonorarios: number;
	tienePresupuesto: boolean;
	annoPresupuesto: number | null;
	tieneIngresos: boolean;
	tieneGastos: boolean;
	ingresosTotal: number;
	gastosTotal: number;
}

/**
 * Comparativa entre comunas con los totales que ya tenemos. Son montos
 * absolutos, no per cápita: no tenemos población real todavía (el campo
 * existe en el catálogo pero nunca se completó), así que una comuna
 * grande va a aparecer arriba en dotación/gasto simplemente por tener más
 * habitantes, no porque gaste "peor" que una chica.
 */
export function comparativaMunicipal(): ComparativaMunicipal[] {
	return comunas.map((c) => {
		const suPersonal = personalDeComuna(c.id);
		const suPresupuesto = presupuestoDeComuna(c.id);
		const annoPresupuesto = suPresupuesto.length
			? Math.max(...suPresupuesto.map((p) => p.anno))
			: null;
		const delAnno = suPresupuesto.filter((p) => p.anno === annoPresupuesto);
		const ingresosDelAnno = delAnno.filter((p) => p.tipo === 'ingreso');
		const gastosDelAnno = delAnno.filter((p) => p.tipo === 'gasto');

		const porTipo = (tipo: string) =>
			suPersonal.filter((p) => p.tipo_contrato === tipo).reduce((s, p) => s + p.dotacion, 0);

		return {
			comuna_id: c.id,
			nombre: c.nombre,
			periodoPersonal: suPersonal[0] ? `${suPersonal[0].mes}/${suPersonal[0].anno}` : null,
			dotacionTotal: suPersonal.reduce((s, p) => s + p.dotacion, 0),
			remuneracionTotal: suPersonal.reduce((s, p) => s + p.remuneracion_total, 0),
			dotacionPlanta: porTipo('planta'),
			dotacionContrata: porTipo('contrata'),
			dotacionHonorarios: porTipo('honorarios'),
			tienePresupuesto: suPresupuesto.length > 0,
			annoPresupuesto,
			// ingreso y gasto se registran como filas separadas del mismo tipo de
			// dato: algunas comunas solo tienen uno de los dos capturado para su
			// año más reciente. 0 filas de un tipo no significa monto real 0.
			tieneIngresos: ingresosDelAnno.length > 0,
			tieneGastos: gastosDelAnno.length > 0,
			ingresosTotal: ingresosDelAnno.reduce((s, p) => s + p.monto, 0),
			gastosTotal: gastosDelAnno.reduce((s, p) => s + p.monto, 0),
		};
	});
}

export const AREA_LABEL: Record<string, string> = {
	municipal: 'Municipal',
	salud: 'Salud',
	educacion: 'Educación',
};

export const TIPO_CONTRATO_LABEL: Record<string, string> = {
	planta: 'Planta',
	contrata: 'Contrata',
	honorarios: 'Honorarios',
};

export function mocionesDeAutoridad(autoridadId: string) {
	return mociones.filter((m) => m.autoridad_id === autoridadId);
}

export function declaracionPatrimonioDeAutoridad(autoridadId: string) {
	return declaracionesPatrimonio.find((d) => d.autoridad_id === autoridadId) ?? null;
}

export function asistenciaResumenDeAutoridad(autoridadId: string) {
	// puede haber más de un período acumulado con el tiempo; se muestra el
	// más reciente, igual que con personalDeComuna.
	const delAutoridad = asistenciaResumen
		.filter((a) => a.autoridad_id === autoridadId)
		.sort((a, b) => b.anno - a.anno);
	return delAutoridad[0] ?? null;
}

export function asistenciaSesionesDeAutoridad(autoridadId: string) {
	return asistenciaDiputados.filter((a) => a.autoridad_id === autoridadId);
}

export const VOTO_LABEL: Record<string, string> = {
	favor: 'A favor',
	contra: 'En contra',
	abstencion: 'Abstención',
	pareo: 'Pareo',
	ausente: 'Ausente',
	inhabilitado: 'Se inhabilita',
	dispensado: 'Dispensado/a de votar',
};

export function votacionesDeAutoridad(autoridadId: string) {
	return [...votaciones, ...votacionesCore, ...votacionesCamara]
		.map((v) => ({ sesion: v, voto: v.votos.find((x) => x.autoridad_id === autoridadId) }))
		.filter((x) => x.voto);
}

export const CARGOS = ['senador', 'diputado', 'gobernador', 'core', 'alcalde', 'concejal'] as const;

export const CARGO_LABEL: Record<string, string> = {
	alcalde: 'Alcalde/sa',
	concejal: 'Concejal/a',
	core: 'Consejero/a Regional',
	diputado: 'Diputado/a',
	senador: 'Senador/a',
	gobernador: 'Gobernador/a Regional',
};

export const GRUPO_LABEL: Record<string, string> = {
	senador: 'Senadores',
	diputado: 'Diputados',
	gobernador: 'Gobernador Regional',
	core: 'Consejo Regional',
	alcalde: 'Alcaldes',
	concejal: 'Concejales',
};

// Fotos de autoridades: se suben manualmente a site/public/autoridades/,
// nombradas exactamente como el id de la autoridad (el mismo slug que usa
// su URL /autoridades/{id}/), en jpg/jpeg/png/webp. Si no existe el
// archivo, se usa el fallback de iniciales en el template.
const FOTOS_DIR = path.join(process.cwd(), 'public', 'autoridades');
const EXTENSIONES_FOTO = ['jpg', 'jpeg', 'png', 'webp'];

export function fotoAutoridad(id: string): string | null {
	for (const ext of EXTENSIONES_FOTO) {
		if (fs.existsSync(path.join(FOTOS_DIR, `${id}.${ext}`))) {
			return `/autoridades/${id}.${ext}`;
		}
	}
	return null;
}

export function nombreComuna(comunaId: string | null): string | null {
	if (!comunaId) return null;
	return comunas.find((c) => c.id === comunaId)?.nombre ?? comunaId;
}

// El campo partido viene de distintas fuentes (SERVEL, BCN, sitios
// institucionales) sin normalizar: el mismo partido aparece con su nombre
// completo, con sigla entre paréntesis, o solo la sigla. Estas son las
// variantes reales observadas en los datos de diputados/senadores/core/
// gobernador (2026-08-25) — no es una función genérica porque prefiere
// listar explícitamente lo que se está uniendo, en vez de adivinar con un
// regex que podría fusionar partidos distintos por error.
const PARTIDO_ALIAS: Record<string, string> = {
	'Partido Comunista de Chile': 'Partido Comunista',
	'Partido Comunista (PC)': 'Partido Comunista',
	'Partido Socialista de Chile': 'Partido Socialista',
	'Partido Socialista (PS)': 'Partido Socialista',
	'Partido Socialista de Chile (PS)': 'Partido Socialista',
	PS: 'Partido Socialista',
	'Unión Demócrata Independiente (UDI)': 'Unión Demócrata Independiente',
	'Frente Amplio (FA)': 'Frente Amplio',
	'Partido de la Gente (PDG)': 'Partido de la Gente',
	'Partido Nacional Libertario (PNL)': 'Partido Nacional Libertario',
	'Independiente (cupo PC, lista Unidad por Chile)': 'Independiente',
	'Renovación Nacional (RN)': 'Renovación Nacional',
	RN: 'Renovación Nacional',
	'Partido Republicano de Chile': 'Partido Republicano',
	'Partido Demócrata Cristiano (PDC)': 'Partido Demócrata Cristiano',
	DC: 'Partido Demócrata Cristiano',
	'Partido Por la Democracia (PPD)': 'Partido Por la Democracia',
	'Partido Demócratas Chile': 'Partido Demócratas',
	Demócratas: 'Partido Demócratas',
};

export interface ComposicionPartido {
	partido: string;
	total: number;
}

/**
 * Composición por partido de las 142 autoridades (alcaldes, concejales,
 * consejeros regionales, gobernador, diputados y senadores). Normaliza
 * variantes reales observadas en los datos (siglas, "de Chile", etc.) vía
 * PARTIDO_ALIAS de forma explícita, en vez de un regex que podría fusionar
 * partidos distintos por error.
 */
export function composicionPartidoTodos(): ComposicionPartido[] {
	const conteo = new Map<string, number>();
	for (const a of autoridades) {
		if (!a.partido) continue;
		const partido = PARTIDO_ALIAS[a.partido] ?? a.partido;
		conteo.set(partido, (conteo.get(partido) ?? 0) + 1);
	}
	return [...conteo.entries()]
		.map(([partido, total]) => ({ partido, total }))
		.sort((a, b) => b.total - a.total);
}

export interface IndiceVotacion {
	autoridad_id: string;
	nombre: string;
	cargo: string;
	favor: number;
	contra: number;
	abstencion: number;
	pareo: number;
	ausente: number;
	inhabilitado: number;
	dispensado: number;
	participacionPct: number;
	alineamientoPct: number | null;
}

function nombreYCargo(autoridadId: string): { nombre: string; cargo: string } {
	const a = autoridades.find((x) => x.id === autoridadId);
	return { nombre: a?.nombre_completo ?? autoridadId, cargo: a?.cargo ?? '' };
}

/**
 * Métricas de votación por autoridad: participación (% de sesiones donde
 * emitió un voto real, contando como ausente tanto los "ausente"
 * explícitos como el simple no-aparecer en la sesión — el Senado no
 * registra ausencias, solo omite a quien no votó) y alineamiento (%, de
 * los votos favor/contra, que coincidieron con el resultado final de la
 * sesión). No se calcula un puntaje único ponderado a propósito: mezclar
 * participación y alineamiento en un solo número requeriría una
 * ponderación arbitraria: se muestran ambas métricas por separado.
 */
export function indiceVotaciones(sesiones: VotacionSesion[], autoridadIds: string[]): IndiceVotacion[] {
	const totalSesiones = sesiones.length;
	return autoridadIds.map((autoridad_id) => {
		const conteo: Record<string, number> = {};
		let alineados = 0;
		let comparables = 0;

		for (const sesion of sesiones) {
			const voto = sesion.votos.find((v) => v.autoridad_id === autoridad_id);
			if (!voto) continue;
			conteo[voto.voto] = (conteo[voto.voto] ?? 0) + 1;

			const esFavorOContra = voto.voto === 'favor' || voto.voto === 'contra';
			if (esFavorOContra && (sesion.resultado === 'aprobado' || sesion.resultado === 'rechazado')) {
				comparables++;
				const alineado =
					(sesion.resultado === 'aprobado' && voto.voto === 'favor') ||
					(sesion.resultado === 'rechazado' && voto.voto === 'contra');
				if (alineado) alineados++;
			}
		}

		const votosReales = (conteo.favor ?? 0) + (conteo.contra ?? 0) + (conteo.abstencion ?? 0) + (conteo.pareo ?? 0);

		return {
			autoridad_id,
			...nombreYCargo(autoridad_id),
			favor: conteo.favor ?? 0,
			contra: conteo.contra ?? 0,
			abstencion: conteo.abstencion ?? 0,
			pareo: conteo.pareo ?? 0,
			ausente: conteo.ausente ?? 0,
			inhabilitado: conteo.inhabilitado ?? 0,
			dispensado: conteo.dispensado ?? 0,
			participacionPct: totalSesiones > 0 ? Math.round((votosReales / totalSesiones) * 1000) / 10 : 0,
			alineamientoPct: comparables > 0 ? Math.round((alineados / comparables) * 1000) / 10 : null,
		};
	});
}

export interface IndiceMociones {
	autoridad_id: string;
	nombre: string;
	cargo: string;
	total: number;
}

export function indiceMociones(autoridadIds: string[]): IndiceMociones[] {
	return autoridadIds.map((autoridad_id) => ({
		autoridad_id,
		...nombreYCargo(autoridad_id),
		total: mociones.filter((m) => m.autoridad_id === autoridad_id).length,
	}));
}

export interface IndiceAsistencia {
	autoridad_id: string;
	nombre: string;
	cargo: string;
	asistenciaPct: number | null;
	asistencias: number;
	sesionesComputables: number;
	ausenciasJustificadas: number;
	ausenciasSinJustificar: number;
}

/**
 * % de asistencia tal como lo calculan las fuentes oficiales (camara.cl
 * para diputados, senado.cl para senadores) — no lo recalculamos
 * nosotros. A diferencia del índice de votaciones, este dato viene ya
 * agregado de la fuente, no lo derivamos de sesiones individuales.
 */
export function indiceAsistencia(autoridadIds: string[]): IndiceAsistencia[] {
	return autoridadIds.map((autoridad_id) => {
		const resumen = asistenciaResumenDeAutoridad(autoridad_id);
		return {
			autoridad_id,
			...nombreYCargo(autoridad_id),
			// camara.cl a veces publica más asistencias que "sesiones
			// computables" (ej. Carolina Tello: 62/61) — no lo corregimos
			// nosotros porque no sabemos la causa real, pero un % sobre 100
			// no es válido por definición, así que se topa en 100.
			asistenciaPct:
				resumen && resumen.sesiones_computables > 0
					? Math.min(100, Math.round((resumen.asistencias / resumen.sesiones_computables) * 1000) / 10)
					: null,
			asistencias: resumen?.asistencias ?? 0,
			sesionesComputables: resumen?.sesiones_computables ?? 0,
			ausenciasJustificadas:
				(resumen?.ausencias_justif_no_afecta ?? 0) + (resumen?.ausencias_justif_si_afecta ?? 0),
			ausenciasSinJustificar: resumen?.ausencias_sin_justificar ?? 0,
		};
	});
}
