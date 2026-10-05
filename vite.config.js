import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// SPA plano (sin SvelteKit), igual que Admon: index.html -> src/main.js -> App.svelte.
// La razon de NO usar SvelteKit es el costo del router de archivos para una app
// de este tamaño, y que `adapter-static` mete una capa de prerender que aqui no
// se usa: todas las rutas las decide el cliente.
export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: {
      $lib: '/src/lib'
    }
  },
  server: {
    host: true,
    port: 5174
  },
  build: {
    outDir: 'dist'
  }
});
