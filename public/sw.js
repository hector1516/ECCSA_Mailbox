// ═══════════════════════════════════════════════════════════════════════════
// Mailbox · service worker
//
// REGLA DURA, la más importante del archivo:
//   SOLO INTERCEPTAR GET.
//
// Nunca respondWith(fetch(request)) sobre POST/PUT/PATCH con FormData: el
// service worker pierde el body, el backend recibe size=0 y FastAPI responde
// 422. Ya se rompió dos veces en el ecosistema por esto (docs/TROUBLESHOOTING
// de Field, §1). El `if (event.request.method !== 'GET') return;` de más abajo
// no es opcional ni una optimización: es la razón de que los adjuntos y los
// envíos funcionen.
//
// SEGUNDA REGLA: este archivo no lee del navegador nada del shell. Los
// selectores de estilos viven en el CSS del shell (body.css); acá solo hay
// lógica.
// ═══════════════════════════════════════════════════════════════════════════

const CACHE = 'mailbox-v0.1.0';
const APP_SHELL = '/index.html';

// Se pre-cachea el armazón para que la app abra sin red y muestre el splash en
// vez de la pantalla de error del navegador. El `catch` individual es a
// propósito: que falte un ícono no puede impedir instalar el SW.
const PRECACHE = [
	'/',
	'/index.html',
	'/manifest.webmanifest',
	'/mailbox_logo.png',
	'/mailbox_marca.png',
	'/engrane.png',
	'/icons/icon-192x192.png',
	'/icons/icon-512x512.png',
	'/icons/icon-512-maskable.png',
	'/apple-touch-icon.png'
];

// ── Instalación / activación ─────────────────────────────────────────────────
self.addEventListener('install', (event) => {
	event.waitUntil((async () => {
		const cache = await caches.open(CACHE);
		await Promise.all(
			PRECACHE.map((url) => cache.add(url).catch(() => {}))
		);
		// Sin esto el nuevo SW espera a que se cierren todas las pestañas.
		await self.skipWaiting();
	})());
});

self.addEventListener('activate', (event) => {
	event.waitUntil((async () => {
		const claves = await caches.keys();
		await Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
		await self.clients.claim();
		// Avisa a las pestañas abiertas para que recarguen y no se queden con
		// el bundle viejo (el hash del archivo cambia en cada build).
		const tabs = await self.clients.matchAll();
		tabs.forEach((c) => c.postMessage({ type: 'FORCE_RELOAD' }));
	})());
});

// ── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
	const url = new URL(event.request.url);

	// Solo same-origin: los recursos externos (fuentes, etc.) no se tocan.
	if (url.origin !== self.location.origin) return;

	// API y docs: SIEMPRE en red, nunca cacheadas. Un correo listado desde
	// caché puede ser un borrador que el usuario ya borró.
	if (url.pathname.startsWith('/api') || url.pathname.startsWith('/docs')) return;

	// ── LA REGLA DURA ──────────────────────────────────────────────────────
	// Cualquier cosa que no sea GET se deja pasar de largo. Sin respondWith,
	// el navegador hace la petición directamente y el body intacto.
	if (event.request.method !== 'GET') return;
	// ──────────────────────────────────────────────────────────────────────

	// Navegaciones: red primero (el index.html lleva no-store), caché de
	// respaldo. Sin este camino, sin red el usuario ve la pantalla de error
	// del navegador en vez de la app.
	if (event.request.mode === 'navigate') {
		event.respondWith((async () => {
			try {
				const res = await fetch(event.request);
				// Solo se guarda si la respuesta fue buena: cachear un 403 o un
				// 404 envenena el armazón y después no se recovers sin borrar
				// la caché a mano.
				if (res && res.ok) {
					const cache = await caches.open(CACHE);
					await cache.put(APP_SHELL, res.clone());
				}
				return res;
			} catch {
				return (await caches.match(APP_SHELL)) || Response.error();
			}
		})());
		return;
	}

	// Estáticos con hash en el nombre (/assets/index-XXXX.js): cache-first con
	// revalidación al fondo. El hash cambia cuando el contenido cambia, así que
	// una entrada vieja nunca se sirve por error.
	event.respondWith((async () => {
		const cache = await caches.open(CACHE);
		const cached = await cache.match(event.request);
		const red = fetch(event.request).then((res) => {
			if (res && res.ok) cache.put(event.request, res.clone());
			return res;
		}).catch(() => null);
		return cached || (await red) || Response.error();
	})());
});

// ── Notificaciones push ──────────────────────────────────────────────────────
// iOS exige la PWA instalada y iOS 16.4+ para que esto se dispare; el cliente
// (src/lib/push.js) es quien verifica esas condiciones antes de pedir permiso.
function _esIOS() {
	const ua = navigator.userAgent || '';
	if (/iP(hone|ad|od)/.test(ua)) return true;
	return /Macintosh/.test(ua) && (navigator.maxTouchPoints || 0) > 1;
}

self.addEventListener('push', (event) => {
	// Con userVisibleOnly:true el servidor SIEMPRE manda body. Si no llega, no
	// hay nada que mostrar y mostrar un aviso vacío sería peor que nada.
	if (!event.data) return;

	let payload = {};
	try {
		payload = event.data.json();
	} catch {
		payload = { title: 'Mailbox', body: event.data.text() };
	}

	const title = payload.title || 'Mailbox';

	const options = {
		body: payload.body || '',
		data: { url: payload.url || '/', idMensaje: payload.id || null },
		// El tag agrupa: si llegan 3 correos de la misma cuenta, el segundo
		// reemplaza al primero en lugar de apilar tres avisos. En iPhone la
		// pila de notificaciones se llena rápido y tapar la pantalla es peor
		// que resumir.
		tag: payload.tag || 'mailbox',
		renotify: !!payload.tag,
		silent: !!payload.silent,
		// iOS NO usa imágenes remotas: el ícono tiene que estar empaquetado
		// con la app, así que se referencia uno local siempre.
		icon: '/icons/icon-192x192.png',
		// El badge tiene semántica distinta por plataforma y mandarlo igual en
		// los dos casos se ve mal en alguno:
		//   · iOS      → `badge` es un NÚMERO que se pinta en el ícono.
		//   · Android  → `badge` es la URL de una IMAGEN pequeña.
		// Por eso el servidor manda `badge_count` y acá se decide.
		badge: _esIOS() ? String(payload.badge_count || 0) : '/icons/icon-96x96.png'
	};

	// En iOS el ícono grande de la notificación (Aperture) sale del bundle, no
	// de la app: no se controla desde acá y no se intenta.
	if (payload.vibrate && navigator.vibrate) {
		options.vibrate = payload.vibrate;
	}

	event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();

	const url = event.notification.data?.url || '/';
	const idMensaje = event.notification.data?.idMensaje || null;

	event.waitUntil((async () => {
		// Primero se intenta despertar una pestaña que YA esté abierta: en iOS
		// abrir una ventana nueva desde una notificación deja la PWA en un
		// estado raro (a veces en blanco), así que enfocar la existente es
		// siempre la opción preferida.
		const tabs = await self.clients.matchAll({
			type: 'window',
			includeUncontrolled: true
		});

		for (const tab of tabs) {
			if (tab.url.startsWith(self.location.origin)) {
				await tab.focus();
				// Se le pasa la ruta para que la app abra el mensaje. Se usa
				// postMessage en vez de tab.navigate() porque la ruta puede
				// llevar query (?msg=123) y el router de la app la lee del
				// history, no de un evento.
				tab.postMessage({ type: 'ABRIR_MENSAJE', id: idMensaje, url });
				return;
			}
		}

		// No había ninguna pestaña: se abre la PWA.
		await self.clients.openWindow(url);
	})());
});

self.addEventListener('notificationclose', (event) => {
	// Gancho para métricas futuras. No se manda nada a la red a propósito:
	// hacerlo desde el SW en iOS es poco confiable y no vale el riesgo de
	// despertar el proceso por un analytics.
});

// Mensaje de la app al SW. Se usa para limpiar el badge cuando el usuario lee
// todo, porque el ícono del iPhone lo pinta el SO y no hay otra forma.
self.addEventListener('message', (event) => {
	const d = event.data || {};
	if (d.type === 'SKIP_WAITING') {
		self.skipWaiting();
		return;
	}
	if (d.type === 'FORCE_RELOAD') {
		return; // lo escucha la página (index.html), no el SW
	}
	if (d.type === 'LIMPIAR_BADGE') {
		event.waitUntil((async () => {
			if (typeof self.registration.clearAppBadge === 'function') {
				await self.registration.clearAppBadge();
			}
		})());
	}
});