<script>
	import { onMount } from 'svelte';
	import { api, isNetworkError } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import { ponerContador, refrescarContador } from '$lib/push.js';
	import ActionsBar from '../components/ActionsBar.svelte';

	let { cuentaId = 0, onSalir = null } = $props();

	let cuenta = $state(null);
	let mensajes = $state([]);
	let cargando = $state(true);
	let error = $state('');
	let carpeta = $state('INBOX');

	// Las carpetas que se listan. El worker sincroniza INBOX y Sent de entrada;
	// el resto de IMAP (borradores, archivo, papelera) llega en la fase de
	// lectura completa. Ver AGENTS.md §Fases.
	const CARPETAS = [
		{ id: 'INBOX', label: 'Entrada', icon: '📥' },
		{ id: 'Sent', label: 'Enviados', icon: '📤' }
	];

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
			mensajes = await api.get(`/mailbox/cuentas/${cuentaId}/mensajes?carpeta=${encodeURIComponent(carpeta)}&limite=50`);
		} catch (e) {
			error = isNetworkError(e)
				? 'Sin conexión. Los correos se vuelven a pedir al recuperar la red.'
				: (e.message || 'No se pudo cargar la cuenta.');
		} finally {
			cargando = false;
		}
	}

	async function cambiarCarpeta(id) {
		carpeta = id;
		await cargar();
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
		{#each CARPETAS as c}
			<button class="cb-tab" class:active={carpeta === c.id} onclick={() => cambiarCarpeta(c.id)}>
				<span>{c.icon}</span> {c.label}
				{#if c.id === 'INBOX' && cuenta?.no_leidos > 0}
					<span class="cb-tab-n">{cuenta.no_leidos}</span>
				{/if}
			</button>
		{/each}
	</div>

	{#if error}
		<div class="cb-alert">
			<span>{error}</span>
			<button class="btn btn-sm btn-secondary" onclick={cargar}>Reintentar</button>
		</div>
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
							<span class="cb-nombre">{m.remitente_nombre || m.remitente_email}</span>
						</div>
						<div class="cb-asunto">{m.asunto || '(sin asunto)'}</div>
						<div class="cb-snippet">{m.extracto || ''}</div>
					</div>
					<div class="cb-lateral">
						<span class="cb-fecha">{m.fecha_correo || ''}</span>
						{#if m.tiene_adjuntos}<span class="cb-clip">📎 {m.num_adjuntos || ''}</span>{/if}
					</div>
				</button>
			{/each}
		</div>
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
	.cb-snippet {
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