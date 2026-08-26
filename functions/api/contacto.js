// Cloudflare Pages Function — recibe el formulario de /contacto/ sin salir
// del dominio ni depender de un servicio de formularios de terceros
// (Formspree bloqueaba el envío por AJAX en el plan gratuito salvo
// reCAPTCHA/key especial, y redirigía a una página con su propia marca).
//
// Flujo: valida el token de Cloudflare Turnstile contra la API oficial de
// Cloudflare, y si es válido, envía el correo vía la API de Resend.
//
// Variables de entorno requeridas (Cloudflare Pages → Settings →
// Environment variables, como "Secret" — nunca en el código):
//   RESEND_API_KEY      — resend.com → API Keys
//   TURNSTILE_SECRET_KEY — dash.cloudflare.com → Turnstile → el widget → Secret Key

const DESTINATARIO = 'contacto@oprcoquimbo.cl';
// resend.com exige verificar el dominio propio para poder usarlo como
// remitente — hasta que oprcoquimbo.cl esté verificado en Resend, se usa
// su dirección de pruebas. Una vez verificado, cambiar esto a algo como
// "OPRC <contacto@oprcoquimbo.cl>".
const REMITENTE = 'OPRC <onboarding@resend.dev>';

function escaparHtml(texto) {
	return texto
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;');
}

export async function onRequestPost({ request, env }) {
	try {
		const datos = await request.formData();
		const nombre = (datos.get('nombre') || '').toString().trim();
		const email = (datos.get('email') || '').toString().trim();
		const asunto = (datos.get('asunto') || '').toString().trim();
		const mensaje = (datos.get('mensaje') || '').toString().trim();
		const tokenTurnstile = (datos.get('cf-turnstile-response') || '').toString();

		if (!nombre || !email || !asunto || !mensaje) {
			return Response.json({ ok: false, error: 'Faltan campos requeridos.' }, { status: 400 });
		}
		if (!tokenTurnstile) {
			return Response.json({ ok: false, error: 'Falta la verificación anti-spam.' }, { status: 400 });
		}

		const verificacion = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				secret: env.TURNSTILE_SECRET_KEY,
				response: tokenTurnstile,
				remoteip: request.headers.get('CF-Connecting-IP') || undefined,
			}),
		});
		const resultadoVerificacion = await verificacion.json();
		if (!resultadoVerificacion.success) {
			return Response.json({ ok: false, error: 'No se pudo verificar que sos una persona.' }, { status: 400 });
		}

		const resp = await fetch('https://api.resend.com/emails', {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${env.RESEND_API_KEY}`,
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				from: REMITENTE,
				to: DESTINATARIO,
				reply_to: email,
				subject: `[Contacto OPRC] ${asunto}`,
				html: `
					<p><strong>Nombre:</strong> ${escaparHtml(nombre)}</p>
					<p><strong>Correo:</strong> ${escaparHtml(email)}</p>
					<p><strong>Asunto:</strong> ${escaparHtml(asunto)}</p>
					<p><strong>Mensaje:</strong></p>
					<p>${escaparHtml(mensaje).replace(/\n/g, '<br>')}</p>
				`,
			}),
		});

		if (!resp.ok) {
			const detalle = await resp.text();
			return Response.json({ ok: false, error: `Resend: ${detalle}` }, { status: 502 });
		}

		return Response.json({ ok: true });
	} catch (err) {
		return Response.json({ ok: false, error: String(err) }, { status: 500 });
	}
}
