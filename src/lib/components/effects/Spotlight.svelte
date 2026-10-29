<!-- Spotlight.svelte — Efecto spotlight que sigue el mouse (adaptado de Aceternity UI) -->
<script lang="ts">
  interface Props {
    class?: string;
    fill?: string;
    children?: any;
  }

  let {
    class: className = '',
    fill = 'rgba(255, 107, 0, 0.15)',
    children
  }: Props = $props();

  let container: HTMLDivElement;
  let mouseX = $state(0);
  let mouseY = $state(0);
  let isHovering = $state(false);

  function handleMouseMove(e: MouseEvent) {
    if (!container) return;
    const rect = container.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;
  }

  function handleMouseEnter() {
    isHovering = true;
  }

  function handleMouseLeave() {
    isHovering = false;
  }
</script>

<div
  bind:this={container}
  class="spotlight-container {className}"
  onmousemove={handleMouseMove}
  onmouseenter={handleMouseEnter}
  onmouseleave={handleMouseLeave}
>
  {#if isHovering}
    <div
      class="spotlight"
      style="left: {mouseX}px; top: {mouseY}px; background: radial-gradient(circle 200px at center, {fill}, transparent);"
    ></div>
  {/if}
  <div class="spotlight-content">
    {#if children}
      {@render children()}
    {/if}
  </div>
</div>

<style>
  .spotlight-container {
    position: relative;
    overflow: hidden;
    border-radius: var(--radius, 16px);
  }

  .spotlight {
    position: absolute;
    width: 400px;
    height: 400px;
    transform: translate(-50%, -50%);
    pointer-events: none;
    z-index: 0;
    transition: opacity 0.3s ease;
  }

  .spotlight-content {
    position: relative;
    z-index: 1;
  }
</style>