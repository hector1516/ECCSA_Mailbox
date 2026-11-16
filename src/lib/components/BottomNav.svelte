<!-- BottomNav — skin: ingram -->
<script>
  import { onMount, onDestroy } from 'svelte';
  import { path, navigate } from '$lib/router.js';
  import { ArrowLeft, Home, Search, Trophy, User } from 'lucide-svelte';

  let navVisible = $state(true);
  let lastScrollY = 0;
  let ticking = false;

  function handleScroll() {
    if (!ticking) {
      requestAnimationFrame(() => {
        const currentScrollY = window.scrollY;
        if (currentScrollY > lastScrollY + 50) {
          navVisible = false;
        } else if (currentScrollY < lastScrollY) {
          navVisible = true;
        }
        lastScrollY = currentScrollY;
        ticking = false;
      });
      ticking = true;
    }
  }

  onMount(() => {
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  });

  const items = [
    { icon: ArrowLeft, label: 'Atras', action: () => { if (window.history.length > 1) history.back(); else navigate('/dashboard'); } },
    { icon: Home, label: 'Inicio', action: () => navigate('/dashboard') },
    { icon: Search, label: 'Buscar', action: () => navigate('/busqueda') },
    { icon: Trophy, label: 'Legends', action: () => navigate('/legends') },
    { icon: User, label: 'Perfil', action: () => navigate('/perfil') },
  ];

  function isActive(item) {
    const p = $path;
    if (item.label === 'Inicio') return p === '/dashboard' || p === '/' || p === '';
    if (item.label === 'Legends') return p === '/legends';
    if (item.label === 'Buscar') return p === '/busqueda';
    if (item.label === 'Perfil') return p === '/perfil';
    return false;
  }
</script>

<nav class="bottom-nav" class:hidden={!navVisible} class:visible={navVisible}>
  {#each items as item}
    <button class="nav-item" class:active={isActive(item)} onclick={item.action} aria-label={item.label}>
      <svelte:component this={item.icon} size={20} />
    </button>
  {/each}
</nav>