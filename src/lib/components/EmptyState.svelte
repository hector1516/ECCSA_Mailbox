<!-- EmptyState — componente estándar del shell -->
<script>
  import { onMount } from 'svelte';

  let { icon = '📋', title = 'Sin datos', description = '', actionLabel = '', action = null } = $props();
</script>

<div class="empty-state">
  <div class="empty-icon">{icon}</div>
  <h3 class="empty-title">{title}</h3>
  {#if description}
    <p class="empty-desc">{description}</p>
  {/if}
  {#if actionLabel && action}
    <button class="btn btn-primary btn-sm" onclick={action}>{actionLabel}</button>
  {/if}
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 1.5rem;
    text-align: center;
    color: var(--color-text-muted, #94a3b8);
  }
  .empty-icon { font-size: 3rem; line-height: 1; margin-bottom: 1rem; opacity: 0.6; }
  .empty-title { font-size: 1.05rem; font-weight: 600; margin: 0 0 0.5rem; color: var(--color-text, #f1f5f9); }
  .empty-desc { font-size: 0.85rem; line-height: 1.5; margin: 0 0 1rem; max-width: 300px; }
  .btn { padding: 0.4rem 0.75rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; }
  .btn-primary { background: var(--color-primary, #3b82f6); color: white; }
  .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.8rem; }
</style>