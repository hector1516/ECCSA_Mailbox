<!-- ErrorState — componente estándar del shell -->
<script>
  let { message = 'Error al cargar', onRetry = null } = $props();
</script>

<div class="error-state">
  <div class="error-icon">⚠️</div>
  <p class="error-msg">{message}</p>
  {#if onRetry}
    <button class="btn btn-sm btn-secondary" onclick={onRetry}>Reintentar</button>
  {/if}
</div>

<style>
  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem 1.5rem;
    text-align: center;
    color: var(--color-danger, #ef4444);
  }
  .error-icon { font-size: 2rem; margin-bottom: 0.75rem; }
  .error-msg { font-size: 0.85rem; margin: 0 0 1rem; color: var(--color-text-muted, #94a3b8); }
  .btn { padding: 0.4rem 0.75rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; }
  .btn-secondary { background: var(--color-surface-2, #334155); color: white; }
  .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.8rem; }
</style>