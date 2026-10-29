<!-- TextGenerate.svelte — Texto que se genera palabra por palabra (adaptado de Aceternity UI) -->
<script lang="ts">
  interface Props {
    text: string;
    class?: string;
    speed?: number;
    filter?: boolean;
  }

  let {
    text,
    class: className = '',
    speed = 50,
    filter = true
  }: Props = $props();

  let displayedWords = $state<string[]>([]);
  let isGenerating = $state(false);

  $effect(() => {
    if (!text) return;
    isGenerating = true;
    displayedWords = [];
    const words = text.split(' ');
    let i = 0;
    const interval = setInterval(() => {
      if (i < words.length) {
        displayedWords = [...displayedWords, words[i]];
        i++;
      } else {
        clearInterval(interval);
        isGenerating = false;
      }
    }, speed);
    return () => clearInterval(interval);
  });
</script>

<div class="text-generate {className}">
  {#each displayedWords as word, i}
    <span
      class="text-word"
      class:blur={filter}
      style="animation-delay: {i * 0.05}s"
    >
      {word}{' '}
    </span>
  {/each}
  {#if isGenerating}
    <span class="text-cursor">|</span>
  {/if}
</div>

<style>
  .text-generate {
    display: inline;
  }

  .text-word {
    display: inline;
    opacity: 0;
    animation: text-appear 0.3s ease forwards;
  }

  .text-word.blur {
    filter: blur(4px);
    animation: text-appear-blur 0.5s ease forwards;
  }

  @keyframes text-appear {
    0% { opacity: 0; }
    100% { opacity: 1; }
  }

  @keyframes text-appear-blur {
    0% { opacity: 0; filter: blur(4px); }
    100% { opacity: 1; filter: blur(0); }
  }

  .text-cursor {
    display: inline-block;
    animation: cursor-blink 1s step-end infinite;
    color: var(--color-primary, #FF6B00);
  }

  @keyframes cursor-blink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0; }
  }

  @media (prefers-reduced-motion: reduce) {
    .text-word {
      opacity: 1;
      filter: none;
      animation: none;
    }
  }
</style>