<!--
	Card Fan — efecto de abanico para mostrar múltiples tarjetas.

	Inspirado en DQnamo Kitchen (https://www.dqnamo.com/kitchen).
	Las tarjetas se despliegan en abanico, se pueden hojear y seleccionar.
	Ideal para mostrar múltiples vehículos/empleados en el Dashboard.

	Uso: <CardFan cards={[{title: 'Juan', subtitle: 'ECCSA'}, ...]} />
-->
<script lang="ts">
	interface Card {
		title: string;
		subtitle?: string;
		icon?: string;
		color?: string;
	}

	interface Props {
		cards: Card[];
		/** Máximo de tarjetas visibles en el abanico */
		maxVisible?: number;
	}
	let { cards, maxVisible = 5 }: Props = $props();

	let spread = $state(false);
	let hoveredIndex = $state<number | null>(null);

	const visibleCards = $derived(cards.slice(0, maxVisible));
	const fanAngle = $derived(spread ? 8 : 3);
	const fanOffset = $derived(spread ? 40 : 12);
</script>

<div
	class="fan-container"
	onmouseenter={() => (spread = true)}
	onmouseleave={() => (spread = false)}
>
	{#each visibleCards as card, i}
		{@const angle = (i - (visibleCards.length - 1) / 2) * fanAngle}
		{@const offset = (i - (visibleCards.length - 1) / 2) * fanOffset}
		<div
			class="fan-card"
			class:hovered={hoveredIndex === i}
			style="
				--angle: {angle}deg;
				--offset: {offset}px;
				--index: {i};
				--z: {visibleCards.length - i};
				--color: {card.color || '#ffae00'};
			"
			onmouseenter={() => (hoveredIndex = i)}
			onmouseleave={() => (hoveredIndex = null)}
		>
			<div class="card-content">
				{#if card.icon}
					<div class="card-icon">{card.icon}</div>
				{/if}
				<div class="card-title">{card.title}</div>
				{#if card.subtitle}
					<div class="card-subtitle">{card.subtitle}</div>
				{/if}
			</div>
		</div>
	{/each}
</div>

<style>
	.fan-container {
		position: relative;
		width: 100%;
		height: 200px;
		display: flex;
		align-items: center;
		justify-content: center;
		perspective: 800px;
	}

	.fan-card {
		position: absolute;
		width: 140px;
		height: 180px;
		border-radius: 12px;
		background: linear-gradient(135deg, #1e293b, #0f172a);
		border: 1px solid rgba(255, 174, 0, 0.2);
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
		transform: rotate(var(--angle)) translateX(var(--offset)) translateZ(calc(var(--z) * 1px));
		transform-origin: bottom center;
		transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s;
		z-index: var(--z);
		cursor: pointer;
		overflow: hidden;
	}

	.fan-card.hovered {
		transform: rotate(var(--angle)) translateX(var(--offset)) translateZ(calc(var(--z) * 1px)) translateY(-20px) scale(1.05);
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6), 0 0 12px color-mix(in srgb, var(--color) 30%, transparent);
		z-index: 100;
	}

	.card-content {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100%;
		padding: 12px;
		text-align: center;
	}

	.card-icon {
		font-size: 32px;
		margin-bottom: 8px;
	}

	.card-title {
		font-size: 14px;
		font-weight: 700;
		color: #f1f5f9;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 100%;
	}

	.card-subtitle {
		font-size: 11px;
		color: #94a3b8;
		margin-top: 4px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 100%;
	}
</style>