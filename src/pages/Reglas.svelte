<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import ActionsBar from '../components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let reglas = $state([]);
	let respuestas = $state([]);
	let editando = $state(null);
	let guardando = $state(false);
	let tab = $state('reglas');

	// ── Campos y operadores disponibles ───────────────────────────────────────
	// Las listas mandan: si acá queda un valor que el backend no acepta, el POST
	// vuelve 400 y el usuario ve un error sin sentido.
	const CAMPOS = [
		{ id: 'FROM', label: 'Remitente' },
		{ id: 'TO', label: 'Destinatario' },
		{ id: 'SUBJECT', label: 'Asunto' },
		{ id: 'BODY', label: 'Contenido' },
		{ id: 'DOMINIO', label: 'Dominio del remitente' }
	];
	const OPERADORES = [
		{ id: 'CONTIENE', label: 'contiene' },
		{ id: 'IGUAL', label: 'es exactamente' },
		{ id: 'EMPIEZA', label: 'empieza con' },
		{ id: 'TERMINA', label: 'termina con' },
		{ id: 'REGEX', label: 'expresión regular' }
	];
	const ACCIONES = [
		{ id: 'MARCAR_LEIDO', label: 'Marcar como leído', icono: '👁️' },
		{ id: 'ETIQUETAR', label: 'Etiquetar', icono: '🏷️' },
		{ id: 'ARCHIVAR', label: 'Archivar', icono: '🗄️' },
		{ id: 'ELIMINAR', label: 'Mover a papelera', icono: '🗑️' },
		{ id: 'NO_HACER', label: 'No hacer nada (documentada)', icono: '⏸️' }
	];

	function nueva() {
		editando = {
			id: null, prioridad: (reglas.length + 1) * 10,
			campo: 'FROM', operador: 'CONTIENE', valor: '',
			accion: 'MARCAR_LEIDO', etiqueta: '', activa: true
		};
	}
	function editar(r) { editando = { ...r }; }
	function cancelar() { editando = null; }

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		await cargar();
	});

	async function cargar() {
		try {
			const [r, a] = await Promise.all([
				api.get('/mailbox/reglas'),
				api.get('/mailbox/respuestas-automaticas')
			]);
			reglas = r || [];
			respuestas = a.respuestas || [];
		} catch (e) {
			avisar(e.message || 'No se pudieron cargar', 'error');
		}
	}

	async function guardar() {
		guardando = true;
		try {
			const cuerpo = {
				prioridad: editando.prioridad,
				campo: editando.campo,
				operador: editando.operador,
				valor: editando.valor,
				accion: editando.accion,
				etiqueta: editando.etiqueta,
				activa: editando.activa
			};
			if (editando.id) await api.put(`/mailbox/reglas/${editando.id}`, cuerpo);
			else await api.post('/mailbox/reglas', cuerpo);
			avisar('Regla guardada', 'success');
			editando = null;
			await cargar();
		} catch (e) {
			avisar(e.message || 'No se pudo guardar', 'error', 6000);
		} finally {
			guardando = false;
		}
	}

	async function borrar(r) {
		if (!confirm('¿Borrar esta regla?')) return;
		try {
			await api.delete(`/mailbox/reglas/${r.id}`);
			await cargar();
		} catch (e) {
			avisar(e.message || 'No se pudo borrar', 'error');
		}
	}

	async function alternar(r) {
		try {
			await api.put(`/mailbox/reglas/${r.id}`, { ...r, activa: !r.activa });
			await cargar();
		} catch (e) {
			avisar(e.message || 'No se pudo cambiar', 'error');
		}
	}

	function etiquetaDe(id) {
		return ACCIONES.find((a) => a.id === id) || { label: id, icono: '•' };
	}
	function campoDe(id) {
		return CAMPOS.find((c) => c.id === id)?.label || id;
	}
	function operadorDe(id) {
		return OPERADORES.find((o) => o.id === id)?.label || id;
	}

	let necesitaEtiqueta = $derived(editando?.accion === 'ETIQUETAR');
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<button class="back-btn" onclick={() => navigate('/')} title="Volver">←</button>
			<h1 class="brand">Reglas</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	<div class="rl-tabs">
		<button class="rl-tab" class:active={tab === 'reglas'} onclick={() => tab = 'reglas'}>
			📐 Reglas
		</button>
		<button class="rl-tab" class:active={tab === 'auto'} onclick={() => tab = 'auto'}>
			💤 Respuestas automáticas
		</button>
	</div>

	{#if tab === 'reglas'}
		{#if editando}
			<div class="card rl-editor">
				<h2>{editando.id ? 'Editar regla' : 'Nueva regla'}</h2>

				<div class="field">
					<label for="rl-prioridad">Orden</label>
					<input id="rl-prioridad" class="input" type="number" bind:value={editando.prioridad}
					       min="1" max="999" />
					<p class="rl-pista">Menor número = se revisa antes. La primera que coincide gana.</p>
				</div>

				<div class="field">
					<label for="rl-campo">Buscar en</label>
					<select id="rl-campo" class="input" bind:value={editando.campo}>
						{#each CAMPOS as c}<option value={c.id}>{c.label}</option>{/each}
					</select>
				</div>

				<div class="field">
					<label for="rl-operador">Condición</label>
					<select id="rl-operador" class="input" bind:value={editando.operador}>
						{#each OPERADORES as o}<option value={o.id}>{o.label}</option>{/each}
					</select>
					<input class="input rl-valor" type="text" bind:value={editando.valor}
					       placeholder={editando.operador === 'REGEX' ? 'ej: ^Factura \\d{4}' : 'ej: noreply@'} />
				</div>

				<div class="field">
					<label for="rl-accion">Hacer</label>
					<select id="rl-accion" class="input" bind:value={editando.accion}>
						{#each ACCIONES as a}<option value={a.id}>{a.icono} {a.label}</option>{/each}
					</select>
				</div>

				{#if necesitaEtiqueta}
					<div class="field">
						<label for="rl-etiqueta">Etiqueta</label>
						<input id="rl-etiqueta" class="input" type="text" bind:value={editando.etiqueta}
						       placeholder="Proveedores" maxlength="60" />
					</div>
				{/if}

				<label class="rl-check">
					<input type="checkbox" bind:checked={editando.activa} />
					<span>Regla activa</span>
				</label>

				<div class="rl-acciones">
					<button class="btn btn-primary" onclick={guardar} disabled={guardando}>
						{guardando ? 'Guardando…' : '💾 Guardar'}
					</button>
					<button class="btn btn-secondary" onclick={cancelar}>Cancelar</button>
				</div>
			</div>
		{:else if reglas.length === 0}
			<div class="card rl-vacio">
				<div class="rl-vacio-icon">📐</div>
				<h2>Sin reglas todavía</h2>
				<p>
					Las reglas se aplican al sincronizar: cuando entra un correo que
					coincide, el worker lo marca, etiqueta o archiva solo.
				</p>
				<button class="btn btn-primary" onclick={nueva}>＋ Crear la primera regla</button>
			</div>
		{:else}
			<div class="list">
				{#each reglas as r (r.id)}
					<div class="card rl-fila" class:inactiva={!r.activa}>
						<div class="rl-fila-top">
							<span class="rl-accion-icono">{etiquetaDe(r.accion).icono}</span>
							<div class="rl-fila-txt">
								<strong>
									Si {campoDe(r.campo).toLowerCase()} {operadorDe(r.operador)}
									<em>"{r.valor}"</em>
								</strong>
								<span>→ {etiquetaDe(r.accion).label}{r.etiqueta ? `: ${r.etiqueta}` : ''}</span>
							</div>
							<label class="rl-switch">
								<input type="checkbox" checked={r.activa} onchange={() => alternar(r)} />
								<span></span>
							</label>
						</div>
						<div class="rl-fila-pie">
							<span class="rl-orden">orden {r.prioridad}</span>
							{#if r.veces_ejecutada > 0}
								<span class="rl-veces">se aplicó {r.veces_ejecutada}×</span>
							{/if}
							<span class="rl-fila-spacer"></span>
							<button class="btn btn-sm btn-secondary" onclick={() => editar(r)}>Editar</button>
							<button class="btn btn-sm btn-danger" onclick={() => borrar(r)}>Borrar</button>
						</div>
					</div>
				{/each}
			</div>
			<button class="btn btn-primary btn-block rl-nueva" onclick={nueva}>＋ Nueva regla</button>
		{/if}
	{:else}
		{#if respuestas.length === 0}
			<div class="card rl-vacio">
				<div class="rl-vacio-icon">💤</div>
				<h2>Sin respuestas automáticas</h2>
				<p>
					Se usan cuando un correo llega a un buzón que no tiene a nadie
					atendiendo, por ejemplo un permiso o una incapacitated.
				</p>
				<a class="btn btn-primary" href="/firmas">Configurar desde Firmas</a>
			</div>
		{:else}
			<div class="list">
				{#each respuestas as a (a.id)}
					<div class="card rl-fila">
						<div class="rl-fila-top">
							<span class="rl-accion-icono">💤</span>
							<div class="rl-fila-txt">
								<strong>{a.es_default ? 'Respuesta por defecto' : 'Respuesta automática'}</strong>
								<span>
									{#if a.solo_fuera_horario}Solo fuera de horario · {/if}
									{#if a.excepciones_dominio}excepto {a.excepciones_dominio}{/if}
								</span>
							</div>
						</div>
						<div class="rl-firma-preview">
							<iframe title="Respuesta automática" sandbox="" srcdoc={a.mensaje} style="height:90px"></iframe>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<style>
	.brand-col { display: flex; align-items: center; gap: 0.75rem; }
	.brand { font-size: 1.2rem; margin: 0; }

	/* ── Pestañas ──────────────────────────────────────────────────────────── */
	.rl-tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
	.rl-tab {
		flex: 1; padding: 0.55rem 0.5rem;
		border-radius: var(--radius-xs);
		background: var(--color-surface);
		border: 1px solid rgba(255,255,255,0.05);
		color: var(--color-text-muted);
		font-size: 0.8rem; font-weight: 600; font-family: inherit;
		cursor: pointer; transition: all 0.15s;
	}
	.rl-tab.active {
		background: rgba(255,107,0,0.12);
		color: var(--color-primary);
		border-color: rgba(255,107,0,0.3);
	}

	/* ── Editor ────────────────────────────────────────────────────────────── */
	.rl-editor h2 { font-size: 1rem; margin: 0 0 1rem; }
	.rl-valor { margin-top: 0.4rem; }
	.rl-pista { font-size: 0.72rem; color: var(--color-text-muted); margin: 0.35rem 0 0; }
	.rl-check { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; cursor: pointer; }
	.rl-acciones { display: flex; gap: 0.6rem; margin-top: 1rem; }

	/* ── Filas ─────────────────────────────────────────────────────────────── */
	.rl-fila { margin-bottom: 0.7rem; }
	.rl-fila.inactiva { opacity: 0.5; }
	.rl-fila-top { display: flex; align-items: flex-start; gap: 0.6rem; }
	.rl-accion-icono { font-size: 1.15rem; flex: 0 0 auto; }
	.rl-fila-txt { flex: 1; min-width: 0; font-size: 0.83rem; line-height: 1.45; }
	.rl-fila-txt span { display: block; color: var(--color-text-muted); font-size: 0.78rem; }
	.rl-fila-txt em { color: var(--color-primary-light); font-style: normal; }

	/* Interruptor. El <input> real queda escondido y el span dibuja el botón:
	   un checkbox pelado en iOS se ve diminuto y es difícil de tocar. */
	.rl-switch { position: relative; flex: 0 0 auto; }
	.rl-switch input { position: absolute; opacity: 0; width: 44px; height: 26px; margin: 0; }
	.rl-switch span {
		display: block; width: 44px; height: 26px;
		border-radius: 999px; background: var(--color-surface-2);
		transition: background 0.2s; pointer-events: none;
	}
	.rl-switch span::after {
		content: ''; position: absolute; top: 3px; left: 3px;
		width: 20px; height: 20px; border-radius: 50%;
		background: var(--color-text); transition: transform 0.2s;
	}
	.rl-switch input:checked + span { background: var(--color-success); }
	.rl-switch input:checked + span::after { transform: translateX(18px); }

	.rl-fila-pie {
		display: flex; align-items: center; gap: 0.6rem;
		margin-top: 0.7rem; padding-top: 0.6rem;
		border-top: 1px solid rgba(255,255,255,0.06);
		font-size: 0.72rem; color: var(--color-text-muted);
	}
	.rl-fila-spacer { flex: 1; }

	.rl-firma-preview {
		margin-top: 0.6rem; border: 1px solid rgba(255,255,255,0.08);
		border-radius: var(--radius-sm); overflow: hidden; background: #fff;
	}
	.rl-firma-preview iframe { width: 100%; border: 0; display: block; }

	.rl-nueva { margin-top: 0.5rem; }

	.rl-vacio { text-align: center; padding: 2rem 1.25rem; }
	.rl-vacio-icon { font-size: 3rem; margin-bottom: 0.75rem; }
	.rl-vacio h2 { font-size: 1rem; margin: 0 0 0.5rem; }
	.rl-vacio p { font-size: 0.85rem; color: var(--color-text-muted); margin: 0 0 1.25rem; line-height: 1.5; }
	.rl-vacio a { text-decoration: none; }
</style>