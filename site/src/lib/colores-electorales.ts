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
