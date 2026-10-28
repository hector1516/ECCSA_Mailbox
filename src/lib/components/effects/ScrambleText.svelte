<!--
	Scramble Text — texto que se revela mediante scramble encriptado.

	Inspirado en DQnamo Kitchen (https://www.dqnamo.com/kitchen).
	El texto se muestra con caracteres aleatorios que se van resolviendo
	hasta revelar el texto final. Ideal para KPIs que cambian.

	Uso: <ScrambleText text="1,234" duration={800} />
-->
<script lang="ts">
	interface Props {
		/** Texto final a revelar */
		text: string;
		/** Duración de la animación en ms */
		duration?: number;
		/** Caracteres usados para el scramble */
		chars?: string;
		/** Clase CSS adicional */
		class?: string;
	}
	let { text, duration = 800, chars = '0123456789ABCDEF', class: className = '' }: Props = $props();

	let display = $state('');
	let animating = $state(false);

	const scramble = (target: string, dur: number) => {
		animating = true;
		const len = target.length;
		let frame = 0;
		const totalFrames = Math.ceil(dur / 30);
		const interval = setInterval(() => {
			frame++;
			let result = '';
			for (let i = 0; i < len; i++) {
				const progress = frame / totalFrames;
				const charProgress = (i / len) * 0.5 + 0.5;
				if (progress > charProgress) {
					result += target[i];
				} else {
					result += chars[Math.floor(Math.random() * chars.length)];
				}
			}
			display = result;
			if (frame >= totalFrames) {
				clearInterval(interval);
				display = target;
				animating = false;
			}
		}, 30);
	};

	$effect(() => {
		scramble(text, duration);
	});
</script>

<span class="scramble {className}" class:animating>{display}</span>

<style>
	.scramble {
		font-variant-numeric: tabular-nums;
		display: inline-block;
	}
	.scramble.animating {
		color: #ffae00;
	}
</style>