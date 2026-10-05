<script>
	import { onMount } from 'svelte';
	import { api, isNetworkError } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import { ponerContador, refrescarContador } from '$lib/push.js';
	import ActionsBar from '../components/ActionsBar.svelte';
	import Paginacion from '../components/Paginacion.svelte';

	let { cuentaId = 0, onSalir = null } = $props();

	// 25 y no 50: la lista ahora trae remitente + dos líneas de extracto, así
	// que 50 tarjetas son una pantalla muy larga y el scroll infinito no existe
	// en una PWA. Con paginación es más barato mantener  la lista corta.
	const POR_PAGINA = 25;

	let cuenta = $state(null);
	let mensajes = $state([]);
	let carpetas = $state([]);
	let total = $state(0);
	let pagina = $state(1);
	let cargando = $state(true);
	let error = $state('');
	let carpeta = $state('NOLEIDOS');
	let mostrarNueva = $state(false);
	let nombreNueva = $state('');
	let guardando = $state(false);
	let totalNoLeidos = $state(0);

	// Las carpetas NO son una lista fija: se piden al backend, que las lee del
	// índice. Antes eran dos literales (INBOX y Sent) escritas en el front, por
	// eso no había forma de agregar ni de ver las carpetas que el usuario crea
	// en su correo.
	const ETIQUETAS = {
		INBOX: { label: 'Entrada', icon: '📥' },
		Sent: { label: 'Enviados', icon: '📤' },
	};
	function etiquetaCarpeta(id) {
		return ETIQUETAS[id] || { label: id, icon: '📁' };
	}

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		await cargar();
	});

	async function cargar() {
		cargando = true;
		error = '';
		try {
			cuenta = await api.get(`/mailbox/cuentas/${cuentaId}`);
			await cargarCarpetas();

			// EL BUG QUE HACÍA QUE NO SE VIERAN LOS CORREOS
			// ---------------------------------------------------
			// El endpoint devuelve un SOBRE: { mensajes: [...], total, pagina,
			// limite, no_leidos }. Este código asignaba el sobre entero a
			// `mensajes`, así que el `{#each}` iteraba sobre las 5 claves del
			// objeto ("mensajes", "total", "pagina"...) y no sobre los correos.
			// Cada fila salía con remitente vacío y asunto vacío, y el mensaje
			// se veía en la base y en la API pero no en pantalla.
			//
			// Se lee `.mensajes` del sobre. Y `total` se usa para la
			// paginación, que es la razón de que el endpoint devuelva el sobre.
			const r = await api.get(
				`/mailbox/cuentas/${cuentaId}/mensajes?carpeta=${encodeURIComponent(carpeta)}` +
				`&limite=${POR_PAGINA}&pagina=${pagina}`
			);
			mensajes = r.mensajes || [];
			total = r.total || 0;
		} catch (e) {
			error = isNetworkError(e)
				? 'Sin conexión. Los correos se vuelven a pedir al recuperar la red.'
				: (e.message || 'No se pudo cargar la cuenta.');
			mensajes = [];
			total = 0;
		} finally {
			cargando = false;
		}
	}

	async function cargarCarpetas() {
		const r = await api.get(`/mailbox/cuentas/${cuentaId}/carpetas`);
		carpetas = r.carpetas || [];
		totalNoLeidos = r.no_leidos || 0;
	}

	async function cambiarCarpeta(id) {
		carpeta = id;
		pagina = 1;
		await cargar();
	}

	async function cambiarPagina(p) {
		pagina = p;
		await cargar();
		window.scrollTo({ top: 0, behavior: 'smooth' });
	}

	async function crearCarpeta() {
		const nombre = nombreNueva.trim();
		if (!nombre) return;
		guardando = true;
		try {
			await api.post(`/mailbox/cuentas/${cuentaId}/carpetas`, { nombre });
			mostrarNueva = false;
			nombreNueva = '';
			avisar('Carpeta creada. Aparece en cuanto el worker la confirme.', 'ok');
			await cargarCarpetas();
		} catch (e) {
			avisar(e.message || 'No se pudo crear la carpeta', 'error');
		} finally {
			guardando = false;
		}
	}

</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<button class="back-btn" onclick={() => navigate('/')} title="Volver">←</button>
			<h1 class="brand">{cuenta?.alias || cuenta?.email || 'Cuenta'}</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	{#if cuenta}
		<div class="cb-meta">
			<span class="cb-email">{cuenta.email}</span>
			{#if cuenta.ultimo_sync}
				<span class="cb-sync">🔄 Última sincronización: {cuenta.ultimo_sync}</span>
			{:else}
				<span class="cb-sync cb-sync--nunca">⏳ Todavía no se ha sincronizado esta cuenta</span>
			{/if}
			{#if cuenta.ultimo_error}
				<span class="cb-error">⚠️ {cuenta.ultimo_error}</span>
			{/if}
		</div>
	{/if}

	<!-- Pestañas de carpeta -->
	<div class="cb-tabs">
		<!-- "No leídos" va PRIMERO y es una pseudo-carpeta: no existe en IMAP,
		     es un atajo a Visto = 0 sobre todas las carpetas. Es lo primero que
		     quiere ver quien abre la app: qué hay pendiente, no el último correo
		     que llegó. Antes la pestaña de Entrada mezclaba los 407 correos
		     archivados con los de hoy y no había forma de separar los nuevos. -->
		<button class="cb-tab" class:active={carpeta === 'NOLEIDOS'} onclick={() => cambiarCarpeta('NOLEIDOS')}>
			<span>🔴</span> No leídos
			{#if totalNoLeidos > 0}<span class="cb-tab-n">{totalNoLeidos}</span>{/if}
		</button>

		{#each carpetas as c (c.id)}
			{@const et = etiquetaCarpeta(c.id)}
			<button class="cb-tab" class:active={carpeta === c.id} onclick={() => cambiarCarpeta(c.id)}>
				<span>{et.icon}</span> {et.label}
				{#if c.no_leidos > 0}<span class="cb-tab-n">{c.no_leidos}</span>{/if}
			</button>
		{/each}

		<button class="cb-tab cb-tab--nueva" onclick={() => (mostrarNueva = !mostrarNueva)}
			title="Crear carpeta">＋</button>
	</div>

	{#if mostrarNueva}
		<form class="cb-nueva" onsubmit={(e) => { e.preventDefault(); crearCarpeta(); }}>
			<input type="text" bind:value={nombreNueva} maxlength="60" placeholder="Nombre de la carpeta"
				autofocus aria-label="Nombre de la carpeta" />
			<button class="btn btn-sm btn-primary" type="submit" disabled={guardando || !nombreNueva.trim()}>
				{guardando ? 'Creando…' : 'Crear'}
			</button>
			<button class="btn btn-sm btn-secondary" type="button" onclick={() => (mostrarNueva = false)}>
				Cancelar
			</button>
		</form>
	{/if}

	{#if cargando}
		<div class="empty">Cargando…</div>
	{:else if mensajes.length === 0}
		<div class="card cb-vacio">
			<div class="cb-vacio-icon">📭</div>
			<h2>{carpeta === 'INBOX' ? 'No hay correos' : 'Nada enviado todavía'}</h2>
			<p>
				{#if !cuenta?.ultimo_sync}
					El worker todavía no ha sincronizado esta cuenta. En cuanto lo haga,
					los correos aparecen aquí.
				{:else}
					Esta carpeta está vacía.
				{/if}
			</p>
		</div>
	{:else}
		<!-- `.list` y `.list-card` son del shell: la lista de correos se ve igual
		     que la de reportes en Field y los remitentes en Admon. -->
		<div class="list">
			{#each mensajes as m (m.id)}
				<button class="list-card cb-msg" class:sin-leer={!m.visto}
				        onclick={() => navigate(`/cuenta/${cuentaId}/mensaje/${m.id}`)}>
					<div class="cb-msg-cuerpo">
						<div class="cb-msg-remitente">
							{#if !m.visto}<span class="cb-punto"></span>{/if}
							<!-- El remitente va en su propia línea y con el correo
							     completo debajo: con solo el nombre, dos remitentes
							     "Juan Pérez" de empresas distintas son indistinguibles
							     y en un correo de trabajo ése es el dato que importa. -->
							<span class="cb-nombre">{m.remitente_nombre || m.remitente_email || '(sin remitente)'}</span>
							{#if m.remitente_nombre && m.remitente_email}
								<span class="cb-remitente-mail">{m.remitente_email}</span>
							{/if}
						</div>
						<div class="cb-asunto">{m.asunto || '(sin asunto)'}</div>
						<!-- DOS LÍNEAS: el `extracto` es lo que decide si un correo
						     se abre o se borra, y a una sola línea casi siempre
						     alcanza para decidir mal. -->
						<div class="cb-snippet">{m.extracto || ''}</div>
					</div>
					<div class="cb-lateral">
						<span class="cb-fecha">{m.fecha_correo || ''}</span>
						{#if m.tiene_adjuntos}
							<span class="cb-clip" title="{m.num_adjuntos} adjuntos">📎 {m.num_adjuntos || ''}</span>
						{/if}
					</div>
				</button>
			{/each}
		</div>

		<Paginacion total={total} bind:pagina={pagina} porPagina={POR_PAGINA}
			etiqueta="correos" />
	{/if}
</div>

<style>
	.brand-col { display: flex; align-items: center; gap: 0.75rem; }
	.brand { font-size: 1.1rem; margin: 0; }

	/* ── Metadatos de la cuenta ──────────────────────────────────────────── */
	.cb-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem 0.9rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin-bottom: 0.9rem;
	}
	.cb-email { font-weight: 600; color: var(--color-text); }
	.cb-sync--nunca { color: var(--color-warning); }
	.cb-error { color: var(--color-danger); flex-basis: 100%; }

	/* ── Carpeta nueva ──────────────────────────────────────────────────── */
	.cb-nueva {
		display: flex;
		gap: 0.4rem;
		margin-bottom: 0.9rem;
		flex-wrap: wrap;
	}
	.cb-nueva input {
		flex: 1 1 12rem;
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-sm);
		padding: 0.45rem 0.6rem;
		font-size: 0.85rem;
		font-family: inherit;
	}
	.cb-tab--nueva {
		font-size: 1rem;
		font-weight: 700;
		padding: 0.4rem 0.7rem;
		color: var(--color-primary);
	}

	/* ── Carpetas ────────────────────────────────────────────────────────── */
	.cb-tabs {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1rem;
		overflow-x: auto;
		/* El shell pone -webkit-overflow-scrolling en otros sitios; aquí se
		   repite porque sin esto la barra se corta en iOS. */
		-webkit-overflow-scrolling: touch;
	}
	.cb-tab {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.5rem 0.85rem;
		border-radius: var(--radius-xs);
		background: var(--color-surface);
		border: 1px solid rgba(255, 255, 255, 0.05);
		color: var(--color-text-muted);
		font-size: 0.82rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		transition: all 0.15s;
	}
	.cb-tab.active {
		background: rgba(255, 107, 0, 0.12);
		color: var(--color-primary);
		border-color: rgba(255, 107, 0, 0.3);
	}
	.cb-tab-n {
		background: var(--color-primary);
		color: #fff;
		border-radius: 999px;
		font-size: 0.65rem;
		padding: 0 0.35rem;
		font-weight: 700;
	}

	/* ── Alerta ───────────────────────────────────────────────────────────── */
	.cb-alert {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.8rem 0.9rem;
		border-radius: var(--radius-sm);
		background: rgba(239, 68, 68, 0.15);
		color: var(--color-danger);
		font-size: 0.82rem;
		margin-bottom: 1rem;
	}

	/* ── Lista de mensajes ───────────────────────────────────────────────── */
	/* `.list-card` es del shell y pone display:flex + justify-between; esta
	   regla solo reparte el ancho entre el texto y la columna lateral. */
	.cb-msg { gap: 0.75rem; align-items: flex-start; }
	.cb-msg-cuerpo { flex: 1; min-width: 0; }

	.cb-msg-remitente { display: flex; align-items: center; gap: 0.4rem; }
	/* Punto de no leído. Con `align-items: center` en un flex de una línea, el
	   punto se vería achatado si tuviera tamaño; el flex-shrink lo evita. */
	.cb-punto {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--color-primary);
		flex: 0 0 auto;
	}
	.cb-nombre {
		font-size: 0.88rem;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.cb-msg.sin-leer .cb-asunto { font-weight: 700; color: var(--color-text); }

	.cb-asunto {
		font-size: 0.83rem;
		color: var(--color-text);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		margin-top: 0.1rem;
	}
	.cb-remitente-mail {
		font-size: 0.72rem;
		font-weight: 400;
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.cb-snippet {
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		line-height: 1.35;
	
		font-size: 0.75rem;
		color: var(--color-text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		margin-top: 0.1rem;
	}

	.cb-lateral {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.25rem;
		flex: 0 0 auto;
		font-size: 0.7rem;
		color: var(--color-text-muted);
	}
	.cb-fecha { white-space: nowrap; }

	/* ── Vacío ────────────────────────────────────────────────────────────── */
	.cb-vacio { text-align: center; padding: 2rem 1.25rem; }
	.cb-vacio-icon { font-size: 3rem; margin-bottom: 0.75rem; }
	.cb-vacio h2 { font-size: 1rem; margin: 0 0 0.4rem; }
	.cb-vacio p { font-size: 0.85rem; color: var(--color-text-muted); margin: 0; line-height: 1.5; }
</style>