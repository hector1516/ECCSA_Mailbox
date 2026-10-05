<script>
	import { onMount } from 'svelte';
	import { api, isNetworkError } from '$lib/api.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { auth } from '$lib/stores/auth.js';
	import { navigate } from '$lib/router.js';
	import { ponerContador, refrescarContador } from '$lib/push.js';
	import ActionsBar from '../components/ActionsBar.svelte';

	/** onSalir lo pasa App.svelte; acá solo se propaga a la barra de acciones. */
	let { onSalir = null } = $props();

	let cuentas = $state([]);
	let cargando = $state(true);
	let error = $state('');

	// Módulos que son herramientas, no cuentas de correo. Vienen después de las
	// cuentas para que la home sea primero "mi correo" y después "mis
	// herramientas", que es el orden en el que se usan.
	const HERRAMIENTAS = [
		{ icon: '✍️', title: 'Redactar', desc: 'Escribir un correo', path: '/redactar' },
		{ icon: '✒️', title: 'Firmas', desc: 'Tu firma y sus imágenes', path: '/firmas' },
		{ icon: '📐', title: 'Reglas', desc: 'Filtros y ausencias', path: '/reglas' },
		{ icon: '🔔', title: 'Alertas', desc: 'Notificaciones en el teléfono', path: '/notificaciones' }
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
			const datos = await api.get('/mailbox/cuentas');
			cuentas = Array.isArray(datos) ? datos : [];
			// El número de no leídos de TODAS las cuentas se usa para el badge del
			// ícono de la app (en iOS es un número, no una imagen).
			const total = cuentas.reduce((a, c) => a + (c.no_leidos || 0), 0);
			if (total > 0) ponerContador(total);
			else refrescarContador();
		} catch (e) {
			if (isNetworkError(e)) {
				error = 'Sin conexión. Revisa tu red e inténtalo de nuevo.';
			} else {
				error = e.message || 'No se pudieron cargar las cuentas.';
			}
		} finally {
			cargando = false;
		}
	}

	function ir(path) {
		navigate(path);
	}
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<h1 class="brand">
				<img class="brand-logo" src="/mailbox_marca.png" alt="Mailbox" /> Mailbox
			</h1>
		</div>
		<!-- Barra de acciones del shell. Solo se pasan los manejadores que existen:
		     el componente oculta los demás, así no aparecen botones muertos. -->
		<ActionsBar onlogout={onSalir} />
	</div>

	{#if error}
		<div class="alert alert-danger">
			<span>{error}</span>
			<button class="btn btn-sm btn-secondary" onclick={cargar}>Reintentar</button>
		</div>
	{/if}

	{#if cargando}
		<div class="empty">
			<div class="mb-spinner"></div>
			<p>Cargando tus cuentas…</p>
		</div>
	{:else if cuentas.length === 0}
		<!-- Sin cuentas asignadas: no es un error, es un estado real (alguien
		     recién highsueldo, o el admin todavía no le asignó ninguna). Se explica
		     qué hacer en vez de mostrar una pantalla vacía. -->
		<div class="card mb-vacio">
			<div class="mb-vacio-icon">📭</div>
			<h2>Todavía no tienes cuentas asignadas</h2>
			<p>
				Las cuentas de correo las asigna un administrador desde el panel de
				ECCSA. Cuando te asigne una, aparecerá aquí como una tarjeta.
			</p>
			<a class="btn btn-secondary" href="mailto:administracion@ecc-sa.com.mx?subject=Alta%20en%20Mailbox%20ECCSA">
				✉️ Solicitar una cuenta
			</a>
		</div>
	{:else}
		<!-- `.module-grid` y `.module-card` son del shell: mismo look que la
		     home de Admon y Field, columnas por resolución, tarjeta rectangular.
		     El contador de no leídos va en `.module-badge`, que el shell posiciona
		     en la esquina. -->
		<div class="module-grid">
			{#each cuentas as c (c.id)}
				<button class="module-card" onclick={() => ir(`/cuenta/${c.id}`)}>
					<span class="module-icon">{c.icono || '📬'}</span>
					<span class="module-title">{c.alias || c.email}</span>
					<span class="module-desc">{c.email}</span>
					{#if c.no_leidos > 0}
						<span class="module-badge">{c.no_leidos > 99 ? '99+' : c.no_leidos}</span>
					{/if}
				</button>
			{/each}

			{#each HERRAMIENTAS as h}
				<button class="module-card" onclick={() => ir(h.path)}>
					<span class="module-icon">{h.icon}</span>
					<span class="module-title">{h.title}</span>
					<span class="module-desc">{h.desc}</span>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	/* ── Propio de esta vista (el shell no lo trae) ────────────────────────── */

	.brand-col { display: flex; flex-direction: column; gap: 0; }
	.brand { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1.2rem; }
	/* object-fit: cover + el mismo radio que el logo shaved. Sin esto se ve el
	   PNG completo (que es 218x186, no cuadrado) con las esquinas redondeadas
	   sobre el fondo transparente. */
	.brand-logo {
		width: 34px;
		height: 34px;
		object-fit: cover;
		border-radius: 8px;
	}

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

	.mb-vacio { text-align: center; padding: 2rem 1.25rem; }
	.mb-vacio-icon { font-size: 3rem; line-height: 1; margin-bottom: 0.75rem; }
	.mb-vacio h2 { font-size: 1.05rem; margin: 0 0 0.5rem; }
	.mb-vacio p {
		color: var(--color-text-muted);
		font-size: 0.85rem;
		line-height: 1.5;
		margin: 0 0 1.25rem;
	}
</style>