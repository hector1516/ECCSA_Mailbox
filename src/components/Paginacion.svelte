<script>
	// Paginación para los listados de Admon.
	//
	// Antes cada pantalla pintaba TODOS los registros de una vez: el listado de
	// inventario son 519 ítems y el de cotizaciones más de mil. Con eso el
	// navegador se come el trabajo de crear miles de nodos al abrir la pantalla.
	// Este componente no pide nada al servidor: parte el arreglo que ya está en
	// memoria y muestra solo una página, así que también funciona sin conexión
	// (el aviso de "Sin conexión" sigue mandando la lista desde la caché).
	//
	// Uso:
	//   let pagina = $state(1);
	//   const pag = $derived(filtradas.slice((pagina - 1) * 100, pagina * 100));
	//   ...{#each pag as x}...{/each}
	//   <Paginacion total={filtradas.length} bind:pagina />
	//
	// `porPagina` es 100 porque es lo que pidió el usuario; con menos de 100
	// registros no se dibuja nada (no hay nada que paginar).
	let {
		total = 0,
		pagina = $bindable(1),
		porPagina = 100,
		etiqueta = 'registros',
		mostrarRango = true
	} = $props();

	const totalPaginas = $derived(Math.max(1, Math.ceil((total || 0) / porPagina)));
	const desde = $derived(total === 0 ? 0 : (pagina - 1) * porPagina + 1);
	const hasta = $derived(Math.min(pagina * porPagina, total));

	// Si la lista se acorta (un filtro nuevo, un borrado) y la página actual se
	// queda fuera de rango, se corrige sola; si no, el usuario se queda en una
	// página vacía sin salida visible.
	$effect(() => {
		if (pagina > totalPaginas) pagina = totalPaginas;
		if (pagina < 1) pagina = 1;
	});

	// Atajo: saltar de página con las flechas cuando el foco está en el control.
	function alTeclado(e) {
		if (e.key === 'ArrowLeft' && pagina > 1) { pagina -= 1; e.preventDefault(); }
		if (e.key === 'ArrowRight' && pagina < totalPaginas) { pagina += 1; e.preventDefault(); }
	}
</script>

{#if total > porPagina}
	<nav class="pag" aria-label="Paginación de {etiqueta}">
		{#if mostrarRango}
			<span class="rango">Mostrando {desde}–{hasta} de <b>{total}</b> {etiqueta}</span>
		{/if}

		<div class="botones">
			<button class="btn-sm" onclick={() => (pagina = 1)} disabled={pagina === 1}
				title="Primera página" aria-label="Primera página">⏮</button>
			<button class="btn-sm" onclick={() => (pagina -= 1)} disabled={pagina === 1}
				onkeydown={alTeclado} title="Anterior" aria-label="Página anterior">◀ Anterior</button>

			<span class="folio">Página <b>{pagina}</b> de <b>{totalPaginas}</b></span>

			<button class="btn-sm" onclick={() => (pagina += 1)} disabled={pagina === totalPaginas}
				onkeydown={alTeclado} title="Siguiente" aria-label="Página siguiente">Siguiente ▶</button>
			<button class="btn-sm" onclick={() => (pagina = totalPaginas)} disabled={pagina === totalPaginas}
				title="Última página" aria-label="Última página">⏭</button>
		</div>

		{#if totalPaginas > 2}
			<input class="saltar" type="number" min="1" max={totalPaginas} placeholder="ir a…"
				aria-label="Ir a la página"
				onkeydown={(e) => {
					if (e.key !== 'Enter') return;
					const n = parseInt(e.currentTarget.value, 10);
					if (!Number.isNaN(n)) pagina = Math.min(Math.max(1, n), totalPaginas);
					e.currentTarget.value = '';
				}} />
		{/if}
	</nav>
{/if}

<style>
	.pag {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.6rem;
		justify-content: space-between;
		margin-top: 1rem;
		padding-top: 0.85rem;
		border-top: 1px solid var(--color-line);
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}
	.rango { white-space: nowrap; }
	.rango b { color: var(--color-text); }
	.botones { display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; }
	.folio { padding: 0 0.45rem; white-space: nowrap; }
	.folio b { color: var(--color-text); }
	.btn-sm {
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-sm);
		padding: 0.35rem 0.6rem;
		font-size: 0.78rem;
		font-family: var(--font-family);
		cursor: pointer;
		transition: background 0.15s, border-color 0.15s;
	}
	.btn-sm:hover:not(:disabled) { background: rgba(255, 107, 0, 0.12); border-color: var(--color-primary); }
	.btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }
	.saltar {
		width: 4.2rem;
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-sm);
		padding: 0.35rem 0.5rem;
		font-size: 0.78rem;
		font-family: var(--font-family);
	}
	@media (max-width: 640px) {
		.pag { justify-content: center; }
		.rango { width: 100%; text-align: center; }
	}
</style>