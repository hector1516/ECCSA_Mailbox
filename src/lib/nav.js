/* ECCSA-Shell — nav.js (skin: ingram) — store compartido para visibilidad de nav y banner */
import { writable } from 'svelte/store';

export const navVisible = writable(true);
export const currentModule = writable('');