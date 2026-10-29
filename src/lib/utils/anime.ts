// anime.ts — Wrapper para anime.js (adaptado para Svelte 5)
// Uso: import { animate } from '$lib/utils/anime';
// o: import { animate, stagger } from '$lib/utils/anime';

import anime from 'animejs';

export { anime };
export const stagger = anime.stagger;

// Helper para animar elementos con anime.js en Svelte
export function animateElement(
  target: string | Element | Element[],
  properties: Record<string, any>,
  options: Record<string, any> = {}
): anime.AnimeInstance {
  return anime({
    targets: target,
    ...properties,
    ...options
  });
}

// Helper para animar al montar un componente
export function animateOnMount(
  node: Element,
  properties: Record<string, any>,
  options: Record<string, any> = {}
): anime.AnimeInstance {
  return anime({
    targets: node,
    ...properties,
    ...options
  });
}

// Presets comunes
export const presets = {
  fadeIn: { opacity: [0, 1], translateY: [20, 0], duration: 600, easing: 'easeOutExpo' },
  fadeOut: { opacity: [1, 0], translateY: [0, -20], duration: 400, easing: 'easeInExpo' },
  slideInLeft: { translateX: [-50, 0], opacity: [0, 1], duration: 600, easing: 'easeOutExpo' },
  slideInRight: { translateX: [50, 0], opacity: [0, 1], duration: 600, easing: 'easeOutExpo' },
  bounceIn: { scale: [0, 1], opacity: [0, 1], duration: 800, easing: 'easeOutElastic(1, .5)' },
  pulse: { scale: [1, 1.05, 1], duration: 600, easing: 'easeInOutSine' },
  shake: { translateX: [-5, 5, -5, 5, 0], duration: 400, easing: 'easeInOutSine' }
};