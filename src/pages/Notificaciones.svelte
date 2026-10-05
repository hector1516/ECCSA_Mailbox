<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import { estado, activar, desactivar } from '$lib/push.js';
	import ActionsBar from '../components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let st = $state(null);
	let ocupado = $state(false);

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		await refrescar();
	});

	async function refrescar() {
		st = await estado();
	}

	// ── Activar ──────────────────────────────────────────────────────────────
	// Esta función es el gesto del usuario: se llama desde onclick y en iOS
	// ESE es el requisito para que requestPermission() muestre el diálogo.
	// Si se moviera a un onMount, en iPhone no aparecería nada y el usuario
	// pensaría que la app está rota.
	async function activarNotificaciones() {
		ocupado = true;
		const r = await activar();
		ocupado = false;
		if (r.ok) {
			avisar('Notificaciones activadas 📬', 'success');
		} else {
			avisar(r.motivo, 'error', 7000);
		}
		await refrescar();
	}

	async function apagarNotificaciones() {
		ocupado = true;
		const r = await desactivar();
		ocupado = false;
		avisar(r.ok ? 'Notificaciones desactivadas' : r.motivo, r.ok ? 'info' : 'error');
		await refrescar();
	}

	async function enviarPrueba() {
		ocupado = true;
		try {
			await api.post('/push/prueba');
			avisar('Prueba enviada. Tarda unos segundos en llegar.', 'success');
		} catch (e) {
			avisar(e.message || 'No se pudo enviar la prueba', 'error');
		} finally {
			ocupado = false;
		}
	}

	// ── Textos según el estado ───────────────────────────────────────────────
	let titulo = $derived.by(() => {
		if (!st) return '';
		if (st.suscrito) return 'Notificaciones activas';
		if (st.permiso === 'denied') return 'Notificaciones bloqueadas';
		if (st.permiso === 'granted') return 'Falta activar';
		return 'Notificaciones desactivadas';
	});

	let iconoEstado = $derived.by(() => {
		if (!st) return '🔔';
		if (st.suscrito) return '✅';
		if (st.permiso === 'denied') return '🚫';
		return '🔕';
	});
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<button class="back-btn" onclick={() => navigate('/')} title="Volver">←</button>
			<h1 class="brand">Alertas</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	{#if !st}
		<div class="empty">Cargando…</div>
	{:else}
		<!-- Tarjeta de estado -->
		<div class="card nb-estado" class:ok={st.suscrito}>
			<div class="nb-estado-icono">{iconoEstado}</div>
			<div class="nb-estado-texto">
				<strong>{titulo}</strong>
				{#if st.suscrito}
					<p>Este teléfono te avisa cuando llega un correo nuevo.</p>
				{:else if st.permiso === 'denied'}
					<p>El navegador no deja preguntar. Hay que reactivarlo en los ajustes.</p>
				{:else}
					<p>Actívalas para enterarte de los correos nuevos aunque no tengas la app abierta.</p>
				{/if}
			</div>
		</div>

		<!-- ── Bloque iOS: el que más importa ───────────────────────────────
		     En iPhone hay tres condiciones y el navegador NO avisa de ninguna.
		     En vez de un error genérico, se dice exactamente qué hacer. -->
		{#if st.ios}
			<div class="card nb-ios">
				<div class="nb-ios-head">
					<span class="nb-ios-badge">iPhone</span>
					<strong>Requisitos para recibir avisos en iPhone</strong>
				</div>

				<ul class="nb-checks">
					<li class="ok">
						<span class="nb-mark">✓</span>
						<div>
							<strong>iOS 16.4 o superior</strong>
							{#if st.versionIOS}
								<p>Este equipo tiene iOS {st.versionIOS.mayor}.{st.versionIOS.menor}{st.versionIOS.parche ? '.' + st.versionIOS.parche : ''}</p>
							{/if}
						</div>
					</li>
					<li class:ok={st.instalada}>
						<span class="nb-mark">{st.instalada ? '✓' : '✕'}</span>
						<div>
							<strong>La app instalada en la pantalla de inicio</strong>
							{#if !st.instalada}
								<p>
									Con Safari abierto en una pestaña no llegan avisos.
									Toca <b>Compartir</b> → <b>Agregar a pantalla de inicio</b> y abre
									Mailbox desde el ícono nuevo (no desde el navegador).
								</p>
							{:else}
								<p>Estás en la app instalada. ✓</p>
							{/if}
						</div>
					</li>
					<li class:ok={st.permiso === 'granted'}>
						<span class="nb-mark">{st.permiso === 'granted' ? '✓' : '○'}</span>
						<div>
							<strong>Permiso concedido</strong>
							{#if st.permiso === 'granted'}
								<p>Concedido ✓</p>
							{:else}
								<p>Se concede con el botón de abajo. iOS solo lo pregunta desde un toque.</p>
							{/if}
						</div>
					</li>
				</ul>

				{#if !st.instalada}
					<div class="nb-nota">
						<span>ℹ️</span>
						<p>
							Después de instalarla, vuelve a abrir Mailbox desde el ícono de la
							pantalla de inicio y activa las notificaciones desde aquí.
						</p>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Botón principal. Solo aparece si tiene sentido pedirlo. -->
		{#if st.suscrito}
			<button class="btn btn-secondary btn-block" onclick={apagarNotificaciones} disabled={ocupado}>
				Desactivar en este teléfono
			</button>
			<button class="btn btn-primary btn-block" onclick={enviarPrueba} disabled={ocupado}>
				📨 Enviarme una prueba
			</button>
			<p class="nb-help">
				Si no te llega la prueba, revisa que el modo <b>No molestar</b> o
				<b>Enfocar</b> del iPhone no esté activo.
			</p>
		{:else if st.listo}
			<button class="btn btn-primary btn-block nb-btn-grande" onclick={activarNotificaciones}
			        disabled={ocupado}>
				{#if ocupado}Activando…{:else}🔔 Activar notificaciones{/if}
			</button>
			{#if st.permiso === 'denied'}
				<div class="nb-nota">
					<span>🚫</span>
					<p>
						Para reactivarlas: en iPhone ve a <b>Ajustes → Notificaciones → Mailbox</b>
						y activa <b>Permitir notificaciones</b>. En Chrome o Safari de
						escritorio, desbloquea el candado junto a la dirección del sitio.
					</p>
				</div>
			{/if}
		{:else}
			<div class="nb-nota" class:aviso={st.ios}>
				<span>⚠️</span>
				<p>{st.motivo}</p>
			</div>
		{/if}

		<!-- ── Qué vas a recibir ────────────────────────────────────────────
		     Expectations: es mejor decir de antemano qué llega al teléfono y
		     qué no, para que nadie espere un aviso de algo que no lo manda. -->
		<div class="card nb-que">
			<h2>Qué llega a tu teléfono</h2>
			<ul>
				<li>✉️ <strong>Correo nuevo</strong> en la bandeja de entrada de una cuenta asignada</li>
				<li>🔔 <strong>Respuesta automática enviada</strong> por una regla tuya</li>
				<li>📋 <strong>Cola con errores</strong>, para que no se pierdan en silencio</li>
			</ul>
			<p class="nb-que-nota">
				Los correos que tú mismo envías y los que quedan en la papelera
				<b>no</b> generan aviso: sería ruido.
			</p>
		</div>
	{/if}
</div>

<style>
	/* Todo el color viene de los tokens del shell. Acá solo la estructura. */

	.brand-col { display: flex; align-items: center; gap: 0.75rem; }
	.brand { font-size: 1.2rem; margin: 0; }

	/* ── Estado ────────────────────────────────────────────────────────────── */
	.nb-estado {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 1rem;
	}
	.nb-estado.ok { border-color: rgba(34, 197, 94, 0.35); }
	.nb-estado-icono { font-size: 2rem; line-height: 1; flex: 0 0 auto; }
	.nb-estado-texto strong { font-size: 1rem; }
	.nb-estado-texto p {
		margin: 0.2rem 0 0;
		font-size: 0.82rem;
		color: var(--color-text-muted);
		line-height: 1.45;
	}

	/* ── Bloque iOS ────────────────────────────────────────────────────────── */
	.nb-ios { margin-bottom: 1rem; }
	.nb-ios-head {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin-bottom: 0.9rem;
		font-size: 0.9rem;
	}
	.nb-ios-badge {
		background: rgba(255, 255, 255, 0.08);
		color: var(--color-text);
		font-size: 0.7rem;
		font-weight: 600;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
	}

	.nb-checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.75rem; }
	.nb-checks li { display: flex; gap: 0.7rem; align-items: flex-start; }
	.nb-mark {
		flex: 0 0 auto;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		font-weight: 700;
		background: var(--color-surface-2);
		color: var(--color-text-muted);
	}
	.nb-checks li.ok .nb-mark { background: rgba(34, 197, 94, 0.18); color: var(--color-success); }
	.nb-checks strong { font-size: 0.85rem; display: block; }
	.nb-checks p {
		margin: 0.15rem 0 0;
		font-size: 0.78rem;
		color: var(--color-text-muted);
		line-height: 1.45;
	}

	/* ── Notas ─────────────────────────────────────────────────────────────── */
	.nb-nota {
		display: flex;
		gap: 0.6rem;
		align-items: flex-start;
		background: rgba(59, 130, 246, 0.12);
		border-radius: var(--radius-sm);
		padding: 0.8rem 0.9rem;
		font-size: 0.8rem;
		line-height: 1.5;
		color: var(--color-text);
		margin-top: 0.75rem;
	}
	.nb-nota.aviso { background: rgba(245, 158, 11, 0.14); }
	.nb-nota p { margin: 0; }

	/* ── Botones ───────────────────────────────────────────────────────────── */
	.nb-btn-grande { min-height: 52px; font-size: 1rem; }
	button.btn-block + button.btn-block { margin-top: 0.6rem; }

	.nb-help {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		line-height: 1.5;
		margin-top: 0.9rem;
	}

	/* ── Qué llega ─────────────────────────────────────────────────────────── */
	.nb-que { margin-top: 1.25rem; }
	.nb-que h2 { font-size: 0.95rem; margin: 0 0 0.75rem; }
	.nb-que ul { list-style: none; margin: 0 0 0.85rem; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
	.nb-que li { font-size: 0.85rem; line-height: 1.45; }
	.nb-que-nota {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		margin: 0;
		padding-top: 0.75rem;
		border-top: 1px solid rgba(255, 255, 255, 0.08);
		line-height: 1.5;
	}
</style>