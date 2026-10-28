<!-- MagneticDropZone.svelte — Zona de drop que atrae el drag entrante -->
<script lang="ts">
  interface Props {
    label?: string;
    accept?: string;
    maxSize?: number;
    ondrop?: (files: File[]) => void;
    children?: any;
  }

  let {
    label = 'Arrastra archivos aquí',
    accept = '*',
    maxSize = 10 * 1024 * 1024,
    ondrop,
    children
  }: Props = $props();

  let isDragging = $state(false);
  let isOver = $state(false);
  let files = $state<File[]>([]);
  let zoneEl: HTMLDivElement;

  function handleDragEnter(e: DragEvent) {
    e.preventDefault();
    isDragging = true;
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    isOver = true;
  }

  function handleDragLeave(e: DragEvent) {
    e.preventDefault();
    if (e.target === zoneEl) {
      isOver = false;
    }
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    isDragging = false;
    isOver = false;
    
    const droppedFiles = Array.from(e.dataTransfer?.files || []);
    const validFiles = droppedFiles.filter(f => f.size <= maxSize);
    files = [...files, ...validFiles];
    ondrop?.(validFiles);
  }

  function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    const selected = Array.from(input.files || []);
    files = [...files, ...selected];
    ondrop?.(selected);
  }

  function removeFile(index: number) {
    files = files.filter((_, i) => i !== index);
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }
</script>

<div
  class="drop-zone"
  class:dragging={isDragging}
  class:over={isOver}
  bind:this={zoneEl}
  ondragenter={handleDragEnter}
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  ondrop={handleDrop}
  role="button"
  tabindex="0"
>
  {#if isDragging}
    <div class="drop-magnet">
      <div class="magnet-ring"></div>
      <div class="magnet-core">⬇</div>
    </div>
  {:else if files.length > 0}
    <div class="file-list">
      {#each files as file, i}
        <div class="file-item">
          <span class="file-icon">📄</span>
          <span class="file-name">{file.name}</span>
          <span class="file-size">{formatSize(file.size)}</span>
          <button class="file-remove" onclick={() => removeFile(i)}>✕</button>
        </div>
      {/each}
    </div>
  {:else}
    <div class="drop-content">
      {#if children}
        {@render children()}
      {:else}
        <div class="drop-icon">📁</div>
        <p class="drop-label">{label}</p>
        <p class="drop-hint">o haz clic para seleccionar</p>
      {/if}
    </div>
  {/if}
  
  <input
    type="file"
    {accept}
    multiple
    class="file-input"
    onchange={handleFileInput}
  />
</div>

<style>
  .drop-zone {
    position: relative;
    border: 2px dashed #334155;
    border-radius: 16px;
    padding: 2rem;
    text-align: center;
    transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    cursor: pointer;
    min-height: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .drop-zone:hover {
    border-color: #FF6B00;
    background: rgba(255, 107, 0, 0.05);
  }

  .drop-zone.dragging {
    border-color: #FF6B00;
    background: rgba(255, 107, 0, 0.1);
    transform: scale(1.02);
  }

  .drop-zone.over {
    border-color: #22C55E;
    background: rgba(34, 197, 94, 0.1);
    transform: scale(1.05);
  }

  .drop-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
  }

  .drop-icon {
    font-size: 2.5rem;
    opacity: 0.6;
  }

  .drop-label {
    color: #E2E8F0;
    font-weight: 600;
    margin: 0;
  }

  .drop-hint {
    color: #64748B;
    font-size: 0.8rem;
    margin: 0;
  }

  .drop-magnet {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .magnet-ring {
    width: 80px;
    height: 80px;
    border: 3px solid #FF6B00;
    border-radius: 50%;
    animation: magnet-pulse 0.8s ease-in-out infinite;
  }

  .magnet-core {
    position: absolute;
    font-size: 2rem;
    color: #FF6B00;
  }

  @keyframes magnet-pulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.3); opacity: 0.5; }
  }

  .file-list {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .file-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: rgba(30, 41, 59, 0.8);
    border-radius: 8px;
    font-size: 0.85rem;
  }

  .file-icon { font-size: 1.2rem; }
  .file-name { flex: 1; color: #E2E8F0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-size { color: #64748B; font-size: 0.75rem; }
  .file-remove {
    background: none;
    border: none;
    color: #64748B;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
    transition: color 0.2s, background 0.2s;
  }
  .file-remove:hover {
    color: #EF4444;
    background: rgba(239, 68, 68, 0.1);
  }

  .file-input {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }
</style>