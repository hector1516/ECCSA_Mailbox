<!-- AuroraBackground.svelte — Fondo aurora animado (adaptado de Aceternity UI) -->
<script lang="ts">
  interface Props {
    class?: string;
    children?: any;
  }

  let {
    class: className = '',
    children
  }: Props = $props();
</script>

<div class="aurora-container {className}">
  <div class="aurora-bg">
    <div class="aurora-blob aurora-blob-1"></div>
    <div class="aurora-blob aurora-blob-2"></div>
    <div class="aurora-blob aurora-blob-3"></div>
  </div>
  <div class="aurora-content">
    {#if children}
      {@render children()}
    {/if}
  </div>
</div>

<style>
  .aurora-container {
    position: relative;
    overflow: hidden;
    background: var(--color-bg, #0F172A);
  }

  .aurora-bg {
    position: absolute;
    inset: 0;
    overflow: hidden;
    filter: blur(60px);
    opacity: 0.6;
  }

  .aurora-blob {
    position: absolute;
    border-radius: 50%;
    mix-blend-mode: screen;
  }

  .aurora-blob-1 {
    width: 60%;
    height: 60%;
    top: -20%;
    left: -10%;
    background: radial-gradient(circle, rgba(255, 107, 0, 0.4) 0%, transparent 70%);
    animation: aurora-move-1 15s ease-in-out infinite alternate;
  }

  .aurora-blob-2 {
    width: 50%;
    height: 50%;
    top: 10%;
    right: -15%;
    background: radial-gradient(circle, rgba(255, 174, 0, 0.3) 0%, transparent 70%);
    animation: aurora-move-2 18s ease-in-out infinite alternate;
  }

  .aurora-blob-3 {
    width: 40%;
    height: 40%;
    bottom: -10%;
    left: 30%;
    background: radial-gradient(circle, rgba(34, 197, 94, 0.2) 0%, transparent 70%);
    animation: aurora-move-3 20s ease-in-out infinite alternate;
  }

  @keyframes aurora-move-1 {
    0% { transform: translate(0, 0) scale(1); }
    100% { transform: translate(20%, 15%) scale(1.2); }
  }

  @keyframes aurora-move-2 {
    0% { transform: translate(0, 0) scale(1); }
    100% { transform: translate(-15%, 20%) scale(1.15); }
  }

  @keyframes aurora-move-3 {
    0% { transform: translate(0, 0) scale(1); }
    100% { transform: translate(10%, -15%) scale(1.1); }
  }

  .aurora-content {
    position: relative;
    z-index: 1;
  }

  @media (prefers-reduced-motion: reduce) {
    .aurora-blob {
      animation: none !important;
    }
  }
</style>