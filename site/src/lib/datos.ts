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

import autoridadesRaw from '../../../data/processed/autoridades.json';
import comunasRaw from '../../../data/processed/comunas.json';

export const autoridades: Autoridad[] = autoridadesRaw as Autoridad[];
export const comunas: Comuna[] = comunasRaw as Comuna[];

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
