import { writable } from 'svelte/store';

// Micro-router history-mode (sin dependencias, nativo Svelte 5).
// Reemplaza a svelte-routing, cuyo prop `component={...}` invoca los
// componentes-función de Svelte 5 sin argumentos y rompe el render.
export const path = writable(
	typeof window !== 'undefined' ? window.location.pathname : '/'
);

export function navigate(to, { replace = false } = {}) {
	if (typeof window === 'undefined') return;
	// El store guarda la RUTA, no la URL completa. Sin este split, basta con
	// navegar a `/redactar?cuenta=1` para que `$path` valga
	// `/redactar?cuenta=1`, que NO es igual a `/redactar`, y el `{#if $path ===
	// '/redactar'}` de App.svelte no entre: la pantalla cae al `{:else}` final,
	// que es el Home.
	//
	// Pasó: los botones Responder, Responder a todos y Reenviar aterrizaban en
	// el menú principal. No era un problema de las reglas de reenvío: era que
	// `navigate()` metía la query en la ruta y la comparación del router no
	// podía dar nunca.
	//
	// Los query params siguen disponibles donde hacen falta: se leen de
	// `window.location.search`, no del store.
	const ruta = String(to).split('?')[0].split('#')[0];
	if (replace) history.replaceState({}, '', to);
	else history.pushState({}, '', to);
	path.set(ruta);
	window.scrollTo(0, 0);
}

if (typeof window !== 'undefined') {
	window.addEventListener('popstate', () => path.set(window.location.pathname));
	// Interceptar clicks en enlaces internos <a href="/..."> (misma pestaña)
	document.addEventListener('click', (e) => {
		if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
		const t = e.target;
		const el = t instanceof Element ? t.closest('a[href]') : null;
		if (!el) return;
		if (el.target && el.target !== '_self') return;
		const href = el.getAttribute('href');
		if (!href || !href.startsWith('/') || href.startsWith('//')) return;
		e.preventDefault();
		if (href !== window.location.pathname) navigate(href);
	});
}
