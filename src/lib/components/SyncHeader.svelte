<script>
	/* ECCSA-Shell �� banner comǧn (referencia Svelte). ESTE ES EL EST�?NDAR.
	   ------------------------------------------------------------------
	   Banner universal: estado de sync + usuario + lugar + versi��n + botones
	   de navegaci��n (volver, config, novedades, salir). Todo en una sola
	   barra semitransparente con blur, compacta y notch-aware.

	   Reparto de responsabilidades:
	     �� El SHELL manda: este markup, los textos y el CSS �?" que vive en
	       src/body.css como `.sync-header`, NO en un <style> acǭ.
	     �� La APP manda: sus stores y los botones internos del m��dulo.

	   Props:
	     estado        'offline'|'syncing'|'error'|'pending'|'idle'
	     pendientes    number
	     usuario       string   ('' = sin sesi��n)
	     lugar         'oficina'|'remoto'|'desconocido'
	     ip            string
	     appVersion    string
	     shellVersion  string
	     endpoint      string   (default '/api/shell/state')
	     fetcher       (url) => Promise
	     onsync        () => any
	     titulo        string   (t��tulo de la pǭgina; '' = no se pinta)
	     onBack        () => any  (si se pasa, se pinta �?�)
	     onConfig      () => any  (si se pasa, se pinta �?�)
	     onLogout      () => any  (si se pasa, se pinta �Y-s�)
	     onChangelog   () => any  (si se pasa, se pinta �Y"�)
	     showBack      boolean (default false)
	*/
	let {
		estado = 'idle',
		pendientes = 0,
		usuario = '',
		lugar = null,
		ip = '',
		appVersion = '',
		shellVersion = '',
		endpoint = '/api/shell/state',
		fetcher = null,
		onsync = null,
		titulo = '',
		onBack = null,
		onConfig = null,
		onLogout = null,
		onChangelog = null,
		showBack = false
	} = $props();

	let lugarApi = $state('desconocido');
	let ipApi = $state('');
	let usuarioApi = $state('');
	let versionApi = $state('');

	$effect(() => {
		let vivo = true;
		(async () => {
			try {
				const pedir = fetcher
					|| ((url) => fetch(url, { credentials: 'same-origin' }));
				const r = await pedir(endpoint);
				if (!r.ok) return;
				const d = await r.json();
				if (!vivo) return;
				lugarApi = d.lugar?.modo || 'desconocido';
				ipApi = d.lugar?.ip || '';
				usuarioApi = d.user?.nombre || '';
				versionApi = d.shell?.version || '';
			} catch (e) { }
		})();
		return () => { vivo = false; };
	});

	const modo = $derived(lugar || lugarApi);
	const ipFinal = $derived(ip || ipApi);
	const nombre = $derived(usuario || usuarioApi);
	const vApp = $derived(appVersion || '?');
	const vShell = $derived(shellVersion || versionApi || '?');

	const LUGAR = {
		oficina: { icono: '🏢', texto: 'Oficina' },
		remoto: { icono: '🌐', texto: 'Remoto' },
		desconocido: { icono: '❓', texto: '—' }
	};
	const lug = $derived(LUGAR[modo] || LUGAR.desconocido);

	const effective = $derived(
		estado === 'offline' || estado === 'syncing' || estado === 'error'
			? estado
			: pendientes > 0 ? 'pending' : 'idle'
	);

	const PUNTO = {
		offline: 'offline',
		syncing: 'syncing',
		error: 'error',
		pending: 'pending',
		idle: 'ok'
	};

	function texto() {
		switch (effective) {
			case 'offline': return 'Sin conexión — modo offline';
			case 'syncing': return 'Sincronizando...';
			case 'error': return 'Error al sincronizar — reintentando';
			case 'pending':
				return `${pendientes} pendiente${pendientes > 1 ? 's' : ''} — toca para sincronizar`;
			default: return 'Todo sincronizado';
		}
	}
</script>

<div class="sync-header" onclick={() => onsync && onsync()}>
	<!-- Izquierda: volver + título -->
	<div class="sh-left">
		{#if showBack && onBack}
			<button class="sh-btn" onclick={(e) => { e.stopPropagation(); onBack(); }} title="Volver">←</button>
		{/if}
		{#if titulo}
			<span class="sh-title">{titulo}</span>
		{/if}
	</div>
	<!-- Centro: estado de sync -->
	<div class="sh-center">
		<span class="dot {PUNTO[effective] || 'ok'}"></span>
		<span class="sh-text">{texto()}</span>
	</div>
	<!-- Derecha: usuario + lugar + acciones + versión -->
	<div class="sh-right">
		{#if nombre}
			<span class="who">
				👤 {nombre}
				<span class="lugar {modo}" title={ipFinal}>{lug.icono} {lug.texto}</span>
			</span>
		{/if}
		{#if onChangelog}
			<button class="sh-btn" onclick={(e) => { e.stopPropagation(); onChangelog(); }} title="Novedades">📋</button>
		{/if}
		{#if onConfig}
			<button class="sh-btn" onclick={(e) => { e.stopPropagation(); onConfig(); }} title="Configuración">⚙️</button>
		{/if}
		{#if onLogout}
			<button class="sh-btn" onclick={(e) => { e.stopPropagation(); onLogout(); }} title="Salir">🚪</button>
		{/if}
		<span class="vers">v{vApp} · shell {vShell}</span>
	</div>
</div>