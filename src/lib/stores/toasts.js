// Store de avisos (toasts). Usa las clases `.toast-container` / `.toast-*` que
// ya define el CSS del shell, así que un aviso se ve igual en las 4 apps.
import { writable } from 'svelte/store';

export const toasts = writable([]);

let seq = 0;

/**
 * Muestra un aviso unos segundos y lo quita solo.
 * `tipo` es uno de: success | error | warning | info.
 */
export function avisar(mensaje, tipo = 'info', ms = 4000) {
	const id = ++seq;
	toasts.update((t) => [...t, { id, mensaje, tipo }]);
	setTimeout(() => {
		toasts.update((t) => t.filter((x) => x.id !== id));
	}, ms);
	return id;
}

export function cerrarAviso(id) {
	toasts.update((t) => t.filter((x) => x.id !== id));
}