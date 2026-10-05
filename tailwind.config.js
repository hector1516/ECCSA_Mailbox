/** @type {import('tailwindcss').Config} */
// Paleta de ECCSA. Los MISMOS valores viven como tokens en el CSS del shell
// (ECCSA-Shell/tokens.css): esto es la copia que Tailwind v3 necesita para
// poder usar clases como `bg-surface` o `text-muted`. Si se cambia un color,
// se cambia en el shell y se propaga; editar esto a mano rompe la paridad.
module.exports = {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{html,js,svelte,ts}',
  ],
  theme: {
    extend: {
      colors: {
        dark: '#0F172A',
        surface: '#1E293B',
        primary: '#FF6B00',
        secondary: '#FFAE00',
        text: '#F8FAFC',
        muted: '#64748B',
        accent: '#FFB400',
      }
    }
  },
  plugins: []
}
