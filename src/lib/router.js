import { writable } from 'svelte/store';

// Micro-router history-mode (sin dependencias, nativo Svelte 5).
// Reemplaza a svelte-routing, cuyo prop `component={...}` invoca los
// componentes-función de Svelte 5 sin argumentos y rompe el render.
export const path = writable(
	typeof window !== 'undefined' ? window.location.pathname : '/'
);

export function navigate(to, { replace = false } = {}) {
	if (typeof window === 'undefined') return;
	if (replace) history.replaceState({}, '', to);
	else history.pushState({}, '', to);
	path.set(to);
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
