<!--
	Receipt Printer — estado de checkout que imprime un recibo físico al pagar.

	Inspirado en DQnamo Kitchen (https://www.dqnamo.com/kitchen).
	Un recibo que se "imprime" con animación de despliegue, como una
	impresora térmica. Ideal para avisos de pago procesado o reportes firmados.

	Uso: <ReceiptPrinter title="Pago procesado" amount="$1,234.00" />
-->
<script lang="ts">
	interface Props {
		/** Título del recibo */
		title: string;
		/** Monto o dato principal */
		amount?: string;
		/** Líneas de detalle (label: value) */
		details?: { label: string; value: string }[];
		/** Mostrar automáticamente (true) o controlado por prop */
		show?: boolean;
	}
	let { title, amount = '', details = [], show = true }: Props = $props();

	let printing = $state(false);
	let printed = $state(false);

	$effect(() => {
		if (show) {
			printing = true;
			const t = setTimeout(() => {
				printed = true;
				printing = false;
			}, 1200);
			return () => clearTimeout(t);
		}
	});
</script>

{#if show}
	<div class="receipt" class:printing class:printed>
		<div class="receipt-header">
			<div class="receipt-title">{title}</div>
			{#if amount}
				<div class="receipt-amount">{amount}</div>
			{/if}
		</div>

		<div class="receipt-body">
			{#each details as d, i}
				<div class="receipt-line" style="animation-delay: {i * 0.1}s">
					<span class="label">{d.label}</span>
					<span class="value">{d.value}</span>
				</div>
			{/each}
		</div>

		<div class="receipt-footer">
			<div class="barcode"></div>
			<div class="receipt-date">{new Date().toLocaleDateString('es-MX')}</div>
		</div>

		<!-- Efecto de impresión (papel saliendo) -->
		<div class="print-effect"></div>
	</div>
{/if}

<style>
	.receipt {
		background: #f8fafc;
		color: #1e293b;
		border-radius: 8px;
		padding: 16px;
		font-family: 'Courier New', monospace;
		font-size: 13px;
		max-width: 320px;
		margin: 0 auto;
		position: relative;
		overflow: hidden;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
		transform-origin: top center;
		animation: print-in 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
	}

	@keyframes print-in {
		from {
			transform: scaleY(0);
			opacity: 0;
		}
		to {
			transform: scaleY(1);
			opacity: 1;
		}
	}

	.receipt.printing {
		animation: printing 1.2s ease-in-out;
	}

	@keyframes printing {
		0% { transform: scaleY(0); opacity: 0; }
		50% { transform: scaleY(0.5); opacity: 0.7; }
		100% { transform: scaleY(1); opacity: 1; }
	}

	.receipt-header {
		text-align: center;
		border-bottom: 1px dashed #cbd5e1;
		padding-bottom: 12px;
		margin-bottom: 12px;
	}

	.receipt-title {
		font-size: 14px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.1em;
	}

	.receipt-amount {
		font-size: 24px;
		font-weight: 800;
		margin-top: 4px;
		color: #059669;
	}

	.receipt-body {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.receipt-line {
		display: flex;
		justify-content: space-between;
		animation: line-in 0.3s ease-out both;
	}

	@keyframes line-in {
		from { opacity: 0; transform: translateX(-8px); }
		to { opacity: 1; transform: none; }
	}

	.label { color: #64748b; }
	.value { font-weight: 600; color: #1e293b; }

	.receipt-footer {
		border-top: 1px dashed #cbd5e1;
		padding-top: 12px;
		margin-top: 12px;
		text-align: center;
	}

	.barcode {
		height: 30px;
		background: repeating-linear-gradient(
			90deg,
			#1e293b 0px, #1e293b 2px,
			transparent 2px, transparent 4px,
			#1e293b 4px, #1e293b 5px,
			transparent 5px, transparent 8px
		);
		margin-bottom: 8px;
		border-radius: 2px;
	}

	.receipt-date {
		font-size: 10px;
		color: #94a3b8;
	}

	.print-effect {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 4px;
		background: linear-gradient(180deg, rgba(255,255,255,0.8), transparent);
		animation: print-glow 1.2s ease-out;
		pointer-events: none;
	}

	@keyframes print-glow {
		0% { top: 0; opacity: 1; }
		100% { top: 100%; opacity: 0; }
	}
</style>