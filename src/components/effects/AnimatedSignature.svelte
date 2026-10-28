<!-- AnimatedSignature.svelte — Firma SVG que se dibuja al montar -->
<script lang="ts">
  interface Props {
    name?: string;
    width?: number;
    height?: number;
    color?: string;
    strokeWidth?: number;
    duration?: number;
  }

  let {
    name = 'Firma',
    width = 300,
    height = 100,
    color = '#FF6B00',
    strokeWidth = 2,
    duration = 2000
  }: Props = $props();

  let pathEl: SVGPathElement;
  let pathLength = $state(0);
  let isDrawing = $state(false);

  // Generate a simple signature path from name
  function generateSignaturePath(name: string, w: number, h: number): string {
    const chars = name.toLowerCase().split('');
    let x = 20;
    const y = h / 2;
    let path = `M ${x} ${y}`;
    
    for (let i = 0; i < chars.length; i++) {
      const char = chars[i];
      const charWidth = w / (chars.length + 1);
      const nextX = x + charWidth;
      const wave = Math.sin(i * 0.8) * (h * 0.15);
      const controlY = y + wave;
      
      if (i % 2 === 0) {
        path += ` Q ${x + charWidth / 2} ${controlY} ${nextX} ${y}`;
      } else {
        path += ` C ${x + charWidth / 3} ${y - wave} ${x + (2 * charWidth) / 3} ${y + wave} ${nextX} ${y}`;
      }
      x = nextX;
    }
    
    // Add a flourish at the end
    path += ` Q ${x + 10} ${y - 20} ${x + 20} ${y}`;
    path += ` Q ${x + 25} ${y + 15} ${x + 35} ${y - 5}`;
    
    return path;
  }

  let signaturePath = $derived(generateSignaturePath(name, width, height));

  $effect(() => {
    if (pathEl) {
      pathLength = pathEl.getTotalLength();
      // Start animation
      requestAnimationFrame(() => {
        isDrawing = true;
      });
    }
  });
</script>

<div class="signature-container" style="width: {width}px; height: {height}px;">
  <svg
    viewBox="0 0 {width} {height}"
    width={width}
    height={height}
    class="signature-svg"
  >
    <path
      bind:this={pathEl}
      d={signaturePath}
      fill="none"
      stroke={color}
      stroke-width={strokeWidth}
      stroke-linecap="round"
      stroke-linejoin="round"
      class="signature-path"
      class:drawing={isDrawing}
      style="--path-length: {pathLength}; --duration: {duration}ms"
    />
  </svg>
</div>

<style>
  .signature-container {
    display: inline-block;
  }

  .signature-svg {
    overflow: visible;
  }

  .signature-path {
    stroke-dasharray: var(--path-length, 1000);
    stroke-dashoffset: var(--path-length, 1000);
    transition: stroke-dashoffset var(--duration, 2000ms) cubic-bezier(0.4, 0, 0.2, 1);
  }

  .signature-path.drawing {
    stroke-dashoffset: 0;
  }
</style>