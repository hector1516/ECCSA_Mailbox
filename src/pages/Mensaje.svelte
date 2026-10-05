<script>
	import { onMount } from 'svelte';
	import { api, descargar, isNetworkError } from '$lib/api.js';
	import { auth } from '$lib/stores/auth.js';
	import { avisar } from '$lib/stores/toasts.js';
	import { navigate } from '$lib/router.js';
	import ActionsBar from '../components/ActionsBar.svelte';

	let { mensajeId = 0, onSalir = null } = $props();

	let msg = $state(null);
	let html = $state('');
	let cargando = $state(true);
	let error = $state('');
	let cuerpoError = $state('');
	/** false = imágenes remotas bloqueadas (default). true = el usuario las pidió. */
	let permitirRemotas = $state(false);
	let descargando = $state(0);

	/**
	 * CSP dentro del iframe.
	 *
	 * Es la forma DECLARATIVA de bloquear el contenido remoto de un correo: no
	 * hay que reescribir el HTML con regex (que siempre deja algo pasar).
	 *
	 * · `default-src 'none'`  → nada se carga salvo lo que se Allows explícitamente
	 * · `img-src 'self' data:` → solo imágenes del propio servidor (las inline cid)
	 * · `style-src 'unsafe-inline'` → el HTML de correo trae estilos en línea y
	 *   sin esto el correo se vería sin ningún formato
	 * · `script-src 'none'`  → aunque se colara un <script>, no ejecuta
	 *
	 * El `sandbox=""` del iframe ya prohíbe scripts; la CSP es la segunda capa.
	 * Las dos juntas: el sandbox cubre el resto (formularios, popups, navegación).
	 */
	const CSP_BLOQUEADO = [
		"default-src 'none'",
		"img-src 'self' data:",
		"style-src 'unsafe-inline'",
		"script-src 'none'",
		"frame-src 'none'",
		"form-action 'none'",
		"base-uri 'none'"
	].join('; ');

	const CSP_PERMITIDO = [
		"default-src 'none'",
		"img-src 'self' data: http: https:",
		"style-src 'unsafe-inline'",
		"script-src 'none'",
		"frame-src 'none'",
		"form-action 'none'",
		"base-uri 'none'"
	].join('; ');

	function _srcdoc(contenido, csp) {
		const meta = `<meta http-equiv="Content-Security-Policy" content="${csp}">`;
		// base-uri 'none' + <base> ausente: sin un <base>, un href relativo en el
		// correo no puede resolver contra la ruta del api y salir a otro dominio.
		return meta + (contenido || '<p style="color:#94A3B8;font-family:sans-serif">(sin contenido)</p>');
	}

	let srcdoc = $derived(_srcdoc(html, permitirRemotas ? CSP_PERMITIDO : CSP_BLOQUEADO));
	let altoIframe = $state(420);

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
	 cuerpoError = '';
		try {
			msg = await api.get(`/mailbox/mensajes/${mensajeId}`);
			// Abrir un mensaje lo marca como leído. Es una operación optimista: la
			// app escribe en la cola y el worker la aplica en IMAP. El estado local
			// ya quedó en Visto=1, así que no hay que esperar nada.
			if (msg && !msg.visto) {
				api.post(`/mailbox/mensajes/${mensajeId}/operacion`, { operacion: 'seen', valor: '1' })
					.catch(() => {});
				msg.visto = true;
			}
			try {
				const r = await api.get(`/mailbox/mensajes/${mensajeId}/cuerpo`);
				html = r.html || '';
			} catch (e) {
				// El cuerpo puede faltar por retención (410) o por descarga pendiente
				// (404). Son estados distintos y cada uno se explica distinto.
				cuerpoError = e.message || 'El contenido todavía no está disponible';
				html = '';
			}
		} catch (e) {
			error = isNetworkError(e) ? 'Sin conexión.' : (e.message || 'No se pudo abrir el mensaje');
		} finally {
			cargando = false;
		}
	}

	async function operacion(op, valor = '') {
		try {
			await api.post(`/mailbox/mensajes/${mensajeId}/operacion`, { operacion: op, valor });
			if (op === 'seen') msg.visto = valor !== '0';
			if (op === 'flag') msg.marcado = valor !== '0';
			if (op === 'delete') { avisar('Marcado para borrar', 'info'); navigate('/'); return; }
		} catch (e) {
			avisar(e.message || 'No se pudo aplicar', 'error');
		}
	}

	/**
	 * Descarga un adjunto AL DISPOSITIVO.
	 *
	 * Se baja como blob y se dispara un `<a download>`. La alternativa —un
	 * <a href> directo— no funciona dentro de una PWA en iPhone: Safari abre el
	 * PDF en el visor en vez de guardarlo en Archivos.
	 */
	async function bajar(a) {
		descargando = a.id;
		try {
			const resp = await descargar(`/mailbox/adjuntos/${a.id}/descargar`);
			const blob = await resp.blob();
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = a.nombre || 'adjunto';
			document.body.appendChild(link);
			link.click();
			link.remove();
			// El revoke inmediato cancela la descarga en algunos navegadores de
			// escritorio. Se espera un poco antes de liberar la URL.
			setTimeout(() => URL.revokeObjectURL(url), 30000);
			avisar(`${a.nombre} descargado`, 'success');
		} catch (e) {
			avisar(e.message || 'No se pudo descargar', 'error', 6000);
		} finally {
			descargando = 0;
		}
	}

	function responder() {
		const asunto = (msg.asunto || '');
		sessionStorage.setItem('mailbox_borrador', JSON.stringify({
			para: msg.remitente_email || '',
			asunto: /^re:/i.test(asunto) ? asunto : `Re: ${asunto}`,
			cuerpo: `<br><br><blockquote>El ${msg.fecha}, ${msg.remitente_nombre || msg.remitente_email} escribió:</blockquote>`
		}));
		navigate(`/redactar?cuenta=${msg.cuenta.id}`);
	}

	function tamano(bytes) {
		if (!bytes) return '';
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
		return `${(bytes / 1048576).toFixed(1)} MB`;
	}

	/** Clave de iCloud/Mail que se abre con la app del sistema, no en el visor. */
	const ICONO_POR_TIPO = {
		'application/pdf': '📕', 'image/png': '🖼️', 'image/jpeg': '🖼️',
		'image/gif': '🖼️', 'image/webp': '🖼️',
		'application/zip': '🗜️', 'application/msword': '📄',
		'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '📄',
		'application/vnd.ms-excel': '📊',
		'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '📊',
	};
	function icono(t) {
		if (!t) return '📎';
		if (ICONO_POR_TIPO[t]) return ICONO_POR_TIPO[t];
		if (t.startsWith('image/')) return '🖼️';
		if (t.startsWith('text/')) return '📄';
		if (t.includes('pdf')) return '📕';
		return '📎';
	}

	let remitenteInicial = $derived(
		(msg?.remitente_nombre || msg?.remitente_email || '?').trim().charAt(0).toUpperCase()
	);

	/**
	 * Ajusta el alto del iframe al del contenido.
	 *
	 * Sin esto el iframe queda con el alto por defecto y un correo largo se corta
	 * con scroll interno, lo que en iPhone hace un doble scroll (el de la página
	 * y el del iframe) y se siente roto.
	 */
	function _ajustarAlto(e) {
		try {
			const doc = e.target.contentDocument;
			if (!doc || !doc.body) return;
			const alto = doc.body.scrollHeight + 24;
			// Se acota: un correo con una tabla gigante no debe comerse la pantalla
			// ni el tamaño del iframe (que se pinta en el DOM).
			altoIframe = Math.min(Math.max(alto, 200), 4000);
		} catch (e) {
			/* con sandbox="" el contentDocument es accessible solo en mismo origen */
		}
	}
</script>

<div class="page">
	<div class="header">
		<div class="brand-col">
			<button class="back-btn" onclick={() => navigate('/')} title="Volver">←</button>
			<h1 class="brand">Mensaje</h1>
		</div>
		<ActionsBar onlogout={onSalir} />
	</div>

	{#if cargando}
		<div class="empty">Abriendo…</div>
	{:else if error}
		<div class="cb-alert"><span>{error}</span>
			<button class="btn btn-sm btn-secondary" onclick={cargar}>Reintentar</button>
		</div>
	{:else if msg}
		<!-- ── Encabezado del mensaje ──────────────────────────────────── -->
		<div class="card mv-cab">
			<div class="mv-remitente">
				<div class="mv-avatar">{remitenteInicial}</div>
				<div class="mv-quien">
					<strong>{msg.remitente_nombre || msg.remitente_email}</strong>
					{#if msg.remitente_nombre && msg.remitente_email}
						<span class="mv-mail">{msg.remitente_email}</span>
					{/if}
					<span class="mv-fecha">📨 {msg.cuenta.alias || msg.cuenta.email} · {msg.fecha}</span>
				</div>
				<button class="mv-estrella" class:on={msg.marcado}
				        onclick={() => operacion('flag', msg.marcado ? '0' : '1')}
				        title={msg.marcado ? 'Quitar destacado' : 'Destacar'}>
					{msg.marcado ? '★' : '☆'}
				</button>
			</div>

			<h2 class="mv-asunto">{msg.asunto || '(sin asunto)'}</h2>

			<div class="mv-rutas">
				{#if msg.para}<div><b>Para:</b> {msg.para}</div>{/if}
				{#if msg.cc}<div><b>Cc:</b> {msg.cc}</div>{/if}
			</div>
		</div>

		<!-- ── Adjuntos ───────────────────────────────────────────────────
		     Se listan SIEMPRE aunque no se descarguen: el manifiesto está en
		     el índice y no requiere IMAP. El byte llega recién cuando el
		     usuario aprieta. -->
		{#if msg.adjuntos && msg.adjuntos.length > 0}
			<div class="mv-adjuntos">
				<div class="mv-adjuntos-titulo">
					📎 {msg.adjuntos.length} {msg.adjuntos.length === 1 ? 'adjunto' : 'adjuntos'}
					<span class="mv-adjuntos-nota">
						se descargan a tu dispositivo, no se guardan en el servidor
					</span>
				</div>
				{#each msg.adjuntos as a (a.id)}
					{#if !a.es_inline}
						<button class="mv-adj" onclick={() => bajar(a)} disabled={descargando === a.id}>
							<span class="mv-adj-icono">{icono(a.content_type)}</span>
							<span class="mv-adj-nombre">{a.nombre}</span>
							<span class="mv-adj-size">{tamano(a.size)}</span>
							<span class="mv-adj-accion">
								{descargando === a.id ? '…' : '⬇︎'}
							</span>
						</button>
					{/if}
				{/each}
			</div>
		{/if}

		<!-- ── Cuerpo ─────────────────────────────────────────────────────
		     El iframe es la medida de seguridad: sin `allow-scripts` el HTML
		     del remitente no puede ejecutar nada, ni hacer `top.location`, ni
		     abrir popups. La CSP de adentro agrega el bloqueo de lo remoto. -->
		{#if cuerpoError}
			<div class="mv-cuerpo-error">
				<p>{cuerpoError}</p>
				<p class="mv-cuerpo-error-nota">
					El encabezado de arriba sigue disponible y el mensaje se puede buscar
					por remitente, asunto y fecha.
				</p>
			</div>
		{:else}
			<div class="mv-cuerpo">
				<iframe
					title="Contenido del correo"
					sandbox=""
					{srcdoc}
					style="height:{altoIframe}px"
					onload={_ajustarAlto}
				></iframe>
			</div>

			{#if !permitirRemotas}
				<div class="mv-imgs">
					<span>🛡️</span>
					<p>
						Las imágenes y los links externos están bloqueados. Al permitirlos,
						quien te mandó el correo ve que abriste el mensaje.
					</p>
					<button class="btn btn-sm btn-secondary" onclick={() => permitirRemotas = true}>
						Cargar imágenes
					</button>
				</div>
			{/if}
		{/if}

		<div class="mv-acciones">
			<!-- Responder lleva los datos por session_state, no por query: meter
			     un correo en la URL lo pondría en el historial del navegador y en
			     los logs del proxy. -->
			<button class="btn btn-secondary" onclick={responder}>
				↩️ Responder
			</button>
			<button class="btn btn-secondary" onclick={() => operacion('delete')}>
				🗑️ Borrar
			</button>
		</div>
	{/if}
</div>

<style>
	.brand-col { display: flex; align-items: center; gap: 0.75rem; }
	.brand { font-size: 1.1rem; margin: 0; }

	/* ── Encabezado ──────────────────────────────────────────────────────── */
	.mv-cab { margin-bottom: 0.9rem; }
	.mv-remitente { display: flex; align-items: center; gap: 0.75rem; }
	.mv-avatar {
		width: 40px; height: 40px; flex: 0 0 auto;
		border-radius: 50%;
		background: var(--color-surface-2);
		color: var(--color-text);
		display: flex; align-items: center; justify-content: center;
		font-weight: 700; font-size: 1.05rem;
	}
	.mv-quien { flex: 1; min-width: 0; display: flex; flex-direction: column; }
	.mv-quien strong { font-size: 0.92rem; }
	.mv-mail, .mv-fecha {
		font-size: 0.72rem; color: var(--color-text-muted);
		white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
	}
	.mv-estrella {
		background: none; border: none; cursor: pointer;
		font-size: 1.5rem; color: var(--color-text-muted);
		line-height: 1; padding: 0.25rem; flex: 0 0 auto;
	}
	.mv-estrella.on { color: var(--color-warning); }

	.mv-asunto { font-size: 1.05rem; margin: 0.85rem 0 0.5rem; line-height: 1.35; }
	.mv-rutas {
		font-size: 0.75rem; color: var(--color-text-muted);
		line-height: 1.5; word-break: break-word;
	}
	.mv-rutas b { color: var(--color-text); }

	/* ── Adjuntos ────────────────────────────────────────────────────────── */
	.mv-adjuntos {
		background: var(--color-surface);
		border: 1px solid rgba(255,255,255,0.05);
		border-radius: var(--radius);
		padding: 0.85rem;
		margin-bottom: 0.9rem;
	}
	.mv-adjuntos-titulo {
		font-size: 0.82rem; font-weight: 600; margin-bottom: 0.6rem;
		display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: baseline;
	}
	.mv-adjuntos-nota {
		font-size: 0.7rem; font-weight: 400; color: var(--color-text-muted);
	}
	.mv-adj {
		display: flex; align-items: center; gap: 0.6rem;
		width: 100%; text-align: left;
		padding: 0.55rem 0.5rem; margin-bottom: 0.3rem;
		background: var(--color-bg);
		border: 1px solid rgba(255,255,255,0.06);
		border-radius: var(--radius-sm);
		color: var(--color-text); font-family: inherit;
		font-size: 0.82rem; cursor: pointer;
		transition: background 0.15s;
	}
	.mv-adj:active { background: var(--color-surface-2); }
	.mv-adj:disabled { opacity: 0.5; cursor: progress; }
	.mv-adj-icono { font-size: 1.15rem; flex: 0 0 auto; }
	.mv-adj-nombre {
		flex: 1; min-width: 0;
		white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
	}
	.mv-adj-size { font-size: 0.7rem; color: var(--color-text-muted); flex: 0 0 auto; }
	.mv-adj-accion { font-size: 1rem; flex: 0 0 auto; color: var(--color-primary); }

	/* ── Cuerpo ──────────────────────────────────────────────────────────── */
	/* Fondo BLANCO a propósito: el correo trae sus propios colores y sobre el
	   oscuro del tema los textos negros se pierden. El borde separa el "correo"
	   del "app". */
	.mv-cuerpo {
		background: #fff;
		border-radius: var(--radius);
		overflow: hidden;
		border: 1px solid rgba(255,255,255,0.08);
	}
	.mv-cuerpo iframe { width: 100%; border: 0; display: block; }

	.mv-cuerpo-error {
		background: var(--color-surface);
		border: 1px solid rgba(245,158,11,0.25);
		border-radius: var(--radius);
		padding: 1rem;
		font-size: 0.85rem;
	}
	.mv-cuerpo-error p { margin: 0; }
	.mv-cuerpo-error-nota {
		margin-top: 0.5rem !important;
		font-size: 0.75rem; color: var(--color-text-muted); line-height: 1.5;
	}

	.mv-imgs {
		display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
		margin-top: 0.75rem; padding: 0.75rem 0.85rem;
		background: rgba(59,130,246,0.10);
		border-radius: var(--radius-sm);
		font-size: 0.78rem;
	}
	.mv-imgs p { margin: 0; flex: 1; min-width: 180px; line-height: 1.45; }

	.mv-acciones { display: flex; gap: 0.6rem; margin-top: 1rem; }
	.mv-acciones .btn { flex: 1; }
</style>