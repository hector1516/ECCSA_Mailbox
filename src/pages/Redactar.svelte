<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import ActionsBar from '../components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let cuentas = $state([]);
	let cuentaId = $state(0);
	let para = $state('');
	let cc = $state('');
	let bcc = $state('');
	let asunto = $state('');
	let cuerpo = $state('');
	let firmas = $state([]);
	let idFirma = $state(0);
	let enviando = $state(false);

	// Firma por defecto: la predeterminada del usuario, o la primera asignada a
	// la cuenta elegida. Se recalcula al cambiar de cuenta porque una cuenta
	// puede tener una firma propia.
	let firmaEfectiva = $derived(
		(idFirma ? firmas.find((f) => f.id === idFirma)
		         : firmas.find((f) => (f.cuentas || []).includes(cuentaId)) || firmas.find((f) => f.predeterminada))
		|| null
	);

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		try {
			cuentas = await api.get('/mailbox/cuentas');
			if (cuentas.length === 0) {
				avisar('No tienes cuentas asignadas', 'error');
				navigate('/');
				return;
			}
			// Viene de "Responder": sessionStorage y no la URL, para no dejar el
			// correo del destinatario en el historial del navegador.
			const borr = sessionStorage.getItem('mailbox_borrador');
			if (borr) {
				try {
					const d = JSON.parse(borr);
					para = d.para || '';
					asunto = d.asunto || '';
					cuerpo = d.cuerpo || '';
				} catch { /* borrador corrupto: se sigue con uno vacío */ }
				sessionStorage.removeItem('mailbox_borrador');
			}
			// El ?cuenta= viene de "Responder", que ya sabe de qué cuenta es.
			const q = new URLSearchParams(window.location.search).get('cuenta');
			cuentaId = (q && cuentas.some((c) => c.id === Number(q))) ? Number(q) : cuentas[0].id;
			firmas = await api.get('/mailbox/firmas');
		} catch (e) {
			avisar(e.message || 'No se pudo cargar', 'error');
		}
	});

	/**
	 * Inserta HTML en el cuerpo con el cursor en el lugar correcto.
	 *
	 * `execCommand('insertHTML')` está obsoleto pero sigue siendo lo único que
	 * funciona en todos los navegadores para insertar en un contenteditable sin
	 * perder el historial del undo. Un contentEditable propio con rangos es
	 * mucho más código y peor en Safari.
	 */
	function _insertar(html) {
		document.execCommand('insertHTML', false, html);
		cuerpo = document.getElementById('mb-cuerpo')?.innerHTML || cuerpo;
	}

	async function _subirImagen(e) {
		const archivo = e.target.files?.[0];
		e.target.value = '';
		if (!archivo) return;

		// Si no hay firma guardada todavía, la imagen necesita una firma a la que
		// pertenecer: la tabla HUB_MailboxFirmaImagenes cuelga de una firma.
		if (!firmas.length) {
			avisar('Primero crea una firma', 'warning');
			return;
		}
		let destino = idFirma || (firmas.find((f) => f.predeterminada) || firmas[0])?.id;
		if (!destino) destino = firmas[0].id;

		try {
			const fd = new FormData();
			fd.append('archivo', archivo);
			const r = await api.post(`/mailbox/firmas/${destino}/imagenes`, fd);
			// En la vista previa el src se cambia a la URL; al enviar, el worker
			// lo cambia a cid:. Por eso el HTML guardado siempre lleva cid:.
			_insertar(`<img src="${r.url}" alt="${(r.html.match(/alt="([^"]*)"/) || [, 'imagen'])[1]}" style="max-width:100%">`);
			avisar('Imagen insertada', 'success');
		} catch (err) {
			avisar(err.message || 'No se pudo subir la imagen', 'error');
		}
	}

	function _pedirFirma() {
		document.getElementById('mb-firma-check')?.click();
	}

	async function enviar() {
		if (!para.trim()) {
			avisar('Pon al menos un destinatario', 'warning');
			return;
		}
		enviando = true;
		try {
			const r = await api.post('/mailbox/enviar', {
				id_cuenta: cuentaId,
				para, cc, bcc,
				asunto,
				// El contenteditable guarda HTML; el texto plano se arma de ese mismo
				// HTML para no mandar un cuerpo vacío a quien no lo pinte.
				cuerpo,
				id_firma: idFirma || (firmaEfectiva ? firmaEfectiva.id : 0)
			});
			avisar(`Correo enviado (sigue la firma ${firmaEfectiva?.nombre || 'predeterminada'})`, 'success');
			navigate(`/cuenta/${cuentaId}`);
		} catch (e) {
			avisar(e.message || 'No se pudo encolar el envío', 'error', 6000);
		} finally {
			enviando = false;
		}
	}

	let hayFirma = $derived(!!firmaEfectiva);
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<button class="back-btn" onclick={() => navigate('/')} title="Volver">←</button>
			<h1 class="brand">Redactar</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	<div class="card rd-card">
		<div class="field">
			<label for="rd-cuenta">Desde</label>
			<select id="rd-cuenta" class="input" bind:value={cuentaId}>
				{#each cuentas as c (c.id)}
					<option value={c.id}>{c.icono || '📬'} {c.alias || c.email}</option>
				{/each}
			</select>
		</div>

		<div class="field">
			<label for="rd-para">Para</label>
			<input id="rd-para" class="input" type="text" bind:value={para}
			       placeholder="nombre@empresa.com, otra@empresa.com" autocapitalize="none" />
		</div>

		<div class="field">
			<label for="rd-cc">Cc / Bcc <span class="rd-opcional">(opcional)</span></label>
			<input id="rd-cc" class="input" type="text" bind:value={cc} placeholder="Cc" autocapitalize="none" />
			<input id="rd-bcc" class="input rd-bcc" type="text" bind:value={bcc} placeholder="Bcc" autocapitalize="none" />
		</div>

		<div class="field">
			<label for="rd-asunto">Asunto</label>
			<input id="rd-asunto" class="input" type="text" bind:value={asunto} placeholder="¿De qué se trata?" />
		</div>

		<!-- ── Cuerpo ──────────────────────────────────────────────────────
		     contenteditable + innerHTML. El HTML va al servidor y ahí se
		     sanitiza con la lista blanca de firma, así que lo que se escriba
		     acá no puede inyectar nada al correo que salga. -->
		<div class="field">
			<label for="mb-cuerpo">Mensaje</label>
			<div class="rd-editor" role="textbox" aria-multiline="true" contenteditable="true"
			     id="mb-cuerpo" bind:innerHTML={cuerpo}
			     data-placeholder="Escribe aquí tu mensaje…"></div>
		</div>

		<!-- ── Firma ─────────────────────────────────────────────────────
		     La firma se aplica AL ENVIAR, no se pega en el cuerpo: así el
		     usuario edita sin pisar la firma y se puede cambiar sin reescribir. -->
		<div class="rd-firma">
			<div class="rd-firma-head">
				<span class="rd-firma-label">✍️ Firma</span>
				<button class="btn btn-sm btn-secondary" onclick={_pedirFirma}>Cambiar</button>
			</div>
			{#if hayFirma}
				<label class="rd-check">
					<input type="checkbox" id="mb-firma-check" bind:checked={firmaEfectiva}
					       onchange={() => idFirma = firmaEfectiva ? firmaEfectiva.id : 0} />
					<span>Aplicar <strong>{firmaEfectiva.nombre}</strong> a este correo</span>
				</label>
				<div class="rd-firma-preview">
					<iframe title="Firma" sandbox="" srcdoc={firmaEfectiva.html} style="height:74px"></iframe>
				</div>
			{:else}
				<p class="rd-sin-firma">
					No hay ninguna firma. <a href="/firmas">Crea una</a>.
				</p>
			{/if}
		</div>

		<div class="rd-acciones">
			<button class="btn btn-primary" onclick={enviar} disabled={enviando || !para.trim()}>
				{enviando ? 'Encolando…' : '📤 Enviar'}
			</button>
			<button class="btn btn-secondary" onclick={() => navigate('/')}>Cancelar</button>
		</div>

		<p class="rd-nota">
			Enviar encola el correo; sale en el siguiente ciclo del worker (unos
			segundos). La firma queda guardada con el correo enviado, así que
			editarla después no cambia lo que ya mandaste.
		</p>
	</div>
</div>

<style>
	.brand-col { display: flex; align-items: center; gap: 0.75rem; }
	.brand { font-size: 1.2rem; margin: 0; }

	.rd-card { margin-bottom: 1rem; }
	.rd-opcional { font-weight: 400; opacity: 0.65; font-size: 0.78rem; }
	.rd-bcc { margin-top: 0.4rem; }

	/* El editor es un contenteditable, así que NO puede ser .input (que pone
	   font-size y color para un <input> real). Se le da lo mismo a mano. */
	.rd-editor {
		min-height: 180px;
		padding: 0.75rem 1rem;
		background: var(--color-bg);
		border: 1px solid var(--color-surface-2);
		border-radius: var(--radius-sm);
		color: var(--color-text);
		font-size: 1rem;
		font-family: inherit;
		line-height: 1.5;
		outline: none;
		overflow-y: auto;
	}
	.rd-editor:focus { border-color: var(--color-primary); }
	/* El placeholder de un contenteditable no se pone con `placeholder`: es un
	   pseudo-elemento sobre :empty. */
	.rd-editor:empty::before {
		content: attr(data-placeholder);
		color: var(--color-text-muted);
		opacity: 0.7;
	}

	.rd-firma {
		border-top: 1px solid rgba(255,255,255,0.08);
		padding-top: 0.85rem;
		margin-top: 0.35rem;
	}
	.rd-firma-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
	.rd-firma-label { font-size: 0.85rem; font-weight: 600; }
	.rd-check { display: flex; align-items: center; gap: 0.5rem; font-size: 0.83rem; cursor: pointer; }
	.rd-firma-preview {
		margin-top: 0.6rem;
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: var(--radius-sm);
		overflow: hidden;
		background: #fff;
	}
	.rd-firma-preview iframe { width: 100%; border: 0; display: block; }
	.rd-sin-firma { font-size: 0.8rem; color: var(--color-text-muted); margin: 0; }
	.rd-sin-firma a { color: var(--color-primary); }

	.rd-acciones { display: flex; gap: 0.6rem; margin-top: 1rem; }
	.rd-acciones .btn { flex: 1; }
	.rd-nota {
		font-size: 0.72rem; color: var(--color-text-muted);
		margin: 0.75rem 0 0; line-height: 1.5;
	}
</style>