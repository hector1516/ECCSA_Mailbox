#!/usr/bin/env bash
# tools/prueba_visual/capturar.sh — renderiza home.html y guarda captura.png.
#
# Para qué: `.module-card` / `.module-badge` / los colores los define el
# ECCSA-Shell y no se editan en la app. Verificar el look real sin desplegar
# evita dos cosas: subir un cambio de CSS a ciegas, y tener que reinstalar la
# PWA en un iPhone para ver si un contador quedó bien.
#
# Requiere chromium (o chromium-browser). Si no está, el script lo dice y sale
# 0: es una herramienta de desarrollo, no un gate de CI.
#
#   bash tools/prueba_visual/capturar.sh [ancho] [alto] [salida]
#
# El ancho es lo importante: el shell cambia el número de columnas por resolución
# (2 <560 · 3 ≥560 · 4 ≥900 · 5 ≥1280), así que la MISMA página se ve distinta en
# cada corte y hay que capturar los tres:
#
#   bash tools/prueba_visual/capturar.sh 430    # iPhone, 2 columnas
#   bash tools/prueba_visual/capturar.sh 900    # tablet, 4 columnas
#   bash tools/prueba_visual/capturar.sh 1440   # escritorio, 5 columnas
#
# Default: 430x1900.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$AQUI/../.." && pwd)"
ANCHO="${1:-430}"
ALTO="${2:-1900}"
SALIDA="${3:-$AQUI/captura-$(printf '%s' "$ANCHO" | sed 's/$/px/').png}"

cd "$REPO"

# ── El CSS que se prueba es el COMPILADO ──────────────────────────────────────
# No sirve src/styles/app.css: es la fuente con las directivas @tailwind de
# Tailwind v3, que el navegador no entiende. Hay que compilar primero.
CSS="$(ls dist/assets/index-*.css 2>/dev/null | head -1 || true)"
if [ -z "$CSS" ]; then
	echo "ERROR: no hay dist/. Compilá primero:"
	echo "  npm install && npm run build"
	exit 1
fi

# Se parchea el <link> del HTML con el hash real del bundle. El HTML lleva un
# XXXXXXXX de placeholder justamente para que quede claro que es un archivo
# generado y no algo que se pueda abrir directo en el navegador.
REL="${CSS#dist/}"
python3 - "$REL" <<'PY'
import re, sys
rel = sys.argv[1]
p = "tools/prueba_visual/home.html"
s = open(p, encoding="utf-8").read()
s = re.sub(r'href="\.\./\.\./dist/assets/index-[^"]+\.css"',
           f'href="../../dist/{rel}"', s)
open(p, "w", encoding="utf-8").write(s)
print(f"CSS: {rel}")
PY

# ── chromium ────────────────────────────────────────────────────────────────
BIN=""
for c in chromium chromium-browser google-chrome google-chrome-stable; do
	if command -v "$c" >/dev/null 2>&1; then BIN="$c"; break; fi
done
if [ -z "$BIN" ]; then
	echo "AVISO: no encontré chromium; me salto la captura."
	echo "       instalalo con: apt-get install -y chromium"
	exit 0
fi

echo "Renderizando ${ANCHO}x${ALTO}…"
# --force-device-scale-factor=2 para que el texto se vea al tamaño real de una
# pantalla retina y se pueda juzgar la legibilidad del contador.
"$BIN" \
	--headless \
	--no-sandbox \
	--disable-gpu \
	--hide-scrollbars \
	--force-device-scale-factor=2 \
	--window-size="${ANCHO},${ALTO}" \
	--screenshot="$SALIDA" \
	"file://$AQUI/home.html" 2>/dev/null || true

if [ -f "$SALIDA" ]; then
	echo "OK → ${SALIDA#$REPO/} ($(du -h "$SALIDA" | cut -f1))"
else
	echo "ERROR: chromium no produjo la captura"
	exit 1
fi