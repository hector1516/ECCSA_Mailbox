<!--
	Ticket Card — silueta de ticket perforado con parallax sutil.

	Inspirado en DQnamo Kitchen (https://www.dqnamo.com/kitchen).
	El ticket tiene bordes perforados (como un boleto real) y un
	efecto de parallax sutil al mover el mouse.

	Uso: <TicketCard folio="TKT-001" vehiculo="Nissan NP300" usuario="Juan" />
-->
<script lang="ts">
	interface Props {
		folio: string;
		vehiculo?: string;
		usuario?: string;
		cliente?: string;
		descripcion?: string;
		fecha?: string;
		reciente?: boolean;
	}
	let {
		folio,
		vehiculo = '',
		usuario = '',
		cliente = '',
		descripcion = '',
		fecha = '',
		reciente = false
	}: Props = $props();

	let mouseX = $state(0);
	let mouseY = $state(0);
	let hovering = $state(false);

	function handleMouseMove(e: MouseEvent) {
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		mouseX = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
		mouseY = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
	}
</script>

<div
	class="ticket"
	class:reciente
	onmouseenter={() => (hovering = true)}
	onmouseleave={() => (hovering = false)}
	onmousemove={handleMouseMove}
	style="--mx: {mouseX}; --my: {mouseY}"
>
	<!-- Perforaciones laterales -->
	<div class="perf perf-left"></div>
	<div class="perf perf-right"></div>

	<div class="contenido">
		<div class="folio">{folio}</div>
		<div class="vehiculo">{vehiculo}</div>
		<div class="usuario">👤 {usuario}</div>
		{#if cliente}
			<div class="cliente">{cliente}</div>
		{/if}
		{#if descripcion}
			<div class="desc">{descripcion}</div>
		{/if}
		<div class="fecha">{fecha?.replace('T', ' ')}</div>
	</div>
</div>

<style>
	.ticket {
		position: relative;
		display: flex;
		flex-direction: column;
		justify-content: center;
		gap: 3px;
		padding: 14px 18px;
		border-radius: 12px;
		min-height: 110px;
		background: rgba(245, 158, 11, 0.06);
		border: 1px solid rgba(245, 158, 11, 0.14);
		overflow: hidden;
		transform: perspective(600px) rotateY(calc(var(--mx, 0) * 3deg)) rotateX(calc(var(--my, 0) * -3deg));
		transition: transform 0.15s ease-out, box-shadow 0.2s;
	}

	.ticket.reciente {
		border-color: rgba(255, 174, 0, 0.55);
		box-shadow: 0 0 18px rgba(255, 174, 0, 0.18);
	}

	/* Perforaciones laterales (como un boleto real) */
	.perf {
		position: absolute;
		top: 50%;
		width: 12px;
		height: 12px;
		border-radius: 50%;
		background: #0f172a;
		transform: translateY(-50%);
		z-index: 1;
	}
	.perf-left { left: -6px; }
	.perf-right { right: -6px; }

	/* Borde perforado (dashed) */
	.ticket::before {
		content: '';
		position: absolute;
		inset: 4px;
		border: 1px dashed rgba(245, 158, 11, 0.2);
		border-radius: 8px;
		pointer-events: none;
	}

	.contenido {
		position: relative;
		z-index: 2;
	}

	.folio { font-weight: 800; color: #ffae00; font-size: 17px; }
	.vehiculo { font-weight: 700; color: #f1f5f9; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.usuario { font-size: 13.5px; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.cliente { font-size: 13px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.desc { font-size: 12.5px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.fecha { font-size: 11.5px; color: #475569; margin-top: 3px; }
</style>