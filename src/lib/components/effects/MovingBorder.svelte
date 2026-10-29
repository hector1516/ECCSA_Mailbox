<!-- MovingBorder.svelte — Borde animado (adaptado de Aceternity UI) -->
<script lang="ts">
  interface Props {
    duration?: number;
    borderRadius?: string;
    class?: string;
    children?: any;
  }

  let {
    duration = 2000,
    borderRadius = '1.75rem',
    class: className = '',
    children
  }: Props = $props();
</script>

<div
  class="moving-border-container {className}"
  style="--duration: {duration}ms; --border-radius: {borderRadius}"
>
  <div class="moving-border">
    <div class="moving-border-gradient"></div>
  </div>
  <div class="moving-border-content">
    {#if children}
      {@render children()}
    {/if}
  </div>
</div>

<style>
  .moving-border-container {
    position: relative;
    border-radius: var(--border-radius);
    overflow: hidden;
    padding: 1px;
  }

  .moving-border {
    position: absolute;
    inset: 0;
    border-radius: var(--border-radius);
    overflow: hidden;
  }

  .moving-border-gradient {
    position: absolute;
    width: 200%;
    height: 200%;
    top: -50%;
    left: -50%;
    background: conic-gradient(
      from 0deg,
      transparent 0%,
      var(--color-primary, #FF6B00) 10%,
      var(--color-primary-light, #FFAE00) 20%,
      transparent 30%
    );
    animation: moving-border-rotate var(--duration) linear infinite;
  }

  .moving-border-content {
    position: relative;
    z-index: 1;
    background: var(--color-surface, #1E293B);
    border-radius: calc(var(--border-radius) - 1px);
    padding: 1rem;
  }

  @keyframes moving-border-rotate {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  @media (prefers-reduced-motion: reduce) {
    .moving-border-gradient {
      animation: none !important;
    }
  }
</style>