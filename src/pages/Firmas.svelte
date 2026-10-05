<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import ActionsBar from '../components/ActionsBar.svelte';

	let { onSalir = null } = $props();

	let firmas = $state([]);
	let cuentas = $state([]);
	let editando = $state(null);
	let nombre = $state('');
	let html = $state('');
	let predeterminada = $state(false);
	let cuentasSel = $state([]);
	let guardando = $state(false);
	let previsualizacion = $state('');
	let cargando = $state(true);

	onMount(async () => {
		if (!auth.isLoggedIn()) {
			navigate('/login', { replace: true });
			return;
		}
		await cargar();
	});

	async function cargar() {
		cargando = true;
		try {
			const [f, c] = await Promise.all([
				api.get('/mailbox/firmas'),
				api.get('/mailbox/cuentas')
			]);
			firmas = f || [];
			cuentas = c || [];
		} catch (e) {
			avisar(e.message || 'No se pudieron cargar', 'error');
		} finally {
			cargando = false;
		}
	}

	// ── Editor ────────────────────────────────────────────────────────────────

	function nueva() {
		editando = 'nueva';
		nombre = '';
		html = '';
		predeterminada = firmas.length === 0;
		cuentasSel = [];
		previsualizacion = '';
	}

	function editar(f) {
		editando = f.id;
		nombre = f.nombre;
		html = f.html || '';
		predeterminada = f.predeterminada;
		cuentasSel = [...(f.cuentas || [])];
		previsualizacion = f.html || '';
	}

	function cancelar() {
		editando = null;
	}

	/**
	 * execCommand está obsoleto pero sigue siendo lo único que funciona igual en
	 * todos los navegadores para editar en un contenteditable CON historial de
	 * undo. Un contentEditable propio con rangos de selección es mucho más
	 * código y peor en Safari, que es donde más se usa esta app.
	 */
	function _cmd(comando, valor = null) {
		document.execCommand(comando, false, valor);
		html = document.getElementById('fb-editor')?.innerHTML || html;
		_refrescarPrevia();
		// Sin preventDefault del undo: execCommand ya registra el paso.
	}

	function _refrescarPrevia() {
		html = document.getElementById('fb-editor')?.innerHTML || html;
		// La previsualización se pide al SERVIDOR, no se arma acá. Motivo: el
		// cliente no tiene la lista blanca, y si la duplicara se desincronizaría
		// del servidor. Lo que se ve es exactamente lo que se va a guardar.
		debouncePrevia(html);
	}

	// El preview va al servidor. Con cada tecla sería un request por pulsación,
	// así que se espera a que pare de escribir.
	let _t = null;
	function debouncePrevia(texto) {
		clearTimeout(_t);
		_t = setTimeout(async () => {
			try {
				const r = await api.post('/mailbox/firmas/previsualizar', { html: texto });
				previsualizacion = r.html || '';
			} catch {
				previsualizacion = texto;
			}
		}, 450);
	}

	function _insertar(trozo) {
		document.execCommand('insertHTML', false, trozo);
		_refrescarPrevia();
	}

	/** Imagen del logo de ECCSA, ya insertada como cid:. */
	function _insertarLogo() {
		_insertar('<img src="cid:logo@eccsa" alt="ECCSA" height="60" style="display:block;margin:0 0 10px">');
	}

	/** Separador horizontal, que es lo más pedido en una firma. */
	function _separador() {
		_insertar('<hr style="border:none;border-top:1px solid #ddd;margin:12px 0">');
	}

	/** Tabla de 2 columnas: la que se usa para logo + datos. */
	function _tabla() {
		_insertar(
			'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse">' +
			'<tr><td style="padding-right:16px;vertical-align:top"><img src="cid:logo@eccsa" alt="Logo" height="52"></td>' +
			'<td style="vertical-align:top"><strong style="color:#0F172A">Nombre Apellido</strong><br>' +
			'<span style="color:#64748B;font-size:12px">Puesto · Área</span><br>' +
			'<span style="color:#64748B;font-size:12px">telefono · correo@ecc-sa.com.mx</span></td>' +
			'</tr></table><br>'
		);
	}

	function _enlace() {
		const url = prompt('¿A qué dirección?');
		if (!url) return;
		// El sanitizador del servidor igual valida el esquema; esto es solo para
		// no insertar algo que va a ser Tirado a la basura.
		if (!/^(https?:|mailto:|\/)/i.test(url)) {
			avisar('Solo links http, https o mailto', 'warning');
			return;
		}
		_insertar(`<a href="${url}">${url}</a>&nbsp;`);
	}

	async function _subirImagen(e) {
		const archivo = e.target.files?.[0];
		e.target.value = '';
		if (!archivo) return;
		if (!editando || editando === 'nueva') {
			avisar('Guarda la firma primero y después agrega la imagen', 'warning');
			return;
		}
		try {
			const fd = new FormData();
			fd.append('archivo', archivo);
			const r = await api.post(`/mailbox/firmas/${editando}/imagenes`, fd);
			// En la vista previa va la URL; el HTML GUARDADO lleva cid:.
			_insertar(`<img src="${r.url}" alt="${r.html.match(/alt="([^"]*)"/)?.[1] || 'imagen'}" style="max-width:100%">`);
			avisar('Imagen agregada', 'success');
		} catch (err) {
			avisar(err.message || 'No se pudo subir la imagen', 'error', 6000);
		}
	}

	// ── Guardar ──────────────────────────────────────────────────────────────
	async function guardar() {
		if (!nombre.trim()) {
			avisar('Ponle un nombre a la firma', 'warning');
			return;
		}
		guardando = true;
		try {
			const contenido = document.getElementById('fb-editor')?.innerHTML || html;
			const cuerpo = { nombre: nombre.trim(), html: contenido, predeterminada };
			let id;
			if (editando === 'nueva') {
				const r = await api.post('/mailbox/firmas', cuerpo);
				id = r.id;
			} else {
				await api.put(`/mailbox/firmas/${editando}`, cuerpo);
				id = editando;
			}
			await api.put(`/mailbox/firmas/${id}/cuentas`, { cuentas: cuentasSel });
			avisar('Firma guardada', 'success');
			editando = null;
			await cargar();
		} catch (e) {
			avisar(e.message || 'No se pudo guardar', 'error', 6000);
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
				nombre: f.nombre, html: f.html, predeterminada: !f.predeterminada
			});
			await cargar();
		} catch (e) {
			avisar(e.message || 'No se pudo cambiar', 'error');
		}
	}

	function alternarCuenta(id) {
		document.getElementById('fb-cuentas')?.click();
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

	{#if editando}
		<!-- ── Editor ──────────────────────────────────────────────────────── -->
		<div class="card fb-editor">
			<div class="field">
				<label for="fb-nombre">Nombre de la firma</label>
				<input id="fb-nombre" class="input" type="text" bind:value={nombre}
				       placeholder="Formal, Comercial, Clientes…" maxlength="60" />
				<p class="fb-pista">Es para que la identifiques tú; no aparece en el correo.</p>
			</div>

			<!-- Barra de formato. execCommand sobre el contenteditable. -->
			<div class="fb-toolbar" role="toolbar" aria-label="Formato">
				<button class="fb-tb" title="Negritas" onclick={() => _cmd('bold')}><b>N</b></button>
				<button class="fb-tb" title="Cursivas" onclick={() => _cmd('italic')}><i>C</i></button>
				<button class="fb-tb" title="Subrayado" onclick={() => _cmd('underline')}><u>S</u></button>
				<span class="fb-tb-sep"></span>
				<select class="fb-tb-select" title="Color" onchange={(e) => _cmd('foreColor', e.target.value)}>
					<option value="">Color…</option>
					<option value="#0F172A">Negro</option>
					<option value="#FF6B00">Naranja ECCSA</option>
					<option value="#3B82F6">Azul</option>
					<option value="#22C55E">Verde</option>
					<option value="#EF4444">Rojo</option>
					<option value="#64748B">Gris</option>
				</select>
				<select class="fb-tb-select" title="Tamaño" onchange={(e) => _cmd('fontSize', e.target.value)}>
					<option value="">Tamaño…</option>
					<option value="2">Chico</option>
					<option value="3">Normal</option>
					<option value="5">Grande</option>
					<option value="7">Muy grande</option>
				</select>
				<select class="fb-tb-select" title="Alineación" onchange={(e) => _cmd('justify' + e.target.value)}>
					<option value="">Alinear…</option>
					<option value="Left">Izquierda</option>
					<option value="Center">Centro</option>
					<option value="Right">Derecha</option>
				</select>
				<span class="fb-tb-sep"></span>
				<button class="fb-tb fb-tb-txt" title="Separador" onclick={_separador}>— ✕ —</button>
				<button class="fb-tb fb-tb-txt" title="Logo de ECCSA" onclick={_insertarLogo}>🖼 Logo</button>
				<button class="fb-tb fb-tb-txt" title="Tabla logo + datos" onclick={_tabla}>▦ Tabla</button>
				<button class="fb-tb fb-tb-txt" title="Enlace" onclick={_enlace}>🔗</button>
				<label class="fb-tb fb-tb-txt" title="Subir imagen">
					📎 Imagen
					<input type="file" accept="image/png,image/jpeg,image/gif,image/webp"
					       onchange={_subirImagen} hidden />
				</label>
			</div>

			<div class="fb-editor-area" role="textbox" aria-multiline="true" contenteditable="true"
			     id="fb-editor" oninput={_refrescarPrevia}>{@html html}</div>

			<div class="fb-doble">
				<div>
					<div class="fb-label">Vista previa <span>(lo que se va a guardar)</span></div>
					<div class="fb-preview">
						<iframe title="Vista previa de la firma" sandbox=""
						        srcdoc={previsualizacion || '<p style="color:#94A3B8;font-family:sans-serif">(escribe algo)</p>'}
						        style="height:130px"></iframe>
					</div>
				</div>
				<div>
					<div class="fb-label">En el correo <span>(con la firma ya aplicada)</span></div>
					<div class="fb-preview">
						<iframe title="Así se verá" sandbox=""
						        srcdoc={'<div style="font-family:Arial,sans-serif;font-size:13px;color:#0F172A;padding:2px">' +
						        '<p>Buen día,</p><hr>' +
						        (previsualizacion || '<span style="color:#94A3B8">(la firma)</span>') + '</div>'}
						        style="height:130px"></iframe>
					</div>
				</div>
			</div>

			<div class="field fb-cuentas-campo">
				<label>En qué cuentas se aplica</label>
				{#if cuentas.length === 0}
					<p class="fb-pista">Todavía no tienes cuentas asignadas.</p>
				{:else}
					<div class="fb-cuentas">
						{#each cuentas as c (c.id)}
							<label class="fb-cuenta">
								<input type="checkbox" checked={cuentasSel.includes(c.id)}
								       onchange={() => {
										cuentasSel = cuentasSel.includes(c.id)
											? cuentasSel.filter((x) => x !== c.id)
											: [...cuentasSel, c.id];
								   }} />
								<span class="fb-cuenta-icono">{c.icono || '📬'}</span>
								<span class="fb-cuenta-nombre">{c.alias || c.email}</span>
							</label>
						{/each}
					</div>
				{/if}
				<p class="fb-pista">
					Si no marcas ninguna, la firma se aplica igual a las cuentas que no
					tengan otra asignada.
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
			<h2>Crea tu primera firma</h2>
			<p>
				Es el bloque que se pega al final de cada correo que envías. Puedes
				usar colores, tablas, tu logo y separadores, y aplicar una firma a
				unas cuentas y otra a las demás.
			</p>
			<button class="btn btn-primary" onclick={nueva}>✍️ Crear firma</button>
		</div>
	{:else}
		<div class="list">
			{#each firmas as f (f.id)}
				<div class="card fb-firma">
					<div class="fb-firma-head">
						<div class="fb-firma-tit">
							<strong>{f.nombre}</strong>
							{#if f.predeterminada}<span class="badge badge-success">Por defecto</span>{/if}
							<span class="fb-cuentas-n">
								📬 {(f.cuentas || []).length === 0
									? 'todas sin firma propia'
									: `${(f.cuentas || []).length} ${(f.cuentas || []).length === 1 ? 'cuenta' : 'cuentas'}`}
							</span>
						</div>
						<div class="fb-firma-acc">
							<button class="btn btn-sm btn-secondary" onclick={() => editar(f)}>Editar</button>
							<button class="btn btn-sm btn-danger" onclick={() => borrar(f)}>Borrar</button>
						</div>
					</div>

					<div class="fb-preview">
						<iframe title="Vista previa de la firma" sandbox=""
						        srcdoc={f.html || '<p style="color:#94A3B8;font-family:sans-serif">(firma vacía)</p>'}
						        style="height:110px"></iframe>
					</div>

					<label class="fb-check fb-check--inline">
						<input type="checkbox" checked={f.predeterminada}
						       onchange={() => alternarPredeterminada(f)} />
						<span>Firma predeterminada</span>
					</label>
				</div>
			{/each}
		</div>

		<button class="btn btn-primary btn-block fb-nueva" onclick={nueva}>＋ Nueva firma</button>
	{/if}
</div>

<style>
	.brand-col { display: flex; align-items: center; gap: 0.75rem; }
	.brand { font-size: 1.2rem; margin: 0; }

	/* ── Toolbar ───────────────────────────────────────────────────────────── */
	/* Se hace scroll en vez de envolver: en 360 px de ancho una barra de 10
	   botones con wrap ocupa tres filas y empuja el editor fuera de pantalla. */
	.fb-toolbar {
		display: flex; align-items: center; gap: 0.25rem;
		overflow-x: auto; -webkit-overflow-scrolling: touch;
		padding-bottom: 0.5rem; margin-bottom: 0.5rem;
		border-bottom: 1px solid rgba(255,255,255,0.08);
	}
	.fb-tb {
		flex: 0 0 auto;
		min-width: 34px; height: 34px; padding: 0 0.5rem;
		background: var(--color-bg);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: var(--radius-xs);
		color: var(--color-text); font-size: 0.85rem;
		cursor: pointer; font-family: inherit;
		display: inline-flex; align-items: center; justify-content: center;
		transition: background 0.15s;
	}
	.fb-tb:active { background: var(--color-surface-2); }
	.fb-tb-txt { font-size: 0.78rem; }
	.fb-tb-sep { flex: 0 0 auto; width: 1px; height: 22px; background: rgba(255,255,255,0.1); margin: 0 0.25rem; }
	.fb-tb-select {
		flex: 0 0 auto; height: 34px;
		background: var(--color-bg);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: var(--radius-xs);
		color: var(--color-text); font-size: 0.78rem;
		padding: 0 0.35rem; font-family: inherit;
	}

	/* ── Área de edición ───────────────────────────────────────────────────── */
	.fb-editor-area {
		min-height: 190px;
		padding: 0.75rem 0.9rem;
		background: #fff;
		color: #0F172A;
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: var(--radius-sm);
		font-family: Arial, 'Helvetica Neue', sans-serif;
		font-size: 0.9rem;
		line-height: 1.5;
		outline: none;
		overflow-y: auto;
	}
	.fb-editor-area:focus { border-color: var(--color-primary); }
	/* Los emails se leen en clientes de correo, no en navegadores: la fuente
	   por defecto (Outfit) no la tiene casi ninguno. Arial es la que está en
	   todos. */
	/* :global() porque la imagen la mete execCommand en runtime y el
	   compilador de Svelte no la ve: sin esto avisa de selector muerto. */
	.fb-editor-area :global(img) { max-width: 100%; }

	/* ── Previews ──────────────────────────────────────────────────────────── */
	.fb-doble { display: grid; grid-template-columns: 1fr; gap: 0.85rem; margin-top: 0.9rem; }
	@media (min-width: 700px) { .fb-doble { grid-template-columns: 1fr 1fr; } }
	.fb-label { font-size: 0.75rem; color: var(--color-text-muted); margin-bottom: 0.35rem; }
	.fb-label span { opacity: 0.7; }
	.fb-preview {
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: var(--radius-sm);
		overflow: hidden; background: #fff;
	}
	.fb-preview iframe { width: 100%; border: 0; display: block; }

	/* ── Cuentas ───────────────────────────────────────────────────────────── */
	.fb-cuentas-campo { margin-top: 1rem; }
	.fb-cuentas { display: flex; flex-direction: column; gap: 0.35rem; }
	.fb-cuenta {
		display: flex; align-items: center; gap: 0.5rem;
		padding: 0.5rem 0.6rem;
		background: var(--color-bg);
		border: 1px solid rgba(255,255,255,0.06);
		border-radius: var(--radius-sm);
		font-size: 0.83rem; cursor: pointer;
	}
	.fb-cuenta-icono { font-size: 1rem; }
	.fb-cuenta-nombre { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

	.fb-pista { font-size: 0.72rem; color: var(--color-text-muted); margin: 0.35rem 0 0; line-height: 1.45; }
	.fb-check { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; cursor: pointer; margin-top: 0.85rem; }
	.fb-check--inline { margin-top: 0.85rem; font-size: 0.78rem; color: var(--color-text-muted); }
	.fb-acciones { display: flex; gap: 0.6rem; margin-top: 1rem; }

	/* ── Lista ─────────────────────────────────────────────────────────────── */
	.fb-firma { margin-bottom: 0.9rem; }
	.fb-firma-head {
		display: flex; align-items: center; justify-content: space-between;
		gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.85rem;
	}
	.fb-firma-tit { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
	.fb-firma-tit strong { font-size: 0.95rem; }
	.fb-firma-acc { display: flex; gap: 0.4rem; }
	.fb-cuentas-n { font-size: 0.72rem; color: var(--color-text-muted); }

	.fb-nueva { margin-top: 0.5rem; }

	.fb-vacio { text-align: center; padding: 2rem 1.25rem; }
	.fb-vacio-icon { font-size: 3rem; margin-bottom: 0.75rem; }
	.fb-vacio h2 { font-size: 1rem; margin: 0 0 0.5rem; }
	.fb-vacio p { font-size: 0.85rem; color: var(--color-text-muted); margin: 0 0 1.25rem; line-height: 1.5; }
</style>