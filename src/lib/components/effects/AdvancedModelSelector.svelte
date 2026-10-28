<!-- AdvancedModelSelector.svelte — Selector informado con búsqueda y filtrado -->
<script lang="ts">
  interface Option {
    id: string;
    label: string;
    description?: string;
    badge?: string;
    group?: string;
  }

  interface Props {
    options: Option[];
    value?: string;
    placeholder?: string;
    onSelect?: (option: Option) => void;
    searchable?: boolean;
  }

  let {
    options,
    value = '',
    placeholder = 'Seleccionar...',
    onSelect,
    searchable = true
  }: Props = $props();

  let isOpen = $state(false);
  let search = $state('');
  let selectedId = $state(value);

  let filtered = $derived(
    search
      ? options.filter(o =>
          o.label.toLowerCase().includes(search.toLowerCase()) ||
          o.description?.toLowerCase().includes(search.toLowerCase())
        )
      : options
  );

  let selected = $derived(options.find(o => o.id === selectedId));

  function select(option: Option) {
    selectedId = option.id;
    isOpen = false;
    search = '';
    onSelect?.(option);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      isOpen = false;
      search = '';
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="model-selector">
  <button
    class="selector-trigger"
    onclick={() => isOpen = !isOpen}
    aria-expanded={isOpen}
    aria-haspopup="listbox"
  >
    <span class="selector-value">
      {#if selected}
        {selected.label}
        {#if selected.badge}
          <span class="selector-badge">{selected.badge}</span>
        {/if}
      {:else}
        <span class="selector-placeholder">{placeholder}</span>
      {/if}
    </span>
    <span class="selector-arrow" class:open={isOpen}>▾</span>
  </button>

  {#if isOpen}
    <div class="selector-dropdown">
      {#if searchable}
        <div class="selector-search">
          <input
            type="text"
            placeholder="Buscar..."
            bind:value={search}
            autofocus
          />
        </div>
      {/if}
      
      <div class="selector-options" role="listbox">
        {#each filtered as option (option.id)}
          <button
            class="selector-option"
            class:selected={option.id === selectedId}
            onclick={() => select(option)}
            role="option"
            aria-selected={option.id === selectedId}
          >
            <div class="option-main">
              <span class="option-label">{option.label}</span>
              {#if option.badge}
                <span class="option-badge">{option.badge}</span>
              {/if}
            </div>
            {#if option.description}
              <span class="option-desc">{option.description}</span>
            {/if}
          </button>
        {:else}
          <div class="selector-empty">Sin resultados</div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .model-selector {
    position: relative;
    width: 100%;
  }

  .selector-trigger {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.625rem 0.875rem;
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 10px;
    color: #E2E8F0;
    font-size: 0.9rem;
    cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .selector-trigger:hover {
    border-color: #475569;
  }

  .selector-trigger:focus {
    outline: none;
    border-color: #FF6B00;
    box-shadow: 0 0 0 3px rgba(255, 107, 0, 0.15);
  }

  .selector-value {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .selector-placeholder {
    color: #64748B;
  }

  .selector-badge, .option-badge {
    font-size: 0.65rem;
    padding: 0.125rem 0.375rem;
    background: rgba(255, 107, 0, 0.15);
    color: #FF8C33;
    border-radius: 4px;
    font-weight: 600;
  }

  .selector-arrow {
    color: #64748B;
    transition: transform 0.2s;
  }

  .selector-arrow.open {
    transform: rotate(180deg);
  }

  .selector-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    z-index: 50;
    overflow: hidden;
  }

  .selector-search {
    padding: 0.5rem;
    border-bottom: 1px solid #334155;
  }

  .selector-search input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: #0F172A;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #E2E8F0;
    font-size: 0.85rem;
  }

  .selector-search input:focus {
    outline: none;
    border-color: #FF6B00;
  }

  .selector-options {
    max-height: 240px;
    overflow-y: auto;
  }

  .selector-option {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.625rem 0.875rem;
    background: transparent;
    border: none;
    color: #E2E8F0;
    text-align: left;
    cursor: pointer;
    transition: background 0.15s;
  }

  .selector-option:hover {
    background: rgba(255, 107, 0, 0.1);
  }

  .selector-option.selected {
    background: rgba(255, 107, 0, 0.15);
  }

  .option-main {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .option-label {
    font-weight: 500;
  }

  .option-desc {
    font-size: 0.75rem;
    color: #64748B;
  }

  .selector-empty {
    padding: 1rem;
    text-align: center;
    color: #64748B;
    font-size: 0.85rem;
  }
</style>