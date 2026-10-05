// Notificaciones push de Mailbox — cliente.
//
// ─────────────────────────────────────────────────────────────────────────────
// POR QUÉ ESTE MÓDULO ES MÁS LARGO QUE UN "requestPermission Y LISTO"
// ─────────────────────────────────────────────────────────────────────────────
// La mayoría del ecosistema de Mailbox va a ser iPhone, y en iOS el Web Push
// tiene tres condiciones que el navegador NO avisa: simplemente falla.
//
//   1. **iOS 16.4 o superior.** Antes de esa versión no hay Web Push en PWA.
//   2. **La PWA tiene que estar INSTALADA** en la pantalla de inicio. En una
//      pestaña de Safari, `requestPermission()` puede pedir permiso y después
//      `pushManager.subscribe()` revienta con NotSupportedError.
//   3. **`requestPermission()` solo funciona dentro de un gesto del usuario.**
//      Si se llama al cargar la página (que es lo "correcto" en escritorio),
//      iOS lo ignora en silencio y `permission` sigue en 'default'.
//
// Ninguna de las tres produce un error legible, y por eso este módulo no llama
// a la API: la ENVUELVE y devuelve un estado con el motivo, para que la vista
// pueda decirle al usuario qué hacer en vez de mostrar "no se pudo".
//
// Un detalle más: en iOS el permiso nunca llega a ser 'denied' — se queda en
// 'default' para siempre si el usuario no la acepta. Por eso acá se exige ver
// 'granted' explícitamente y nunca se infiere de que "no sea denied".
import { api, isNetworkError } from './api.js';

// Versión mínima de iOS con Web Push en PWA.
const IOS_MIN_MAYOR = 16;
const IOS_MIN_MENOR = 4;

// ── Detección de plataforma ───────────────────────────────────────────────────

/** iPhone/iPad, incluyendo iPadOS 13+ que se reporta como "Macintosh". */
export function esIOS() {
	if (typeof navigator === 'undefined') return false;
	const ua = navigator.userAgent || '';
	if (/iP(hone|ad|od)/.test(ua)) return true;
	// iPadOS 13+ se hace pasar por Mac: tiene touchpoints y dice Macintosh.
	return /Macintosh/.test(ua) && (navigator.maxTouchPoints || 0) > 1;
}

/** Versión de iOS como {mayor, menor}, o null si no es iOS. */
export function versionIOS() {
	if (!esIOS()) return null;
	const ua = navigator.userAgent || '';
	// "CPU iPhone OS 17_5_1 like Mac OS X" o "CPU OS 17_5 like Mac OS X"
	const m = ua.match(/OS (\d+)[._](\d+)(?:[._](\d+))?/);
	if (!m) return null;
	return { mayor: Number(m[1]), menor: Number(m[2]), parche: Number(m[3] || 0) };
}

function iosCumpleElMinimo() {
	const v = versionIOS();
	if (!v) return true;                 // no es iOS: no aplica este filtro
	return v.mayor > IOS_MIN_MAYOR
		|| (v.mayor === IOS_MIN_MAYOR && v.menor >= IOS_MIN_MENOR);
}

/** ¿La app está corriendo como PWA instalada (no en una pestaña de navegador)? */
export function estaInstalada() {
	if (typeof window === 'undefined') return false;
	if (window.navigator.standalone === true) return true;
	// iOS 16.4+ y todos los demás navegadores con display-mode.
	try {
		return window.matchMedia('(display-mode: standalone)').matches;
	} catch {
		return false;
	}
}

// ── Estado ────────────────────────────────────────────────────────────────────

/**
 * Estado completo de las notificaciones, para que la vista decida qué mostrar.
 * `listo` = se puede pedir el permiso y va a funcionar.
 */
export function soporte() {
	const base = {
		navegador: !!(typeof window !== 'undefined'
			&& 'serviceWorker' in navigator
			&& 'PushManager' in window
			&& 'Notification' in window),
		ios: esIOS(),
		instalada: estaInstalada(),
		versionIOS: versionIOS(),
		permiso: (typeof Notification !== 'undefined') ? Notification.permission : 'unsupported',
		suscrito: false,
		listo: false,
		motivo: ''
	};

	if (!base.navegador) {
		base.motivo = 'Este navegador no soporta notificaciones push.';
		return base;
	}
	if (base.ios && !iosCumpleElMinimo()) {
		base.motivo = `Las notificaciones en iPhone necesitan iOS ${IOS_MIN_MAYOR}.${IOS_MIN_MENOR} o superior.`;
		return base;
	}
	// En iOS la PWA tiene que estar en la pantalla de inicio. En escritorio y
	// Android no hace falta, así que el aviso solo se da en iOS.
	if (base.ios && !base.instalada) {
		base.motivo = 'En iPhone hay que instalar la app en la pantalla de inicio.';
		return base;
	}
	base.listo = true;
	return base;
}

/** Suscripción push de este dispositivo, o null. */
export async function suscripcionActual() {
	if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return null;
	try {
		const reg = await navigator.serviceWorker.ready;
		return await reg.pushManager.getSubscription();
	} catch {
		return null;
	}
}

/** Estado + suscripción en una llamada, que es lo que la vista consume. */
export async function estado() {
	const s = soporte();
	const sub = s.listo ? await suscripcionActual() : null;
	return { ...s, suscrito: !!sub, sub };
}

// ── Activación ────────────────────────────────────────────────────────────────

function urlBase64ToUint8Array(base64String) {
	const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
	const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
	const raw = window.atob(base64);
	const out = new Uint8Array(raw.length);
	for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
	return out;
}

/**
 * Pide permiso y registra la suscripción.
 *
 **OBLIGATORIO: llamar desde un manejador de click**, no al montar la vista.
 * En iOS es la diferencia entre que aparezca el diálogo o no.
 *
 * Devuelve { ok, motivo } — nunca lanza, para que el botón no quede colgado.
 */
export async function activar() {
	const s = soporte();
	if (!s.listo) return { ok: false, motivo: s.motivo };

	try {
		const permiso = await Notification.requestPermission();
		if (permiso !== 'granted') {
			// En iOS 'default' significa "no habilitado para este sitio"; no hay
			// forma de saber si el usuario lo va a permitir después. Se dice la
			// verdad en vez de fingir que se guardó.
			return {
				ok: false,
				motivo: permiso === 'denied'
					? 'Las notificaciones están bloqueadas para este sitio. Actívalas en los ajustes del navegador.'
					: 'No se concedió el permiso de notificaciones.'
			};
		}

		// La clave pública VAPID la genera el backend una vez y la guarda en
		// HUB_Config. Se pide acá para no tenerla hardcodeada en el bundle.
		const { publicKey } = await api.get('/push/vapid-public-key');

		const reg = await navigator.serviceWorker.register('/sw.js');
		await navigator.serviceWorker.ready;

		let sub = await reg.pushManager.getSubscription();
		if (!sub) {
			sub = await reg.pushManager.subscribe({
				userVisibleOnly: true,
				applicationServerKey: urlBase64ToUint8Array(publicKey)
			});
		}

		const j = sub.toJSON();
		await api.post('/push/subscribe', {
			endpoint: j.endpoint,
			keys: j.keys
		});

		await refrescarContador();
		return { ok: true, motivo: '' };
	} catch (e) {
		if (isNetworkError(e)) return { ok: false, motivo: 'Sin conexión.' };
		// NotSupportedError en iOS casi siempre significa "no está instalada".
		if (e && e.name === 'NotSupportedError' && esIOS()) {
			return { ok: false, motivo: 'En iPhone hay que instalar la app en la pantalla de inicio.' };
		}
		return { ok: false, motivo: e?.message || 'No se pudieron activar las notificaciones.' };
	}
}

/**
 * Reenvía la suscripción al backend si ya existe.
 *
 * Para qué: la suscripción push pertenece al service worker (estable), pero su
 * ASIGNACIÓN es a un usuario. Si el usuario cierra sesión y entra con otra
 * cuenta en el mismo teléfono, el endpoint quedaría apuntando al usuario
 * anterior. Llamar a esto al iniciar sesión corrige la asignación sin volver a
 * pedir el permiso.
 */
export async function revincular() {
	try {
		const sub = await suscripcionActual();
		if (!sub) return false;
		const j = sub.toJSON();
		if (!j.endpoint) return false;
		await api.post('/push/subscribe', { endpoint: j.endpoint, keys: j.keys });
		return true;
	} catch {
		// Silencioso a propósito: revincular es una mejora silenciosa, si falla
		// no hay que interrumpir el inicio de sesión.
		return false;
	}
}

/** Cancela la suscripción en ESTE dispositivo y la quita del servidor. */
export async function desactivar() {
	try {
		const sub = await suscripcionActual();
		if (sub) {
			await api.post('/push/unsubscribe', { endpoint: sub.endpoint }).catch(() => {});
			await sub.unsubscribe();
		}
		await limpiarContador();
		return { ok: true, motivo: '' };
	} catch (e) {
		if (isNetworkError(e)) return { ok: false, motivo: 'Sin conexión.' };
		return { ok: false, motivo: e?.message || 'No se pudieron desactivar.' };
	}
}

// ── Badge ─────────────────────────────────────────────────────────────────────

/**
 * Pinta el número de no leídos en el ícono de la app.
 * Solo funciona en PWA instalada (en iOS, desde 16.4). En el resto no molesta:
 * si la API no existe, se ignora en silencio.
 */
export async function ponerContador(n) {
	try {
		if (!('serviceWorker' in navigator)) return;
		const reg = await navigator.serviceWorker.ready;
		if (typeof reg.setAppBadge === 'function') {
			if (n > 0) await reg.setAppBadge(n);
			else await reg.clearAppBadge();
		}
	} catch {
		/* sin badge, sin drama */
	}
}

export async function refrescarContador() {
	try {
		const { noLeidos } = await api.get('/push/contador');
		await ponerContador(noLeidos || 0);
		return noLeidos || 0;
	} catch {
		return 0;
	}
}

async function limpiarContador() {
	try {
		if (!('serviceWorker' in navigator)) return;
		const reg = await navigator.serviceWorker.ready;
		if (typeof reg.clearAppBadge === 'function') await reg.clearAppBadge();
	} catch {
		/* nada */
	}
}