<script>
	import { onMount } from 'svelte';
	import { api, isNetworkError } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import ActionsBar from '../components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let firmas = $state([]);
	let cuentas = $state([]);
	let cargando = $state(true);
	let error = $state('');
	let editando = $state(null);          // id de la firma en edición, o null
	let nombre = $state('');
	let cuerpo = $state('');
	let predeterminada = $state(false);
	let guardando = $state(false);

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
			const [f, c] = await Promise.all([
				api.get('/mailbox/firmas'),
				api.get('/mailbox/cuentas')
			]);
			firmas = Array.isArray(f) ? f : [];
			cuentas = Array.isArray(c) ? c : [];
		} catch (e) {
			error = isNetworkError(e)
				? 'Sin conexión.'
				: (e.message || 'No se pudieron cargar tus firmas.');
		} finally {
			cargando = false;
		}
	}

	function nueva() {
		editando = 'nueva';
		nombre = '';
		cuerpo = '';
		predeterminada = firmas.length === 0;
	}

	function editar(f) {
		editando = f.id;
		nombre = f.nombre;
		cuerpo = f.html || '';
		predeterminada = !!f.predeterminada;
	}

	function cancelar() {
		editando = null;
	}

	/**
	 * Guarda la firma.
	 *
	 * El `html` se manda TAL CUAL: el sanitizado es del servidor, no del
	 * cliente. Un sanitizado en el navegador se puede saltar por la consola, y
	 * esta firma se inyecta en el HTML de los correos que salen de la empresa.
	 * Ver api/main.py::_sanitizar_html.
	 */
	async function guardar() {
		if (!nombre.trim()) {
			avisar('Ponle un nombre a la firma', 'error');
			return;
		}
		guardando = true;
		try {
			const cuerpoReq = {
				nombre: nombre.trim(),
				html: cuerpo,
				predeterminada
			};
			if (editando === 'nueva') {
				await api.post('/mailbox/firmas', cuerpoReq);
			} else {
				await api.put(`/mailbox/firmas/${editando}`, cuerpoReq);
			}
			avisar('Firma guardada', 'success');
			editando = null;
			await cargar();
		} catch (e) {
			avisar(e.message || 'No se pudo guardar', 'error');
		} finally {
			guardando = false;
		}
	}

	async function borrar(f) {
		if (!confirm(`¿Borrar la firma "${f.nombre}"?`)) return;
		try {
			await api.delete(`/mailbox/firmas/${f.id}`);
			avisar('Firma borrada', 'info');
			await cargar();
		} catch (e) {
			avisar(e.message || 'No se pudo borrar', 'error');
		}
	}

	async function alternarPredeterminada(f) {
		try {
			await api.put(`/mailbox/firmas/${f.id}`, {
				nombre: f.nombre,
				html: f.html,
				predeterminada: !f.predeterminada
			});
			await cargar();
		} catch (e) {
			avisar(e.message || 'No se pudo cambiar', 'error');
		}
	}

	/** Cuántas cuentas tienen asignada esta firma. */
	function cuentasDe(f) {
		return (f.cuentas || []).length;
	}
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<button class="back-btn" onclick={() => navigate('/')} title="Volver">←</button>
			<h1 class="brand">Firmas</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	{#if error}
		<div class="fb-alert">
			<span>{error}</span>
			<button class="btn btn-sm btn-secondary" onclick={cargar}>Reintentar</button>
		</div>
	{/if}

	{#if editando}
		<!-- ── Editor ─────────────────────────────────────────────────────
		     En la fase 4 este textarea se reemplaza por el editor rico con
		     inserción de imágenes (ver AGENTS.md §Firmas). Va deliberadamente
		     como HTML a la vista: el usuario tiene que poder ver el código que
		     se va a guardar, y la vista previa se valida al vuelo contra el
		     MISMO sanitizador que usa el servidor, que se expone en
		     POST /mailbox/firmas/previsualizar. -->
		<div class="card fb-editor">
			<h2>{editando === 'nueva' ? 'Nueva firma' : 'Editar firma'}</h2>

			<div class="field">
				<label for="fb-nombre">Nombre</label>
				<input id="fb-nombre" class="input" type="text" bind:value={nombre}
				       placeholder="Formal, Comercial, Clientes…" maxlength="60" />
			</div>

			<div class="field">
				<label for="fb-cuerpo">Contenido (HTML)</label>
				<textarea id="fb-cuerpo" class="input fb-html" bind:value={cuerpo} rows="10"
				          placeholder="&lt;p&gt;Saludos,&lt;/p&gt;&lt;p&gt;&lt;b&gt;Tu nombre&lt;/b&gt;&lt;/p&gt;"></textarea>
				<p class="fb-pista">
					Se permite HTML con estilos en línea: tablas, colores, imágenes por
					<code>cid:</code>. El servidor descarta las etiquetas que no estén
					en la lista blanca.
				</p>
			</div>

			<label class="fb-check">
				<input type="checkbox" bind:checked={predeterminada} />
				<span>Usar esta firma por defecto</span>
			</label>

			<div class="fb-acciones">
				<button class="btn btn-primary" onclick={guardar} disabled={guardando}>
					{guardando ? 'Guardando…' : '💾 Guardar'}
				</button>
				<button class="btn btn-secondary" onclick={cancelar}>Cancelar</button>
			</div>
		</div>
	{:else if cargando}
		<div class="empty">Cargando…</div>
	{:else if firmas.length === 0}
		<div class="card fb-vacio">
			<div class="fb-vacio-icon">✍️</div>
			<h2>Todavía no tienes firmas</h2>
			<p>
				Una firma es el bloque de texto y logo que se agrega al final de cada
				correo que envías. Puedes tener varias y aplicar cada una a distintas
				cuentas.
			</p>
			<button class="btn btn-primary" onclick={nueva}>✍️ Crear mi primera firma</button>
		</div>
	{:else}
		<div class="list">
			{#each firmas as f (f.id)}
				<div class="card fb-firma">
					<div class="fb-firma-head">
						<div>
							<strong>{f.nombre}</strong>
							{#if f.predeterminada}<span class="badge badge-success">Por defecto</span>{/if}
						</div>
						<div class="fb-firma-acc">
							<button class="btn btn-sm btn-secondary" onclick={() => editar(f)}>Editar</button>
							<button class="btn btn-sm btn-danger" onclick={() => borrar(f)}>Borrar</button>
						</div>
					</div>

					<!-- Vista previa. El iframe va con sandbox="" (sin
					     allow-scripts) por lo mismo que el visor de correos: es HTML
					     escrito por el usuario y no puede ejecutar nada. -->
					<div class="fb-preview">
						<iframe title="Vista previa de la firma" sandbox=""
						        srcdoc={f.html || '<p style="color:#94A3B8">(firma vacía)</p>'}
						        style="height:110px"></iframe>
					</div>

					<div class="fb-firma-pie">
						<span class="fb-cuentas">
							📬 {cuentasDe(f)} {cuentasDe(f) === 1 ? 'cuenta' : 'cuentas'}
						</span>
						<label class="fb-check fb-check--inline">
							<input type="checkbox" checked={f.predeterminada}
							       onchange={() => alternarPredeterminada(f)} />
							<span>Predeterminada</span>
						</label>
					</div>
				</div>
			{/each}
		</div>

		<button class="btn btn-primary btn-block fb-nueva" onclick={nueva}>＋ Nueva firma</button>
	{/if}
</div>

<style>
	.brand-col { display: flex; align-items: center; gap: 0.75rem; }
	.brand { font-size: 1.2rem; margin: 0; }

	.fb-alert {
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

	/* ── Editor ───────────────────────────────────────────────────────────── */
	.fb-editor h2 { font-size: 1rem; margin: 0 0 1rem; }
	.fb-html { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.8rem; }
	.fb-pista { font-size: 0.75rem; color: var(--color-text-muted); margin: 0.4rem 0 0; line-height: 1.45; }
	.fb-pista code {
		background: var(--color-surface-2);
		padding: 0.05rem 0.25rem;
		border-radius: 4px;
		font-size: 0.72rem;
	}
	.fb-check { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; cursor: pointer; }
	.fb-check--inline { font-size: 0.78rem; color: var(--color-text-muted); }
	.fb-acciones { display: flex; gap: 0.6rem; margin-top: 1rem; }

	/* ── Lista ────────────────────────────────────────────────────────────── */
	.fb-firma { margin-bottom: 0.9rem; }
	.fb-firma-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-bottom: 0.85rem;
	}
	.fb-firma-head strong { font-size: 0.95rem; }
	.fb-firma-head .badge { margin-left: 0.5rem; }
	.fb-firma-acc { display: flex; gap: 0.4rem; }

	.fb-preview {
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: var(--radius-sm);
		overflow: hidden;
		background: #fff;
	}
	.fb-preview iframe { width: 100%; border: 0; display: block; }

	.fb-firma-pie {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-top: 0.85rem;
	}
	.fb-cuentas { font-size: 0.78rem; color: var(--color-text-muted); }

	.fb-nueva { margin-top: 0.5rem; }

	/* ── Vacío ────────────────────────────────────────────────────────────── */
	.fb-vacio { text-align: center; padding: 2rem 1.25rem; }
	.fb-vacio-icon { font-size: 3rem; margin-bottom: 0.75rem; }
	.fb-vacio h2 { font-size: 1rem; margin: 0 0 0.5rem; }
	.fb-vacio p { font-size: 0.85rem; color: var(--color-text-muted); margin: 0 0 1.25rem; line-height: 1.5; }
</style>