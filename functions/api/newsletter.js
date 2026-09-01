// Cloudflare Pages Function — recibe el formulario de suscripción al
// newsletter y agrega el correo como suscriptor en Mailrelay.
//
// Variable de entorno requerida (Cloudflare Pages → Settings →
// Environment variables, como "Secret" — nunca en el código):
//   MAILRELAY_API_KEY — panel de Mailrelay → Configuración → Claves API

const MAILRELAY_DOMINIO = 'oprcoquimbo1.ipzmarketing.com';
const MAILRELAY_GRUPO_NEWSLETTER = 1;

function emailValido(email) {
	return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export async function onRequestPost({ request, env }) {
	try {
		const datos = await request.formData();
		const email = (datos.get('email') || '').toString().trim();
		// honeypot: campo oculto en el formulario que un humano nunca llena
		const trampa = (datos.get('sitio_web') || '').toString().trim();

		if (trampa) {
			// no delatar al bot — responder como si hubiera funcionado
			return Response.json({ ok: true });
		}
		if (!email || !emailValido(email)) {
			return Response.json({ ok: false, error: 'Correo inválido.' }, { status: 400 });
		}

		const resp = await fetch(`https://${MAILRELAY_DOMINIO}/api/v1/subscribers`, {
			method: 'POST',
			headers: {
				'X-AUTH-TOKEN': env.MAILRELAY_API_KEY,
				Accept: 'application/json',
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				email,
				status: 'active',
				group_ids: [MAILRELAY_GRUPO_NEWSLETTER],
			}),
		});

		if (!resp.ok) {
			const detalle = await resp.text();
			// un correo ya suscrito no debería verse como error para quien lo envía
			if (resp.status === 422 && /already|existe|duplicad/i.test(detalle)) {
				return Response.json({ ok: true });
			}
			return Response.json({ ok: false, error: `Mailrelay: ${detalle}` }, { status: 502 });
		}

		return Response.json({ ok: true });
	} catch (err) {
		return Response.json({ ok: false, error: String(err) }, { status: 500 });
	}
}
