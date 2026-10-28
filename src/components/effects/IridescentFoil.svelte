<!--
	Iridescent Foil — tratamiento de foil CSS en capas que reacciona a scroll y puntero.

	Inspirado en DQnamo Kitchen (https://www.dqnamo.com/kitchen).
	Un efecto de foil iridiscente (como holograma) que se mueve con el mouse.
	Ideal para celebraciones (cumpleaños, aniversarios) en el Dashboard.

	Uso: <IridescentFoil><div>Contenido</div></IridescentFoil>
-->
<script lang="ts">
	interface Props {
		/** Intensidad del efecto (0-1) */
		intensity?: number;
		/** Mostrar el foil como overlay sobre el contenido */
		overlay?: boolean;
	}
	let { intensity = 0.6, overlay = true }: Props = $props();

	let mouseX = $state(0.5);
	let mouseY = $state(0.5);
	let hovering = $state(false);

	function handleMouseMove(e: MouseEvent) {
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		mouseX = (e.clientX - rect.left) / rect.width;
		mouseY = (e.clientY - rect.top) / rect.height;
	}
</script>

<div
	class="foil-container"
	class:hovering
	onmouseenter={() => (hovering = true)}
	onmouseleave={() => (hovering = false)}
	onmousemove={handleMouseMove}
	style="--mx: {mouseX}; --my: {mouseY}; --intensity: {intensity}"
>
	<slot />
	{#if overlay}
		<div class="foil-layer"></div>
	{/if}
</div>

<style>
	.foil-container {
		position: relative;
		overflow: hidden;
		border-radius: 12px;
	}

	.foil-layer {
		position: absolute;
		inset: 0;
		pointer-events: none;
		mix-blend-mode: color-dodge;
		opacity: 0;
		transition: opacity 0.3s;
		background: linear-gradient(
			135deg,
			hsl(calc(360 * var(--mx)), 80%, 60%) 0%,
			hsl(calc(360 * var(--my)), 70%, 50%) 25%,
			hsl(calc(360 * var(--mx) + 120), 80%, 60%) 50%,
			hsl(calc(360 * var(--my) + 240), 70%, 50%) 75%,
			hsl(calc(360 * var(--mx)), 80%, 60%) 100%
		);
		background-size: 200% 200%;
		animation: foil-shift 3s ease-in-out infinite;
	}

	.foil-container.hovering .foil-layer {
		opacity: var(--intensity);
	}

	@keyframes foil-shift {
		0%, 100% { background-position: 0% 50%; }
		50% { background-position: 100% 50%; }
	}
</style>