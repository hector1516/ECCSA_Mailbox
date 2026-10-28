<!--
	Logo Trace Loader — loader de logo trazado que se resuelve en una marca rellena.

	Inspirado en DQnamo Kitchen (https://www.dqnamo.com/kitchen).
	El logo de ECCSA se dibuja con trazo (stroke) y luego se rellena (fill),
	dando la sensación de que el logo se "construye" a sí mismo.

	Uso: <LogoTraceLoader size={120} />
-->
<script lang="ts">
	interface Props {
		/** Tamaño del logo en px */
		size?: number;
		/** Duración total de la animación en ms */
		duration?: number;
		/** Mostrar texto "Cargando..." debajo */
		showLabel?: boolean;
	}
	let { size = 120, duration = 2000, showLabel = true }: Props = $props();

	let visible = $state(true);

	// Ocultar después de la animación + un poco de tiempo
	$effect(() => {
		const t = setTimeout(() => (visible = false), duration + 500);
		return () => clearTimeout(t);
	});
</script>

{#if visible}
	<div class="loader" style="--size: {size}px; --dur: {duration}ms">
		<svg
			class="logo-trace"
			viewBox="0 0 200 200"
			width={size}
			height={size}
			aria-label="Cargando ECCSA"
		>
			<!-- Fondo circular -->
			<circle cx="100" cy="100" r="90" class="trace-bg" />

			<!-- Letra E estilizada (trazo) -->
			<path
				class="trace-stroke"
				d="M 60 50 L 60 150 M 60 50 L 140 50 M 60 100 L 120 100 M 60 150 L 140 150"
				fill="none"
				stroke-width="8"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>

			<!-- Letra C (trazo) -->
			<path
				class="trace-stroke trace-stroke-2"
				d="M 150 60 A 40 40 0 1 0 150 140"
				fill="none"
				stroke-width="8"
				stroke-linecap="round"
			/>

			<!-- Relleno final (aparece al final) -->
			<circle cx="100" cy="100" r="90" class="trace-fill" />
		</svg>
		{#if showLabel}
			<div class="label">Cargando…</div>
		{/if}
	</div>
{/if}

<style>
	.loader {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
	}

	.logo-trace {
		filter: drop-shadow(0 0 8px rgba(255, 174, 0, 0.3));
	}

	.trace-bg {
		fill: none;
		stroke: rgba(255, 174, 0, 0.15);
		stroke-width: 2;
	}

	.trace-stroke {
		stroke: #ffae00;
		stroke-dasharray: 400;
		stroke-dashoffset: 400;
		animation: trace var(--dur) ease-in-out forwards;
	}

	.trace-stroke-2 {
		animation-delay: calc(var(--dur) * 0.3);
	}

	.trace-fill {
		fill: rgba(255, 174, 0, 0);
		animation: fill-in calc(var(--dur) * 0.5) ease-in forwards;
		animation-delay: calc(var(--dur) * 0.7);
	}

	@keyframes trace {
		to {
			stroke-dashoffset: 0;
		}
	}

	@keyframes fill-in {
		to {
			fill: rgba(255, 174, 0, 0.08);
		}
	}

	.label {
		font-size: 14px;
		font-weight: 600;
		color: #94a3b8;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		animation: pulse 1.5s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 0.5; }
		50% { opacity: 1; }
	}
</style>