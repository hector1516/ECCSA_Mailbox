<script>
	/* ECCSA-Shell �� PageHeader (referencia Svelte). ESTE ES EL EST�?NDAR.
	   ------------------------------------------------------------------
	   Header de pǭgina universal: proporciona el bot��n de volver, el t��tulo
	   y los botones de acci��n universales (config, novedades, salir). Las apps
	   solo pasan props y ponen su contenido debajo.

	   Reparto de responsabilidades:
	     �� El SHELL manda: este markup y el CSS (.page-header en body.css).
	     �� La APP manda: sus stores y los botones internos del m��dulo, que van
	       en el contenido de la pǭgina, NO en el header.

	   Deliberadamente en JS plano con JSDoc (sin lang="ts"): Admon compila con
	   vite+svelte sin preprocesador de TypeScript.

	   Props:
	     titulo        string   (t��tulo de la pǭgina actual; '' = no se pinta)
	     onBack        () => any  (si se pasa, se pinta el bot��n �?�)
	     onConfig      () => any  (si se pasa, se pinta �?�)
	     onLogout      () => any  (si se pasa, se pinta �Y-s�)
	     onChangelog   () => any  (si se pasa, se pinta �Y"�)
	     showBack      boolean (default false)
	*/
	let {
		titulo = '',
		onBack = null,
		onConfig = null,
		onLogout = null,
		onChangelog = null,
		showBack = false
	} = $props();
</script>

{#if titulo || showBack || onConfig || onLogout || onChangelog}
	<div class="page-header">
		{#if showBack && onBack}
			<button class="btn-back" onclick={onBack} title="Volver">←</button>
		{/if}
		{#if titulo}
			<h1 class="page-title">{titulo}</h1>
		{/if}
		<div class="page-actions">
			{#if onChangelog}
				<button onclick={onChangelog} title="Novedades">📋</button>
			{/if}
			{#if onConfig}
				<button onclick={onConfig} title="Configuración">⚙️</button>
			{/if}
			{#if onLogout}
				<button onclick={onLogout} title="Salir">🚪</button>
			{/if}
		</div>
	</div>
{/if}