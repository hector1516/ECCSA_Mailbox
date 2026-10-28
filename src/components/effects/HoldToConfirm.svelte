<!-- HoldToConfirm.svelte — Acción deliberada que se llena mientras se mantiene -->
<script lang="ts">
  interface Props {
    label?: string;
    confirmLabel?: string;
    duration?: number;
    disabled?: boolean;
    onconfirm?: () => void;
    variant?: 'danger' | 'warning' | 'primary';
  }

  let {
    label = 'Mantener para confirmar',
    confirmLabel = '¡Confirmado!',
    duration = 2000,
    disabled = false,
    onconfirm,
    variant = 'danger'
  }: Props = $props();

  let progress = $state(0);
  let isHolding = $state(false);
  let confirmed = $state(false);
  let intervalId: ReturnType<typeof setInterval> | null = null;
  let startTime = 0;

  function startHold() {
    if (disabled || confirmed) return;
    isHolding = true;
    progress = 0;
    startTime = Date.now();
    
    intervalId = setInterval(() => {
      const elapsed = Date.now() - startTime;
      progress = Math.min(100, (elapsed / duration) * 100);
      
      if (progress >= 100) {
        stopHold(true);
      }
    }, 16);
  }

  function stopHold(didConfirm = false) {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
    
    if (didConfirm) {
      confirmed = true;
      onconfirm?.();
      setTimeout(() => {
        confirmed = false;
        progress = 0;
      }, 1500);
    } else {
      isHolding = false;
      progress = 0;
    }
  }
</script>

<button
  class="hold-btn hold-{variant}"
  class:holding={isHolding}
  class:confirmed
  class:disabled
  {disabled}
  onpointerdown={startHold}
  onpointerup={() => stopHold(false)}
  onpointerleave={() => stopHold(false)}
  onpointercancel={() => stopHold(false)}
>
  <div class="hold-fill" style="width: {progress}%"></div>
  <div class="hold-content">
    {#if confirmed}
      <span class="hold-check">✓</span>
      {confirmLabel}
    {:else}
      <span class="hold-icon">⏳</span>
      {label}
    {/if}
  </div>
</button>

<style>
  .hold-btn {
    position: relative;
    width: 100%;
    padding: 0.875rem 1.25rem;
    border: 2px solid;
    border-radius: 12px;
    background: transparent;
    cursor: pointer;
    overflow: hidden;
    font-family: inherit;
    font-weight: 600;
    font-size: 0.95rem;
    transition: border-color 0.2s, color 0.2s;
    user-select: none;
    -webkit-user-select: none;
    touch-action: none;
  }

  .hold-btn.disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
  }

  .hold-fill {
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    transition: width 0.05s linear;
    z-index: 0;
  }

  .hold-content {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }

  .hold-check {
    font-size: 1.2rem;
    font-weight: 700;
  }

  /* Danger variant */
  .hold-danger {
    border-color: #DC2626;
    color: #DC2626;
  }
  .hold-danger .hold-fill {
    background: rgba(220, 38, 38, 0.2);
  }
  .hold-danger.holding {
    border-color: #EF4444;
    color: #EF4444;
  }
  .hold-danger.confirmed {
    border-color: #22C55E;
    color: #22C55E;
    background: rgba(34, 197, 94, 0.1);
  }

  /* Warning variant */
  .hold-warning {
    border-color: #F59E0B;
    color: #F59E0B;
  }
  .hold-warning .hold-fill {
    background: rgba(245, 158, 11, 0.2);
  }
  .hold-warning.holding {
    border-color: #FBBF24;
    color: #FBBF24;
  }
  .hold-warning.confirmed {
    border-color: #22C55E;
    color: #22C55E;
    background: rgba(34, 197, 94, 0.1);
  }

  /* Primary variant */
  .hold-primary {
    border-color: #FF6B00;
    color: #FF6B00;
  }
  .hold-primary .hold-fill {
    background: rgba(255, 107, 0, 0.2);
  }
  .hold-primary.holding {
    border-color: #FF8C33;
    color: #FF8C33;
  }
  .hold-primary.confirmed {
    border-color: #22C55E;
    color: #22C55E;
    background: rgba(34, 197, 94, 0.1);
  }
</style>