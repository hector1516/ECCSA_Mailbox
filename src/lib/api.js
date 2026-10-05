// Helper de API de Mailbox.
//
// Diferencias con el de Admon, y por qué:
//
// - **Sin caché offline.** El api.js de Admon envuelve cada GET en un
//   cachePut/cacheGet de IndexedDB, que sirve para un módulo que se edita sin
//   conexión (cotizaciones). Mailbox es de solo lectura y su contenido pesado
//   (los adjuntos) se transmite al dispositivo, no se guarda: no hay nada que
//  vale la pena cachear. Cuando entre el modo offline se agrega acá, no antes.
// - **`NetworkError` en vez de un simple throw.** Sigue siendo útil aunque no
//   haya caché: distingue "no hay red" de "el servidor dijo que no", que son
//   dos mensajes muy distintos para el usuario (y para el banner del shell).
// - **fetch directo para descargas.** `descargar()` existe porque la descarga
//   de adjuntos NO es un JSON: es un streaming de bytes con su propio
//   Content-Type y Content-Disposition. Pasarlo por request() lo convertiría
//   en base64 y mataría el streaming.
import { auth } from './stores/auth.js';
import { navigate } from './router.js';

const BASE = '/api';

export class NetworkError extends Error {
	constructor() {
		super('Sin conexión');
		this.name = 'NetworkError';
		this.code = 'NETWORK';
	}
}

export function isNetworkError(e) {
	return !!e && (e.code === 'NETWORK' || e.name === 'NetworkError');
}

async function request(path, options = {}) {
	const headers = { ...(options.headers || {}) };
	const token = localStorage.getItem('mailbox_token');
	if (token) headers['Authorization'] = `Bearer ${token}`;

	// Nunca forzar Content-Type con FormData: el navegador debe poner el
	// multipart/form-data con SU boundary. Si le ponemos JSON, FastAPI responde
	// 422 con size=0. (La lección del service worker, ver AGENTS.md §Trampas.)
	if (!(options.body instanceof FormData)) {
		headers['Content-Type'] = 'application/json';
	} else {
		delete headers['Content-Type'];
		delete headers['content-type'];
	}

	let res;
	try {
		res = await fetch(`${BASE}${path}`, { ...options, headers });
	} catch {
		throw new NetworkError();
	}

	if (res.status === 401) {
		auth.logout();
		navigate('/login', { replace: true });
		throw new Error('Sesión expirada');
	}
	if (!res.ok) {
		const err = await res.json().catch(() => ({}));
		let detail = err.detail || err.message || 'Error del servidor';
		// FastAPI 422 devuelve detail como array de objetos {loc, msg, type}
		if (Array.isArray(detail)) {
			detail = detail.map((d) => d?.msg || JSON.stringify(d)).join('; ');
		}
		throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
	}
	return res.json();
}

/**
 * Descarga un adjunto (o cualquier binario) sin pasar por request().
 *
 * Devuelve el Response crudo para que el que llama decida qué hacer:
 * normalmente `resp.blob()` + `URL.createObjectURL` + un `<a download>`, que
 * es lo que hace que el archivo aterrice en el dispositivo donde está abierta
 * la PWA (el iPhone, la tablet, la PC) y no en el servidor.
 *
 * OJO con el 401: acá NO se llama a auth.logout() porque una descarga no
 * debería cerrar la sesión; solo propagamos el error.
 */
export async function descargar(path) {
	const headers = {};
	const token = localStorage.getItem('mailbox_token');
	if (token) headers['Authorization'] = `Bearer ${token}`;

	let res;
	try {
		res = await fetch(`${BASE}${path}`, { headers });
	} catch {
		throw new NetworkError();
	}
	if (!res.ok) {
		let detalle = 'No se pudo descargar';
		try {
			const err = await res.json();
			detalle = typeof err.detail === 'string' ? err.detail : detalle;
		} catch {
			/* respuesta sin cuerpo JSON (p. ej. HTML de error del proxy) */
		}
		throw new Error(detalle);
	}
	return res;
}

/**
 * El cuerpo de un POST/PUT, listo para fetch.
 *
 * Un FormData se pasa TAL CUAL, sin JSON.stringify. Esto no es un detalle: si se
 * serializa, `JSON.stringify(new FormData())` es la cadena `"{}"`, el `body` deja
 * de ser un FormData, `request()` cree que es JSON y pone
 * `Content-Type: application/json`, y FastAPI responde 422 porque no recibe el
 * archivo. El síntoma es "subir imagen no funciona" sin ningún error visible.
 *
 * Cualquier otro objeto va como JSON, que es lo que espera el resto de la app.
 */
function cuerpo(body) {
	return body instanceof FormData ? body : JSON.stringify(body);
}

export const api = {
	get: (path) => request(path),
	post: (path, body) => request(path, { method: 'POST', body: cuerpo(body) }),
	put: (path, body) => request(path, { method: 'PUT', body: cuerpo(body) }),
	delete: (path) => request(path, { method: 'DELETE' }),
	descargar
};