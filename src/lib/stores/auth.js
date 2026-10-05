// Store de sesión de Mailbox.
//
// Modelo de token: IDÉNTICO al de Admon a propósito — una cadena
// "email|timestamp" que el backend NO valida por sí sola: cada request vuelve a
// leer HUB_Users y reconstruye el dict de permisos desde la fila.
//
// Por qué NO un JWT como el de Field: los permisos se leerían del token y no de
// la base, así que revocar `AccesoMailbox` a alguien no lo expulsaría hasta que
// su token venciera (90 días en Field). En un buzón, quitarle el acceso a
// alguien tiene que ser inmediato. Adquirir un permiso nuevo tampoco exige
// volver a iniciar sesión.
//
// Lo que Mailbox AGREGA sobre Admon: la expiración se guarda en la BD
// (HUB_MailboxSesiones), no solo en localStorage. En Admon el token vive
// para siempre mientras el usuario esté en HUB_Users, lo que impide cerrar la
// sesión en otro dispositivo. Ver api/main.py::_sesion_valida.
import { writable } from 'svelte/store';

const CLAVE_TOKEN = 'mailbox_token';
const CLAVE_EXPIRES = 'mailbox_expires';
const CLAVE_USUARIO = 'mailbox_user';

function _crear() {
	const { subscribe, set } = writable({
		token: null,
		user: null,
		expiresAt: null
	});

	return {
		subscribe,

		init() {
			const token = localStorage.getItem(CLAVE_TOKEN);
			const expires = Number(localStorage.getItem(CLAVE_EXPIRES) || 0);
			const usuario = localStorage.getItem(CLAVE_USUARIO);
			if (token && expires && expires > Date.now() && usuario) {
				try {
					set({ token, user: JSON.parse(usuario), expiresAt: expires });
				} catch {
					this.logout();
				}
			} else {
				this.logout();
			}
		},

		isLoggedIn() {
			const expires = Number(localStorage.getItem(CLAVE_EXPIRES) || 0);
			return !!localStorage.getItem(CLAVE_TOKEN) && expires > Date.now();
		},

		getToken() {
			return localStorage.getItem(CLAVE_TOKEN);
		},

		getUser() {
			try {
				return JSON.parse(localStorage.getItem(CLAVE_USUARIO) || 'null');
			} catch {
				return null;
			}
		},

		/** Guarda la sesión que devuelve el backend (login por contraseña o passkey). */
		async saveSession(data) {
			localStorage.setItem(CLAVE_TOKEN, data.token);
			localStorage.setItem(CLAVE_EXPIRES, String(data.expiresAt));
			localStorage.setItem(CLAVE_USUARIO, JSON.stringify(data.user));
			set({ token: data.token, user: data.user, expiresAt: data.expiresAt });
		},

		async login(email, password) {
			const res = await fetch('/api/auth/login', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email, password })
			});
			if (!res.ok) {
				// El detalle del servidor ya viene en español y es accionable
				// ("Contraseña incorrecta"), así que se propaga tal cual.
				const err = await res.json().catch(() => ({}));
				throw new Error(err.detail || 'No se pudo iniciar sesión');
			}
			await this.saveSession(await res.json());
		},

		/** Cierra la sesión en el servidor (revoca la fila de HUB_MailboxSesiones). */
		async logoutRemoto() {
			const token = localStorage.getItem(CLAVE_TOKEN);
			if (token) {
				await fetch('/api/auth/logout', {
					method: 'POST',
					headers: { 'Authorization': `Bearer ${token}` }
				}).catch(() => {});
			}
		},

		logout() {
			localStorage.removeItem(CLAVE_TOKEN);
			localStorage.removeItem(CLAVE_EXPIRES);
			localStorage.removeItem(CLAVE_USUARIO);
			// La suscripción de push queda en el servidor (ver push.js): la app
			// sigue registrada, solo deja de mostrar notificaciones en este
			// dispositivo. Desregistrarla es una decisión explícita del usuario.
			set({ token: null, user: null, expiresAt: null });
		}
	};
}

export const auth = _crear();