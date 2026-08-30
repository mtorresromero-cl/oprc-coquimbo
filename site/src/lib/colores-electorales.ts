/**
 * Colores por partido para las barras de candidatos, reutilizado por
 * /herramientas/electoral/resultados/ y /herramientas/electoral/comuna/[id]/.
 *
 * Los nombres reales que guarda SERVEL son muy heterogéneos (169 valores
 * distintos entre nombres completos, siglas, "INDEPENDIENTE X", listas y
 * escaños étnicos) — se mapean a mano los ~25 partidos reconocibles más
 * frecuentes y el resto recibe un color generado por hash de su propio
 * nombre, para que sigan siendo distinguibles entre sí en vez de un gris
 * plano.
 */

const COLOR_PARTIDO: Record<string, string> = {
	INDEPENDIENTE: '#78909c', INDEPENDIENTES: '#78909c',
	'RENOVACION NACIONAL': '#1565c0', RN: '#1565c0',
	'UNION DEMOCRATA INDEPENDIENTE': '#0d47a1', UDI: '#0d47a1',
	'PARTIDO SOCIALISTA DE CHILE': '#e91e63', PS: '#e91e63',
	'PARTIDO POR LA DEMOCRACIA': '#2196f3', PPD: '#2196f3',
	'PARTIDO DEMOCRATA CRISTIANO': '#4caf50', PDC: '#4caf50', DC: '#4caf50',
	'PARTIDO COMUNISTA DE CHILE': '#c62828', PC: '#c62828', PCCH: '#c62828',
	'FRENTE AMPLIO': '#e53935',
	'PARTIDO RADICAL DE CHILE': '#7b1fa2', PR: '#7b1fa2',
	'PARTIDO RADICAL SOCIALDEMOCRATA': '#7b1fa2', PRSD: '#7b1fa2',
	'PARTIDO REPUBLICANO DE CHILE': '#ff6f00',
	'REVOLUCION DEMOCRATICA': '#d32f2f',
	'CONVERGENCIA SOCIAL': '#b71c1c',
	'EVOLUCION POLITICA': '#42a5f5',
	'PARTIDO ECOLOGISTA VERDE': '#2e7d32',
	'PARTIDO HUMANISTA': '#66bb6a', PH: '#66bb6a',
	'PARTIDO DE LA GENTE': '#ff9800',
	COMUNES: '#8d6e63',
	AMPLITUD: '#26a69a',
	'FEDERACION REGIONALISTA VERDE SOCIAL': '#00897b',
	IGUALDAD: '#5d4037',
	'PARTIDO PROGRESISTA': '#f4511e', 'PARTIDO PROGRESISTA DE CHILE': '#f4511e',
};

export function hashColor(str: string): string {
	let hash = 0;
	for (let i = 0; i < str.length; i++) hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
	return `hsl(${hash % 360} 55% 42%)`;
}

export function colorPartido(partido: string | null): string {
	if (!partido) return '#78909c';
	const key = partido.trim().toUpperCase();
	return COLOR_PARTIDO[key] || hashColor(key);
}

// Los plebiscitos y otras "opciones" (no candidatos) se colorean por el
// texto de la opción misma, no por partido.
const COLOR_OPCION: Record<string, string> = {
	APRUEBO: '#1565c0',
	'A FAVOR': '#1565c0',
	'CONVENCION CONSTITUCIONAL': '#1565c0',
	RECHAZO: '#c62828',
	'EN CONTRA': '#c62828',
	'CONVENCION MIXTA CONSTITUCIONAL': '#c62828',
};

export function colorOpcion(candidato: string): string {
	return COLOR_OPCION[candidato.trim().toUpperCase()] || hashColor(candidato);
}

export function tituloCase(s: string): string {
	return s
		.toLowerCase()
		.split(' ')
		.map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
		.join(' ');
}

// Siglas cortas (DC, RN, UDI, PPD...) se ven mal en título ("Dc", "Udi") —
// se dejan en mayúsculas tal como vienen.
export function formatoPartido(s: string | null): string | null {
	if (!s) return s;
	return !s.includes(' ') && s.length <= 5 ? s.toUpperCase() : tituloCase(s);
}

// Para agrupar "quién ha ganado más veces" a través de décadas hace falta
// tratar "PS" y "PARTIDO SOCIALISTA DE CHILE" como el mismo partido — sin
// esto, un partido que usó ambas formas en años distintos aparecería
// dividido en dos y subcontado. Solo cubre los mismos ~25 partidos
// reconocibles del mapa de colores; el resto usa formatoPartido() tal cual,
// que para listas/independientes menores ya es su propio grupo razonable.
const NOMBRE_CANONICO: Record<string, string> = {
	RN: 'Renovación Nacional', 'RENOVACION NACIONAL': 'Renovación Nacional',
	UDI: 'UDI', 'UNION DEMOCRATA INDEPENDIENTE': 'UDI',
	PS: 'Partido Socialista', 'PARTIDO SOCIALISTA DE CHILE': 'Partido Socialista',
	PPD: 'PPD', 'PARTIDO POR LA DEMOCRACIA': 'PPD',
	PDC: 'Democracia Cristiana', DC: 'Democracia Cristiana', 'PARTIDO DEMOCRATA CRISTIANO': 'Democracia Cristiana',
	PC: 'Partido Comunista', PCCH: 'Partido Comunista', 'PARTIDO COMUNISTA DE CHILE': 'Partido Comunista',
	'FRENTE AMPLIO': 'Frente Amplio',
	PR: 'Partido Radical', PRSD: 'Partido Radical',
	'PARTIDO RADICAL DE CHILE': 'Partido Radical', 'PARTIDO RADICAL SOCIALDEMOCRATA': 'Partido Radical',
	'PARTIDO REPUBLICANO DE CHILE': 'Partido Republicano',
	'REVOLUCION DEMOCRATICA': 'Revolución Democrática',
	'CONVERGENCIA SOCIAL': 'Convergencia Social',
	'EVOLUCION POLITICA': 'Evolución Política',
	'PARTIDO ECOLOGISTA VERDE': 'Partido Ecologista Verde',
	PH: 'Partido Humanista', 'PARTIDO HUMANISTA': 'Partido Humanista',
	'PARTIDO DE LA GENTE': 'Partido de la Gente',
	COMUNES: 'Comunes',
	AMPLITUD: 'Amplitud',
	'FEDERACION REGIONALISTA VERDE SOCIAL': 'Federación Regionalista Verde Social',
	IGUALDAD: 'Igualdad',
	'PARTIDO PROGRESISTA': 'Partido Progresista', 'PARTIDO PROGRESISTA DE CHILE': 'Partido Progresista',
};

export function nombreCanonicoPartido(s: string | null): string {
	if (!s) return 'Independiente';
	return NOMBRE_CANONICO[s.trim().toUpperCase()] ?? (formatoPartido(s) as string);
}
