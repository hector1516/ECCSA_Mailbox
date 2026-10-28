<!-- ScrollFadeList.svelte — Lista con fade suave en overflow -->
<script lang="ts">
  interface Props {
    maxHeight?: string;
    fadeColor?: string;
    children?: any;
  }

  let {
    maxHeight = '300px',
    fadeColor = 'rgba(15, 23, 42, 0.9)',
    children
  }: Props = $props();

  let scrollEl: HTMLDivElement;
  let showTopFade = $state(false);
  let showBottomFade = $state(true);

  function handleScroll() {
    if (!scrollEl) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollEl;
    showTopFade = scrollTop > 10;
    showBottomFade = scrollTop + clientHeight < scrollHeight - 10;
  }
</script>

<div class="scroll-fade-container" style="max-height: {maxHeight}">
  {#if showTopFade}
    <div class="fade-top" style="background: linear-gradient(to bottom, {fadeColor}, transparent)"></div>
  {/if}
  
  <div class="scroll-content" bind:this={scrollEl} onscroll={handleScroll}>
    {#if children}
      {@render children()}
    {/if}
  </div>
  
  {#if showBottomFade}
    <div class="fade-bottom" style="background: linear-gradient(to top, {fadeColor}, transparent)"></div>
  {/if}
</div>

<style>
  .scroll-fade-container {
    position: relative;
    overflow: hidden;
  }

  .scroll-content {
    overflow-y: auto;
    max-height: inherit;
    scrollbar-width: thin;
    scrollbar-color: #334155 transparent;
  }

  .scroll-content::-webkit-scrollbar {
    width: 6px;
  }

  .scroll-content::-webkit-scrollbar-track {
    background: transparent;
  }

  .scroll-content::-webkit-scrollbar-thumb {
    background: #334155;
    border-radius: 3px;
  }

  .scroll-content::-webkit-scrollbar-thumb:hover {
    background: #475569;
  }

  .fade-top, .fade-bottom {
    position: absolute;
    left: 0;
    right: 0;
    height: 24px;
    pointer-events: none;
    z-index: 1;
  }

  .fade-top { top: 0; }
  .fade-bottom { bottom: 0; }
</style>