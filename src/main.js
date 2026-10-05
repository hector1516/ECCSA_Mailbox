import './styles/app.css';
import { mount } from 'svelte';
import App from './App.svelte';

// Svelte 5: los componentes compilan a funciones, NO a clases.
// `new App(...)` lanza effect_orphan y deja la página en blanco;
// se monta con `mount()`, que crea el contexto de efectos. (Mismo comentario que
// en Admon: son las dos el mismo error y cuesta encontrarlo.)
const app = mount(App, {
  target: document.getElementById('app')
});

export default app;