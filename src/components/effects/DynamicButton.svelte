<!-- DynamicButton.svelte — Botón que se redimensiona al animar su etiqueta -->
<script lang="ts">
  interface Props {
    label: string;
    loadingLabel?: string;
    isLoading?: boolean;
    variant?: 'primary' | 'secondary';
    onclick?: () => void;
    disabled?: boolean;
  }

  let {
    label,
    loadingLabel = 'Cargando...',
    isLoading = false,
    variant = 'primary',
    onclick,
    disabled = false
  }: Props = $props();

  let displayText = $derived(isLoading ? loadingLabel : label);
  let width = $state(0);
  let textEl: HTMLSpanElement;

  $effect(() => {
    if (textEl) {
      width = textEl.offsetWidth + 32;
    }
  });
</script>

<button
  class="dynamic-btn dynamic-{variant}"
  class:loading={isLoading}
  {disabled}
  onclick={onclick}
  style="min-width: {width}px"
>
  <span class="dynamic-text" bind:this={textEl}>
    {#if isLoading}
      <span class="spinner"></span>
    {/if}
    {displayText}
  </span>
</button>

<style>
  .dynamic-btn {
    position: relative;
    border: none;
    border-radius: 10px;
    padding: 0.625rem 1rem;
    font-family: inherit;
    font-weight: 600;
    font-size: 0.9rem;
    cursor: pointer;
    transition: min-width 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.2s, transform 0.1s;
    overflow: hidden;
    white-space: nowrap;
  }

  .dynamic-btn:active:not(:disabled) {
    transform: scale(0.97);
  }

  .dynamic-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .dynamic-primary {
    background: linear-gradient(135deg, #FF6B00, #FF8C33);
    color: #fff;
    box-shadow: 0 2px 8px rgba(255, 107, 0, 0.3);
  }

  .dynamic-secondary {
    background: #1E293B;
    color: #E2E8F0;
    border: 1px solid #334155;
  }

  .dynamic-text {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>