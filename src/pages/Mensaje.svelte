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
	let mostrarMover = $state(false);
	let destinos = $state([]);
	let confirmar = $state('');
	let mostrarFiltro = $state(false);
	let filtro = $state(null);

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

	/**
	 * Los tres botones de respuesta arman el mismo borrador y lo pasan por
	 * sessionStorage, no por la URL. Va en sessionStorage y no en query string
	 * por una razón concreta: las direcciones de los destinatarios NO deben
	 * quedar en el historial del navegador ni en el log del servidor. Con
	 * `?para=...` el correo de un cliente queda escrito en la barra de
	 * direcciones y en cualquier historial o captura de pantalla.
	 *
	 * `Redactar.svelte` lo consume y lo borra de inmediato (una vez), así que
	 * un correo no sensible queda en memoria solo mientras se redacta.
	 */
	const ETIQUETAS = {
		INBOX: { label: 'Entrada', icon: '📥' },
		Sent: { label: 'Enviados', icon: '📤' },
	};
	function etiquetaCarpeta(id) {
		return ETIQUETAS[id] || { label: id, icon: '📁' };
	}

	function _borrador(d) {
		sessionStorage.setItem('mailbox_borrador', JSON.stringify(d));
		navigate(`/redactar?cuenta=${msg.cuenta.id}`);
	}

	// Cita en HTML con el formato que el usuario espera de cualquier cliente de
	// correo. El `border-left` es lo que hace que la columna de texto se separe
	// del mensaje nuevo; sin él la cita se lee como parte de la respuesta.
	function _cita(texto, fecha, nombre) {
		return `<br><blockquote style="border-left:3px solid #ccc;padding-left:10px;margin-left:0;color:#555">` +
			`El ${fecha}, ${nombre} escribió:<br>${texto || ''}</blockquote>`;
	}

	function responder() {
		const asunto = (msg.asunto || '');
		const nombre = msg.remitente_nombre || msg.remitente_email || '';
		_borrador({
			para: msg.remitente_email || '',
			asunto: /^re:/i.test(asunto) ? asunto : `Re: ${asunto}`,
			cuerpo: _cita(msg.extracto || '', msg.fecha_correo || '', nombre)
		});
	}

	/**
	 * Saca direcciones de correo de un header.
	 *
	 * `para` y `cc` NO llegan como arreglo: llegan como el header crudo tal cual
	 * lo dejó el servidor, o sea una cadena tipo
	 * `"Juan Pérez" <juan@empresa.com>, maria@otra.com`. Recorrerla con un
	 * `for...of` it'd devuelve CADA CARÁCTER por separado, y el correo saldría
	 * con letras sueltas en el campo Para.
	 *
	 * Se usa una expresión regular en vez de partir por comas porque un nombre
	 * puede traer la coma DENTRO entre comillas:
	 * `"Pérez, Juan" <juan@x.com>`. Partir por coma rompe ese caso a la mitad.
	 */
	function _correos(header) {
		if (!header) return [];
		const sal = String(header).match(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/gi) || [];
		return sal.map((d) => d.toLowerCase());
	}

	/**
	 * Responder a todos.
	 *
	 * Lo difícil NO es poner a la gente en `para`, es NO volver a meter a este
	 * usuario. Si quien responde es una cuenta de la empresa (y lo son 12 de las
	 * 13 cuentas), incluirse a sí mismo produce un correo que vuelve a la misma
	 * casilla y reaparece en la lista de pendientes, para siempre. Por eso se
	 * comparan TODAS las direcciones contra la cuenta propia y se quitan, sin
	 * importar de qué campo vinieron.
	 *
	 * Los destinatarios que ya venían en CC no se promoted a Para: se dejan en
	 * CC. Cambiarlos de campo cambia la respuesta para todo el mundo.
	 */
	function responderATodos() {
		const asunto = (msg.asunto || '');
		const nombre = msg.remitente_nombre || msg.remitente_email || '';
		const propio = (msg.cuenta.email || '').toLowerCase();

		const para = [];
		const cc = [];
		const vistos = new Set();

		for (const d of _correos(msg.para)) {
			if (d === propio || vistos.has(d)) continue;
			vistos.add(d);
			para.push(d);
		}
		for (const d of _correos(msg.cc)) {
			if (d === propio || vistos.has(d)) continue;
			vistos.add(d);
			cc.push(d);
		}

		// Si no hay nadie más, es un "responder" normal.
		if (para.length === 0 && cc.length === 0) return responder();

		_borrador({
			para: para.join(', '),
			cc: cc.join(', '),
			asunto: /^re:/i.test(asunto) ? asunto : `Re: ${asunto}`,
			cuerpo: _cita(msg.extracto || '', msg.fecha_correo || '', nombre)
		});
	}

	function reenviar() {
		_borrador({
			para: '',
			asunto: (msg.asunto || '').startsWith('Fw:') ? msg.asunto : `Fw: ${msg.asunto || ''}`,
			cuerpo: `<br><br>---------- Correo reenviado ----------<br>` +
				`De: ${msg.remitente_nombre || ''} &lt;${msg.remitente_email || ''}&gt;<br>` +
				`Fecha: ${msg.fecha_correo || ''}<br>` +
				`Asunto: ${msg.asunto || ''}<br><br>${msg.extracto || ''}`
		});
	}

	/**
	 * Mover a carpeta. El movimiento REAL lo hace el worker con un IMAP COPY;
	 * la app solo encola la operación y actualiza la fila al instante, para
	 * que el correo salga de la carpeta actual sin esperar el ciclo del worker.
	 */
	function abrirMover() {
		mostrarMover = true;
		api.get(`/mailbox/cuentas/${msg.cuenta.id}/carpetas`)
			.then((r) => (destinos = (r.carpetas || []).filter((c) => c.id !== (msg.carpeta || ''))))
			.catch(() => (destinos = []));
	}

	/**
	 * Eliminar y spam pasan por CONFIRMACIÓN, y no es desconfianza del usuario:
	 * son las dos únicas acciones de esta pantalla que no se pueden deshacer.
	 *
	 * El `operacion('delete')` de antes movía el mensaje a la papelera sin
	 * preguntar, a un botón de la fila de acciones, a un dedo pegado al de
	 * "Responder". Un toque de más borraba un correo que no se puede recuperar
	 * porque la fila se marca `Eliminado=1` y la retención se la lleva.
	 *
	 * Spam además explica qué va a hacer a futuro, porque no es solo sobre este
	 * correo: crea una regla. Si el usuario cree que solo mueve el mensaje, la
	 * próxima vez que le llegue algo de ese remitente lo vera desaparecer sin
	 * saber por qué.
	 */
	async function confirmarEliminar() {
		confirmar = '';
		try {
			await api.post(`/mailbox/mensajes/${msg.id}/operacion`, { operacion: 'delete' });
			avisar('Mensaje eliminado.', 'success');
			navigate(`/cuenta/${msg.cuenta.id}`);
		} catch (e) {
			avisar(e.message || 'No se pudo eliminar', 'error');
		}
	}

	async function marcarSpam() {
		confirmar = '';
		try {
			const r = await api.post(`/mailbox/mensajes/${msg.id}/spam`, {});
			avisar(
				r.regla_creada
					? 'Marcado como spam. Los próximos correos de ese remitente también caerán en spam.'
					: 'Marcado como spam. Ya existía una regla para ese remitente.',
				'success'
			);
			navigate(`/cuenta/${msg.cuenta.id}`);
		} catch (e) {
			avisar(e.message || 'No se pudo marcar como spam', 'error');
		}
	}

	/**
	 * "Crear filtro" desde el mensaje abierto.
	 *
	 * Los valores vienen rellenos con lo que hay en ESTE correo, que es la
	 * gracia del atajo: no hay que escribir ni copiar nada. Se deja todo
	 * editable porque el 90% de los casos quiere ajustar el valor ("este remitente
	 * Y este asunto", "solo el dominio, no la dirección exacta").
	 *
	 * El campo por defecto es DOMINIO y no FROM a propósito: casi todo filtro que
	 * uno crea en la práctica es "todo lo que venga de este dominio", y
	 * `juan@empresa.com` no captura `facturacion@empresa.com`. Está preseleccionado
	 * pero se cambia en un clic.
	 */
	function abrirFiltro() {
		const remitente = msg.remitente_email || '';
		const dominio = remitente.includes('@') ? remitente.split('@').pop() : '';
		filtro = {
			campo: 'DOMINIO',
			operador: 'CONTIENE',
			valor: dominio,
			accion: 'MARCAR_LEIDO',
			etiqueta: ''
		};
		mostrarFiltro = true;
	}

	/** Cambia el campo y rellena el valor con lo de este mensaje. */
	function cambiarCampoFiltro(campo) {
		if (!filtro) return;
		filtro.campo = campo;
		const asunto = (msg.asunto || '').replace(/^((re|fwd|rv)\s*[:>]\s*)+/i, '').trim();
		if (campo === 'FROM') filtro.valor = msg.remitente_email || '';
		else if (campo === 'DOMINIO') filtro.valor = (msg.remitente_email || '').split('@').pop() || '';
		else if (campo === 'SUBJECT') filtro.valor = asunto || msg.asunto || '';
		else if (campo === 'TO') filtro.valor = (msg.para || '').slice(0, 120);
		else filtro.valor = '';   // BODY: no se rellena, el extracto no es el cuerpo
	}

	async function guardarFiltro() {
		if (!filtro || !filtro.valor.trim()) return;
		try {
			const r = await api.post(`/mailbox/mensajes/${msg.id}/filtro`, filtro);
			mostrarFiltro = false;
			avisar(
				r.creada
					? 'Filtro creado. Se aplica a los correos que lleguen de aquí en adelante.'
					: (r.detalle || 'El filtro ya existía'),
				r.creada ? 'success' : 'warning'
			);
			navigate(`/cuenta/${msg.cuenta.id}`);
		} catch (e) {
			avisar(e.message || 'No se pudo crear el filtro', 'error');
		}
	}

	async function moverA(destino) {
		mostrarMover = false;
		try {
			await api.post(`/mailbox/mensajes/${msg.id}/operacion`, { operacion: 'move', valor: destino });
			avisar(`Movido a «${destino}». El worker lo aplica en su próximo ciclo.`, 'success');
			navigate(`/cuenta/${msg.cuenta.id}`);
		} catch (e) {
			avisar(e.message || 'No se pudo mover', 'error');
		}
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

		<!--
			LAS ACCIONES VAN EN PARES DE DOS, NO EN UNA FILA.
			─────────────────────────────────────────────────
			Son siete botones. En una fila con `flex-wrap` cada uno mide lo que
			mide su texto y la fila se va de la pantalla en móvil: «Responder a
			todos» y «Marcar como spam» son largos y la última pareja se corta o
			deja un hueco enorme.

			El patrón es el del detalle de Cotizaciones Materiales de Admon:
			`.grid-2` con dos botones `btn-block` por fila, cada uno ocupando la
			mitad exacta. Se adapta a cualquier ancho sin `nowrap`, sin
			`overflow` y sin tener que elegir un punto de corte.

			La acción irreversible va sola y al final, como en Admon: separarla
			del resto es lo que evita el toque de más al lado de «Responder».
			No es una cuestión de jerarquía visual, es que el dedo no tiene que
			recorrer seis botones para llegar a la que borra.
		-->
		<div class="mv-acciones">
			<div class="grid-2">
				<button class="btn btn-secondary btn-block" onclick={responder}>
					↩️ Responder
				</button>
				<button class="btn btn-secondary btn-block" onclick={responderATodos}>
					↩️↩️ Responder a todos
				</button>
			</div>
			<div class="grid-2">
				<button class="btn btn-secondary btn-block" onclick={reenviar}>
					➜ Reenviar
				</button>
				<button class="btn btn-secondary btn-block" onclick={abrirMover}>
					📁 Mover
				</button>
			</div>
			<div class="grid-2">
				<button class="btn btn-secondary btn-block" onclick={() => (confirmar = 'spam')}>
					🚫 Spam
				</button>
				<button class="btn btn-secondary btn-block" onclick={abrirFiltro}>
					🎯 Crear filtro
				</button>
			</div>
			<div class="mv-acciones-solo">
				<button class="btn btn-secondary btn-block mv-peligro" onclick={() => (confirmar = 'borrar')}>
					🗑️ Eliminar mensaje
				</button>
			</div>
		</div>
	{/if}

	<!-- ══ Crear filtro desde este mensaje ═══════════════════════════════
	     Los valores vienen rellenos con lo de ESTE correo: es el atajo para no
	     escribir ni copiar. Todo queda editable porque casi siempre se quiere
	     ajustar (solo el dominio, otro campo, otra acción).
	     -->
	{#if mostrarFiltro && filtro && msg}
		<div class="mv-overlay" role="dialog" aria-label="Crear filtro">
			<div class="mv-modal mv-modal--ancha">
				<h2 class="mv-modal-titulo">🎯 Crear filtro</h2>
				<p class="mv-modal-nota">
					Se aplica a los correos que lleguen <b>de aquí en adelante</b>.
					Este mensaje no cambia: para moverlo ahora usa otra acción.
				</p>

				<div class="fl-fila">
					<label class="fl-label" for="fl-campo">Cuando el</label>
					<select id="fl-campo" class="input" value={filtro.campo}
						onchange={(e) => cambiarCampoFiltro(e.currentTarget.value)}>
						<option value="DOMINIO">Dominio del remitente</option>
						<option value="FROM">Remitente</option>
						<option value="SUBJECT">Asunto</option>
						<option value="TO">Destinatario</option>
						<option value="BODY">Contenido</option>
					</select>
				</div>

				<div class="fl-fila">
					<label class="fl-label" for="fl-op">sea</label>
					<select id="fl-op" class="input" bind:value={filtro.operador}>
						<option value="CONTIENE">contiene</option>
						<option value="IGUAL">es exactamente</option>
						<option value="EMPIEZA">empieza con</option>
						<option value="TERMINA">termina con</option>
						<option value="REGEX">expresión regular</option>
					</select>
				</div>

				<div class="fl-fila">
					<label class="fl-label" for="fl-valor">este valor</label>
					<input id="fl-valor" class="input" bind:value={filtro.valor} maxlength="500"
						placeholder="ej. newsletter@empresa.com" autocapitalize="none" />
				</div>

				<div class="fl-fila">
					<label class="fl-label" for="fl-accion">entonces</label>
					<select id="fl-accion" class="input" bind:value={filtro.accion}>
						<option value="MARCAR_LEIDO">👁️ Marcar como leído</option>
						<option value="SPAM">🚫 Marcar como spam</option>
						<option value="ARCHIVAR">🗄️ Archivar</option>
						<option value="ELIMINAR">🗑️ Mover a papelera</option>
						<option value="ETIQUETAR">🏷️ Etiquetar</option>
						<option value="NO_HACER">⏸️ No hacer nada (documentada)</option>
					</select>
				</div>

				{#if filtro.accion === 'ETIQUETAR'}
					<div class="fl-fila">
						<label class="fl-label" for="fl-etiq">con la etiqueta</label>
						<input id="fl-etiq" class="input" bind:value={filtro.etiqueta} maxlength="60"
							placeholder="ej. Newsletters" />
					</div>
				{/if}

				<div class="mv-modal-acciones">
					<button class="btn btn-secondary" onclick={() => (mostrarFiltro = false)}>Cancelar</button>
					<button class="btn btn-primary" onclick={guardarFiltro} disabled={!filtro.valor.trim()}>
						Crear filtro
					</button>
				</div>
			</div>
		</div>
	{/if}

	<!-- Confirmación de las dos acciones irreversibles. -->
	{#if confirmar && msg}
		<div class="mv-overlay" role="dialog" aria-label="Confirmar">
			<div class="mv-modal">
				{#if confirmar === 'spam'}
					<h2 class="mv-modal-titulo">🚫 ¿Marcar como spam?</h2>
					<p class="mv-modal-nota">
						Este correo se va a la carpeta de spam <b>y se crea una regla</b>:
						los próximos correos de
						<b>{msg.remitente_email || msg.remitente_nombre || 'este remitente'}</b>
						también caerán en spam solos. La regla se puede borrar en Reglas.
					</p>
					<div class="mv-modal-acciones">
						<button class="btn btn-secondary" onclick={() => (confirmar = '')}>Cancelar</button>
						<button class="btn btn-primary" onclick={marcarSpam}>Sí, marcar como spam</button>
					</div>
				{:else}
					<h2 class="mv-modal-titulo">🗑️ ¿Eliminar el mensaje?</h2>
					<p class="mv-modal-nota">
						Se mueve a la papelera del buzón <b>{msg.cuenta.email || ''}</b>.
						Si lo borras de ahí en tu cliente de correo, no hay forma de
						recuperarlo desde aquí.
					</p>
					<div class="mv-modal-acciones">
						<button class="btn btn-secondary" onclick={() => (confirmar = '')}>Cancelar</button>
						<button class="btn btn-danger mv-peligro" onclick={confirmarEliminar}>Sí, eliminar</button>
					</div>
				{/if}
			</div>
		</div>
	{/if}

	<!-- Mover a carpeta: la lista sale del índice y no de una constante, para
	     poder mover a una carpeta que el usuario acaba de crear. -->
	{#if mostrarMover && msg}
		<div class="mv-overlay" role="dialog" aria-label="Mover a carpeta">
			<div class="mv-modal">
				<h2 class="mv-modal-titulo">📁 Mover a carpeta</h2>
				<p class="mv-modal-nota">
					El movimiento real lo hace el worker en tu correo. Aquí se actualiza al
					instant para que no tengas que esperar.
				</p>
				{#if destinos.length === 0}
					<p class="mv-modal-vacia">No hay otras carpetas donde moverlo.</p>
				{:else}
					<ul class="mv-modal-lista">
						{#each destinos as d (d.id)}
							<li>
								<button class="mv-modal-item" onclick={() => moverA(d.id)}>
									<span>{etiquetaCarpeta(d.id).icon}</span>
									{etiquetaCarpeta(d.id).label}
									<span class="mv-modal-count">{d.total}</span>
								</button>
							</li>
						{/each}
					</ul>
				{/if}
				<button class="btn btn-secondary mv-modal-cerrar" onclick={() => (mostrarMover = false)}>
					Cerrar
				</button>
			</div>
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
	/* ── Fila de acciones ────────────────────────────────────────────────── */
	.mv-acciones {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-top: 1rem;
	}
	/* Un hueco más grande antes de la acción irreversible: separa el gesto
	   inocuo del que no tiene vuelta atrás. */
	.mv-acciones-solo { margin-top: 0.35rem; }
	/* En pantallas anchas, dos mitades de una fila a pantalla completa son
	   botones de 500 px con tres palabras dentro: se ve un menú, no una acción.

	   El tope de 34rem los deja con proporciones de botón. En Admon esto no
	   hace falta porque su detalle vive en una barra lateral angosta; aquí el
	   mensaje ocupa la pantalla entera, así que el límite hay que ponerlo.

	   `margin: 0 auto` los centra en vez de pegarlos a la izquierda, que es lo
	   que se vería con el ancho completo y el contenido a la derecha. */
	.mv-acciones .grid-2,
	.mv-acciones-solo {
		max-width: 34rem;
		width: 100%;
		margin-left: auto;
		margin-right: auto;
	}
	.mv-acciones .grid-2 .btn {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.85rem;
		padding: 0.55rem 0.5rem;
	}
	@media (max-width: 420px) {
		.mv-acciones .grid-2 .btn { font-size: 0.78rem; padding: 0.5rem 0.35rem; }
	}

	/* ── Modal "Mover a carpeta" ────────────────────────────────────────── */
	.mv-overlay {
		position: fixed;
		inset: 0;
		background: rgba(2, 6, 23, 0.72);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		z-index: 60;
	}
	.mv-modal {
		background: var(--color-surface);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-md);
		padding: 1.1rem;
		width: min(26rem, 100%);
		max-height: 80vh;
		overflow-y: auto;
	}
	.mv-modal-titulo { margin: 0 0 0.4rem; font-size: 1.05rem; }
	.mv-modal-nota { margin: 0 0 0.8rem; font-size: 0.78rem; color: var(--color-text-muted); }
	.mv-modal-vacia { font-size: 0.85rem; color: var(--color-text-muted); }
	.mv-modal-lista { list-style: none; margin: 0 0 0.9rem; padding: 0; }
	.mv-modal-item {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		width: 100%;
		text-align: left;
		background: transparent;
		border: 0;
		border-bottom: 1px solid var(--color-line);
		color: var(--color-text);
		padding: 0.6rem 0.25rem;
		font-size: 0.88rem;
		font-family: inherit;
		cursor: pointer;
	}
	.mv-modal-item:hover { background: rgba(255, 107, 0, 0.1); }
	.mv-modal-count { margin-left: auto; font-size: 0.75rem; color: var(--color-text-muted); }
	.mv-modal-acciones { display: flex; gap: 0.5rem; margin-top: 0.9rem; }
	.mv-modal-acciones .btn { flex: 1; }
	.mv-peligro { color: var(--color-danger); border-color: rgba(239, 68, 68, 0.4); }
	.mv-peligro:hover { background: rgba(239, 68, 68, 0.12) !important; }
	.mv-modal--ancha { width: min(32rem, 100%); }
	.mv-modal-cerrar { width: 100%; }

	/* ── Filtro ─────────────────────────────────────────────────────────── */
	.fl-fila {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin-bottom: 0.6rem;
		flex-wrap: wrap;
	}
	.fl-label {
		flex: 0 0 7.2rem;
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}
	.fl-fila .input { flex: 1 1 12rem; min-width: 0; }

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