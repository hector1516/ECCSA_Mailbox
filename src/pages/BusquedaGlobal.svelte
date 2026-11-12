<script>
	import { onMount } from 'svelte';
	import { api, isNetworkError } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import ActionsBar from '$lib/components/ActionsBar.svelte';
	import Paginacion from '$lib/components/Paginacion.svelte';

	let { onSalir = null } = $props();

	const POR_PAGINA = 25;

	let termino = $state('');
	let mensajes = $state([]);
	let total = $state(0);
	let pagina = $state(1);
	let cargando = $state(false);
	let error = $state('');
	let buscado = $state(false);

	onMount(() => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		// Solo hector.pena tiene acceso
		const user = auth.getUser();
		if (!user || user.email !== 'hector.pena@ecc-sa.com.mx') {
			navigate('/', { replace: true });
			return;
		}
	});

	async function buscar() {
		if (!termino.trim()) {
			avisar('Escribe un término de búsqueda', 'warning');
			return;
		}
		cargando = true;
		error = '';
		buscado = true;
		try {
			const r = await api.get(
				`/mailbox/busqueda-global?buscar=${encodeURIComponent(termino.trim())}` +
				`&limite=${POR_PAGINA}&pagina=${pagina}`
			);
			mensajes = r.mensajes || [];
			total = r.total || 0;
		} catch (e) {
			error = isNetworkError(e)
				? 'Sin conexión.'
				: (e.message || 'Error en la búsqueda.');
			mensajes = [];
			total = 0;
		} finally {
			cargando = false;
		}
	}

	async function cambiarPagina(nueva) {
		pagina = nueva;
		await buscar();
	}

	// Re-buscar cuando cambia la página (para el componente Paginacion que usa bind:)
	let _paginaAnterior = $state(1);
	$effect(() => {
		if (pagina !== _paginaAnterior && buscado) {
			_paginaAnterior = pagina;
			buscar();
		}
	});

	function irAMensaje(m) {
		if (m.id_cuenta) {
			navigate(`/cuenta/${m.id_cuenta}/mensaje/${m.id}`);
		}
	}
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<h1 class="brand">🔍 Búsqueda Global</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	<div class="card" style="margin-bottom: 1rem; padding: 1rem;">
		<div style="display: flex; gap: 0.5rem; align-items: center;">
			<input
				type="text"
				class="input"
				placeholder="Buscar en todos los correos (asunto, remitente, contenido, etc.)..."
				bind:value={termino}
				onkeydown={(e) => e.key === 'Enter' && buscar()}
				style="flex: 1;"
			/>
			<button class="btn btn-primary" onclick={buscar} disabled={cargando}>
				{cargando ? 'Buscando...' : 'Buscar'}
			</button>
		</div>
		{#if buscado}
			<div style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--color-text-muted);">
				{total} resultado{total !== 1 ? 's' : ''} encontrado{total !== 1 ? 's' : ''}
			</div>
		{/if}
	</div>

	{#if error}
		<div class="alert alert-danger">
			<span>{error}</span>
		</div>
	{/if}

	{#if cargando}
		<div class="empty">
			<div class="mb-spinner"></div>
			<p>Buscando...</p>
		</div>
	{:else if buscado && mensajes.length === 0}
		<div class="empty">
			<p>No se encontraron resultados para "{termino}"</p>
		</div>
	{:else if mensajes.length > 0}
		<div class="card">
			{#each mensajes as m (m.id)}
				<button class="mensaje-row" onclick={() => irAMensaje(m)}>
					<div class="mensaje-info">
						<div class="mensaje-header">
							<span class="cuenta-badge">{m.cuenta_alias || m.cuenta_email || 'Sin cuenta'}</span>
							<span class="carpeta-badge">{m.carpeta || 'INBOX'}</span>
							<span class="fecha">{m.fecha_correo}</span>
						</div>
						<div class="mensaje-asunto">{m.asunto || '(Sin asunto)'}</div>
						<div class="mensaje-remitente">{m.remitente_nombre || m.remitente_email || ''}</div>
						{#if m.extracto}
							<div class="mensaje-extracto">{m.extracto}</div>
						{/if}
					</div>
				</button>
			{/each}
		</div>
		{#if total > POR_PAGINA}
			<Paginacion {total} bind:pagina={pagina} porPagina={POR_PAGINA} />
		{/if}
	{/if}
</div>

<style>
	.brand-col { display: flex; flex-direction: column; gap: 0; }
	.brand { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1.2rem; }

	.mb-spinner {
		width: 28px;
		height: 28px;
		margin: 0 auto 0.75rem;
		border: 3px solid var(--color-surface-2);
		border-top-color: var(--color-primary);
		border-radius: 50%;
		animation: mb-spin 0.8s linear infinite;
	}
	@keyframes mb-spin { to { transform: rotate(360deg); } }

	.alert {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.85rem 1rem;
		border-radius: var(--radius-sm);
		font-size: 0.85rem;
		margin-bottom: 1rem;
	}
	.alert-danger {
		background: rgba(239, 68, 68, 0.15);
		color: var(--color-danger);
	}

	.mensaje-row {
		display: block;
		width: 100%;
		text-align: left;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--color-border);
		background: none;
		cursor: pointer;
		transition: background 0.15s;
	}
	.mensaje-row:hover {
		background: var(--color-surface-2);
	}
	.mensaje-header {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		margin-bottom: 0.25rem;
		flex-wrap: wrap;
	}
	.cuenta-badge {
		font-size: 0.75rem;
		background: var(--color-primary);
		color: white;
		padding: 0.15rem 0.5rem;
		border-radius: 4px;
	}
	.carpeta-badge {
		font-size: 0.75rem;
		background: var(--color-surface-2);
		padding: 0.15rem 0.5rem;
		border-radius: 4px;
	}
	.fecha {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin-left: auto;
	}
	.mensaje-asunto {
		font-weight: 600;
		font-size: 0.9rem;
		margin-bottom: 0.15rem;
	}
	.mensaje-remitente {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}
	.mensaje-extracto {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		margin-top: 0.25rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.empty {
		text-align: center;
		padding: 2rem;
		color: var(--color-text-muted);
	}
</style>
