<!-- LoadingState — componente estándar del shell -->
<script>
  let { message = 'Cargando...' } = $props();
</script>

<div class="loading-state">
  <div class="spinner"></div>
  <p class="loading-msg">{message}</p>
</div>

<style>
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem 1.5rem;
    text-align: center;
    color: var(--color-text-muted, #94a3b8);
  }
  .spinner {
    width: 28px; height: 28px; margin: 0 auto 0.75rem;
    border: 3px solid var(--color-surface-2, #334155);
    border-top-color: var(--color-primary, #3b82f6);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-msg { font-size: 0.85rem; margin: 0; }
</style>