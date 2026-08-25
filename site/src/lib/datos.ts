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

import autoridadesRaw from '../../../data/processed/autoridades.json';
import comunasRaw from '../../../data/processed/comunas.json';
import votacionesRaw from '../../../data/processed/votaciones.json';
import mocionesRaw from '../../../data/processed/mociones.json';
import presupuestoRaw from '../../../data/processed/presupuesto-municipal.json';
import personalRaw from '../../../data/processed/personal-municipal.json';
import remuneracionAutoridadRaw from '../../../data/processed/remuneracion-autoridad.json';
import declaracionesPatrimonioRaw from '../../../data/processed/declaracion-patrimonio.json';

export const autoridades: Autoridad[] = autoridadesRaw as Autoridad[];
export const comunas: Comuna[] = comunasRaw as Comuna[];
export const votaciones: VotacionSesion[] = votacionesRaw as VotacionSesion[];
export const mociones: Mocion[] = mocionesRaw as Mocion[];
export const presupuesto: PresupuestoItem[] = presupuestoRaw as PresupuestoItem[];
export const personal: PersonalItem[] = personalRaw as PersonalItem[];
export const remuneracionAutoridad: RemuneracionAutoridad[] = remuneracionAutoridadRaw as RemuneracionAutoridad[];
export const declaracionesPatrimonio: DeclaracionPatrimonio[] =
	declaracionesPatrimonioRaw as DeclaracionPatrimonio[];

export function presupuestoDeComuna(comunaId: string) {
	return presupuesto.filter((p) => p.comuna_id === comunaId);
}

export function personalDeComuna(comunaId: string) {
	return personal.filter((p) => p.comuna_id === comunaId);
}

export function remuneracionAutoridadDeComuna(comunaId: string) {
	return remuneracionAutoridad.filter((r) => r.comuna_id === comunaId);
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

export const VOTO_LABEL: Record<string, string> = {
	favor: 'A favor',
	contra: 'En contra',
	abstencion: 'Abstención',
	pareo: 'Pareo',
	ausente: 'Ausente',
};

export function votacionesDeAutoridad(autoridadId: string) {
	return votaciones
		.map((v) => ({ sesion: v, voto: v.votos.find((x) => x.autoridad_id === autoridadId) }))
		.filter((x) => x.voto);
}

export const CARGOS = ['alcalde', 'concejal', 'core', 'diputado', 'senador', 'gobernador'] as const;

export const CARGO_LABEL: Record<string, string> = {
	alcalde: 'Alcalde/sa',
	concejal: 'Concejal/a',
	core: 'Consejero/a Regional',
	diputado: 'Diputado/a',
	senador: 'Senador/a',
	gobernador: 'Gobernador/a Regional',
};

export function nombreComuna(comunaId: string | null): string | null {
	if (!comunaId) return null;
	return comunas.find((c) => c.id === comunaId)?.nombre ?? comunaId;
}
