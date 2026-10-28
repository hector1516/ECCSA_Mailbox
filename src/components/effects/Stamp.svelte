<!--
	Stamp — marco de sello postal reutilizable para imágenes, texto y contenido.

	Inspirado en DQnamo Kitchen (https://www.dqnamo.com/kitchen).
	Un marco con bordes ondulados (como un sello postal) que se puede
	usar para marcar eventos especiales (cumpleaños, aniversarios, salidas).

	Uso: <Stamp text="¡Feliz cumpleaños!" subtext="Juan Pérez" color="#ffae00" />
-->
<script lang="ts">
	interface Props {
		/** Texto principal del sello */
		text: string;
		/** Subtexto (nombre, fecha) */
		subtext?: string;
		/** Color del sello */
		color?: string;
		/** Tamaño del sello */
		size?: number;
		/** Rotación en grados */
		rotation?: number;
	}
	let {
		text,
		subtext = '',
		color = '#ffae00',
		size = 120,
		rotation = -5
	}: Props = $props();
</script>

<div
	class="stamp"
	style="--color: {color}; --size: {size}px; --rot: {rotation}deg"
>
	<div class="stamp-inner">
		<div class="stamp-text">{text}</div>
		{#if subtext}
			<div class="stamp-subtext">{subtext}</div>
		{/if}
	</div>
	<!-- Borde ondulado (sello postal) -->
	<svg class="stamp-border" viewBox="0 0 100 100" preserveAspectRatio="none">
		<rect x="2" y="2" width="96" height="96" rx="4" ry="4"
			fill="none" stroke={color} stroke-width="2"
			stroke-dasharray="4 2" />
	</svg>
</div>

<style>
	.stamp {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: var(--size);
		height: var(--size);
		transform: rotate(var(--rot));
		position: relative;
	}

	.stamp-inner {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		padding: 8px;
		border: 2px solid var(--color);
		border-radius: 4px;
		background: rgba(15, 23, 42, 0.85);
		backdrop-filter: blur(4px);
		width: calc(var(--size) - 12px);
		height: calc(var(--size) - 12px);
		box-shadow: 0 0 12px color-mix(in srgb, var(--color) 30%, transparent);
	}

	.stamp-text {
		font-size: calc(var(--size) * 0.12);
		font-weight: 800;
		color: var(--color);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		line-height: 1.1;
	}

	.stamp-subtext {
		font-size: calc(var(--size) * 0.09);
		color: #94a3b8;
		margin-top: 4px;
		line-height: 1.2;
	}

	.stamp-border {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
	}
</style>