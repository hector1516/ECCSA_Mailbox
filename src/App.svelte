<script>
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { path, navigate } from '$lib/router.js';
	import { auth } from '$lib/stores/auth.js';
	import { online, onlinePing } from '$lib/stores/online.js';
	import { toasts, cerrarAviso } from '$lib/stores/toasts.js';
	import SyncHeader from './components/SyncHeader.svelte';
	import Changelog from './components/Changelog.svelte';
	import { APP_VERSION, SHELL_VERSION } from '$lib/shell.js';
	import Login from './pages/Login.svelte';
	import Home from './pages/Home.svelte';
	import Firmas from './pages/Firmas.svelte';
	import Notificaciones from './pages/Notificaciones.svelte';
	import Cuenta from './pages/Cuenta.svelte';
	import Mensaje from './pages/Mensaje.svelte';
	import Redactar from './pages/Redactar.svelte';
	import Reglas from './pages/Reglas.svelte';

	// Los segmentos de la ruta, una vez. El dispatcher de abajo los compara por
	// posición en vez de con `startsWith`/`endsWith`: la ruta del mensaje es
	// `/cuenta/<id>/mensaje/<idMensaje>`, que TERMINA en el id del mensaje, así que
	// un `endsWith('/mensaje')` nunca es cierto y la vista no se alcanza nunca.
	const seg = $derived($path.split('/'));

	let ready = $state(false);
	let splashDone = $state(false);
	let splashMsg = $state('');
	let splashProgress = $state(0);

	const splashMessages = [
		'✉️ Preparando el buzón...',
		'🎈 Sincronizando las cuentas...',
		'📡 Alineando antenas con el servidor...',
		'☕ Convirtiendo café en correos...',
		'🔐 Abriendo el sobre cifrado...',
		'⚙️ Ajustando el engrane del servidor...',
		'📬 Contando lo que no se ha leído...'
	];

	onMount(async () => {
		// Splash corto: 2 frases al azar, 800 ms cada una.
		const msgs = [...splashMessages].sort(() => Math.random() - 0.5).slice(0, 2);
		for (let i = 0; i < msgs.length; i++) {
			splashMsg = msgs[i];
			splashProgress = ((i + 1) / msgs.length) * 100;
			await new Promise((r) => setTimeout(r, 800));
		}
		splashDone = true;

		auth.init();
		const actual = window.location.pathname;
		if (!auth.isLoggedIn() && actual !== '/login') {
			navigate('/login', { replace: true });
		}
		ready = true;
		onlinePing().catch(() => {});

		// El service worker notifica que el usuario tocó una notificación.
		// Se centraliza acá (y no en cada página) porque el SW vive más que
		// cualquier vista.
		if ('serviceWorker' in navigator) {
			const sw = await navigator.serviceWorker.getRegistration();
			sw?.addEventListener('message', (e) => {
				if (e.data?.type === 'ABRIR_MENSAJE') {
					navigate(e.data.url || '/', { replace: false });
				}
			});
		}
	});

	// ── Banner común ECCSA-Shell ─────────────────────────────────────────────
	// El componente es del shell y no sabe nada de Mailbox: el estado, el
	// usuario y el clic le llegan por props, y `fetcher` le aporta la cabecera
	// Bearer (sin ella, /api/shell/state da 401 y el 🏢/🏠 se queda en 📍 sin
	// avisar). Ver ECCSA-Shell/docs/CONTRATO.md.
	function shellEstado() {
		if (!get(online)) return 'offline';
		// Mailbox no tiene cola de escritura local en la v1: el worker es el
		// dueño del sync. Lo que sí puede estar pendiente son las operaciones
		// que el usuario encoló y el worker todavía no aplicó al buzón.
		return 'idle';
	}

	async function shellSync() {
		if (!get(online)) return;
		await onlinePing();
		// "Sincronizar" desde el banner significa que el worker recoja ya lo
		// encolado. El backend expone el endpoint para eso.
		try {
			await fetch('/api/sync/pedir', {
				method: 'POST',
				headers: { Authorization: `Bearer ${auth.getToken() || ''}` }
			});
		} catch {
			/* si falla, el banner igual queda en su estado */
		}
	}

	function shellFetch(url) {
		const token = auth.getToken();
		return fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
	}

	function cerrarSesion() {
		auth.logoutRemoto();
		auth.logout();
		navigate('/login', { replace: true });
	}

	// ── Pestañas inferiores ───────────────────────────────────────────────────
	// Las define el shell (.bottom-nav / .nav-item); Mailbox usa las mismas que
	// Field para que la app se sienta de la misma familia.
	const TABS = [
		{ icon: '🏠', label: 'Inicio', ruta: '/' },
		{ icon: '✍️', label: 'Firmas', ruta: '/firmas' },
		{ icon: '📐', label: 'Reglas', ruta: '/reglas' },
		{ icon: '🔔', label: 'Alertas', ruta: '/notificaciones' }
	];

	function pestanaActiva(ruta) {
		if (ruta === '/') return $path === '/' || $path === '';
		return $path === ruta || $path.startsWith(ruta + '/');
	}
</script>

{#if !splashDone}
	<div class="splash">
		<img class="splash-logo-img" src="/mailbox_logo.png" alt="Mailbox ECCSA" />
		<div class="splash-title">Mailbox</div>
		<div class="splash-msg">{splashMsg}</div>
		<div class="splash-bar">
			<div class="splash-bar-fill" style="width:{splashProgress}%"></div>
		</div>
	</div>
{:else if ready}
	{#if $auth.user}
		<SyncHeader
			estado={shellEstado()}
			pendientes={0}
			usuario={$auth.user.nombre}
			appVersion={APP_VERSION}
			shellVersion={SHELL_VERSION}
			fetcher={shellFetch}
			onsync={shellSync}
		/>

		<!-- Popup de novedades (del shell). Va UNA vez acá, en el App, para que
		     salte aunque se entre por cualquier ruta. El texto de los cambios está
		     en public/changelog.json, así se edita sin recompilar. -->
		<Changelog appId="mailbox" appName="Mailbox" version={APP_VERSION}
		           url="/changelog.json" />
	{/if}

	<!-- shell-below-banner: el padding para no quedar bajo el banner fijo lo
	     pone el shell (era un 3.8rem mágico repetido en cada app). -->
	<div class={$auth.user ? 'shell-below-banner' : ''}>
		<!--
		  Los segmentos se sacan UNA vez y se comparan por posición. La ruta del
		  mensaje es `/cuenta/<id>/mensaje/<idMensaje>`: cinco segmentos contando
		  el vacío inicial.

		  Podría escribirse `$path.endsWith('/mensaje')`, pero eso nunca es
		  cierto —la ruta del mensaje TERMINA en el id del mensaje— y el resultado
		  es que la vista de mensaje no se alcanza nunca: la cadena `{#if}` cae al
		  genérico de `/cuenta/` y se ve la lista con el mensaje "dentro". Es un
		  bug silencioso, porque la navegación funciona y la URL es correcta.
		-->
		{#if $path === '/login'}
			<Login />
		<!--
		  EL ORDEN IMPORTA. El dispatch es una cadena {#if}/{@else if} y gana la
		  primera que coincide, así que `/cuenta/5/mensaje/123` tiene que
		  preguntarse ANTES que `/cuenta/5`: si el genérico fuera primero, la
		  vista de mensaje nunca se alcanzaría.
		-->
		{:else if seg[1] === 'cuenta' && seg[3] === 'mensaje' && seg.length >= 5}
			<!-- ["", "cuenta", 5, "mensaje", 123] → cuenta en [2], mensaje en [4] -->
			<Mensaje mensajeId={Number(seg[4])} onSalir={cerrarSesion} />
		{:else if seg[1] === 'cuenta' && seg.length >= 3}
			<Cuenta cuentaId={Number(seg[2])} onSalir={cerrarSesion} />
		{:else if $path === '/firmas'}
			<Firmas onSalir={cerrarSesion} />
		{:else if $path === '/reglas'}
			<Reglas onSalir={cerrarSesion} />
		{:else if $path === '/redactar'}
			<Redactar onSalir={cerrarSesion} />
		{:else if $path === '/notificaciones'}
			<Notificaciones onSalir={cerrarSesion} />
		{:else if !$auth.user}
			<!-- Ruta protegida sin sesión: se manda al login y no se renderiza nada
			     para que no se vea un instante la pantalla vacía. -->
			<div class="page"><div class="empty">Redirigiendo…</div></div>
		{:else}
			<Home onSalir={cerrarSesion} />
		{/if}

		<div class="version-badge">Mailbox v{APP_VERSION}</div>
	</div>

	<!-- Barra de pestañas: solo con sesión, y solo en pantallas donde hay
	     espacio. En una PC angosta estorba más de lo que ayuda. -->
	{#if $auth.user}
		<nav class="bottom-nav tab-bar">
			{#each TABS as t}
				<button class="nav-item" class:active={pestanaActiva(t.ruta)}
				        onclick={() => navigate(t.ruta)}>
					<span class="nav-icon">{t.icon}</span>
					<span>{t.label}</span>
				</button>
			{/each}
		</nav>
	{/if}

	<!-- Avisos (toasts). El contenedor y sus clases los define el shell. -->
	<div class="toast-container">
		{#each $toasts as t (t.id)}
			<div class="toast toast-{t.tipo}" role="status"
			     onclick={() => cerrarAviso(t.id)}>
				{t.mensaje}
			</div>
		{/each}
	</div>
{:else}
	<div class="splash">
		<img class="splash-logo-img" src="/mailbox_logo.png" alt="Mailbox ECCSA" />
		<div class="splash-title">Mailbox</div>
	</div>
{/if}

<style>
	/* La barra de pestañas usa las clases del shell (.bottom-nav / .nav-item).
	   Lo único propio es poder ocultarla en pantallas anchas, donde el menú de
	   tarjetas de la home ya hace de navegación y una barra fija abajo estorba
	   (además de quedar rarísima en un monitor). */
	@media (min-width: 900px) {
		.tab-bar { display: none; }
	}

	/* En el login no hay navegación de fondo. */
	.toast { cursor: pointer; }
</style>