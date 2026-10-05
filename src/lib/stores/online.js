import { writable } from 'svelte/store';

// Estado de conectividad (espejo del store online de Field, sin IndexedDB).
// - navigator.onLine + eventos online/offline
// - ping periódico a /api/health para verificar conectividad real
export const online = writable(typeof navigator !== 'undefined' ? navigator.onLine : true);

export async function onlinePing() {
	try {
		const ctl = new AbortController();
		const t = setTimeout(() => ctl.abort(), 5000);
		const res = await fetch('/api/health', { signal: ctl.signal, cache: 'no-store' });
		clearTimeout(t);
		online.set(res.ok);
		return res.ok;
	} catch {
		online.set(false);
		return false;
	}
}

if (typeof window !== 'undefined') {
	window.addEventListener('online', () => onlinePing());
	window.addEventListener('offline', () => online.set(false));
	setInterval(() => onlinePing(), 30000);
	onlinePing();
}
