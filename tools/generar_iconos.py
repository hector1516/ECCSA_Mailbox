#!/usr/bin/env python3
"""
tools/generar_iconos.py — genera TODOS los assets del logo de Mailbox.

El logo de origen trae el globo y la palabra "Mail" en un solo PNG, con el
contenido metido en el centro de un lienzo grande. Para los iconos del PWA eso
no sirve: un icono tiene que ser cuadrado y el texto se corta en los recortes
redondeados de Android e iOS. Este script parte el logo en dos piezas y genera
el set completo.

Las dos piezas
--------------
  marca   = solo el globo. Es la que va en TODOS los iconos del PWA y en el
            chip de 34px del header, donde un texto seria ilegible.
  lockup  = globo + "Mail". Va en el splash (128px de ancho) y en la pantalla
            de inicio del PWA en iPhone, donde hay sitio y el nombre importa.

Por que esta separacion es automatica y no dos archivos
-------------------------------------------------------
El corte se saca del propio PNG: se recorren las filas con contenido y se busca
el hueco horizontal mas grande. El "Mail" esta separado del globo por una banda
de ~12 filas completamente vacias, asi que el corte cae solo y en el lugar
correcto. Si manana el logo llega con otro diseno, este script sigue funcionando
mientras haya un hueco visible entre el icono y el texto.

Uso
---
    python tools/generar_iconos.py                       # usa ../Mail/IMG_0417.PNG
    python tools/generar_iconos.py otro.png              # otro origen
    python tools/generar_iconos.py --salida /tmp/prueba # otra carpeta

Salidas
-------
    public/mailbox_logo.png     lockup, fondo transparente (splash + header)
    public/mailbox_marca.png    marca, cuadrado, fondo transparente
    public/icons/icon-*.png     120 / 152 / 167 / 180 / 192 / 512
    public/icons/icon-512-maskable.png   Android: marca al 62% (safe zone)
    public/apple-touch-icon.png  180, SIN alfa (iOS no respeta transparencia)
    public/favicon.ico          16 / 32 / 48

Calidad de imagen (LEELO antes de quejarse de que se ve borroso)
-----------------------------------------------------------------
El logo de origen tiene el contenido real en ~210x255 px dentro de un lienzo de
578x432. Ampliar eso a 512 px es un factor de ~2.4, asi que los iconos grandes
se ven suaves por mas que se use LANCZOS. Se compensa con UnsharpMask, pero el
limite es la fuente: si hay un original mas grande (SVG, o PNG de 1024+), este
script lo usa tal cual y el salto de calidad es notorio. Basta con volver a
correrlo apuntando al archivo mejor:

    python tools/generar_iconos.py /ruta/al/logo_grande.png
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

# ── Constantes ────────────────────────────────────────────────────────────────
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ORIGEN_POR_DEFECTO = os.path.join(os.path.dirname(RAIZ), "Mail", "IMG_0417.PNG")

# Fondo de los iconos donde el formato NO admite transparencia.
# iOS pinta el alfa de un apple-touch-icon como negro, y el icono va pegado
# sobre el springboard: negro debajo de #0F172A se nota como un marco sucio.
# Con el fondo del tema, el icono se ve nativo.
FONDO_OPACO = (15, 23, 42)        # --color-bg de ECCSA-Shell

TAMANOS = [120, 152, 167, 180, 192, 512]

# Cuanto del lienzo ocupa la marca en un icono "normal" (square, sin maskable).
# Con 0.86 el globo queda grande pero respira; el shell usa .module-card de
# 130px de alto, y un logo al 100% se veria pegado al borde al recortarse.
RELLENO_ICONO = 0.86

# Android recorta los iconos maskable a un circulo con un safe zone del 80%.
# El contenido debe caber dentro de ese circulo, no del cuadrado: por eso el
# 62% en vez de 0.86. Es el valor que usa Chrome en su propio generador.
RELLENO_MASKABLE = 0.62


# ── Analisis del PNG de origen ─────────────────────────────────────────────────
def _bbox_contenido(im, alpha_min=20):
    """Caja que envuelve todo lo que tiene alfa visible."""
    alfa = im.getchannel("A")
    mascara = alfa.point(lambda v: 255 if v > alpha_min else 0)
    caja = mascara.getbbox()
    if caja is None:
        raise SystemExit("ERROR: el PNG de origen esta completamente vacio.")
    return caja


def _corte_horizontal(im, caja):
    """
    Separa la marca del texto buscando el mayor hueco de filas vacias.

    Devuelve (y_fin_de_la_marca, y_inicio_del_texto). Si NO encuentra un hueco
    claro, devuelve None y el llamador usa el recorte completo: es preferible
    un icono con el texto sin recortar que un corte a la mitad del globo.
    """
    x0, y0, x1, y1 = caja
    ancho = x1 - x0 + 1
    filas_vacias = []
    mejor = None

    for y in range(y0, y1 + 1):
        vacias = 0
        for x in range(x0, x1 + 1):
            if im.getpixel((x, y))[3] <= 20:
                vacias += 1
        if vacias >= ancho * 0.95:          # fila practicamente vacia
            filas_vacias.append(y)
        elif filas_vacias:
            # El hueco termino: si es el mas grande hasta ahora, es el corte.
            alto = y - filas_vacias[0]
            if mejor is None or alto > mejor[1]:
                mejor = (filas_vacias[0], alto)
            filas_vacias = []

    if mejor is None or mejor[1] < 4:
        return None
    inicio, alto = mejor
    # El texto empieza despues del hueco; la marca termina antes.
    return (inicio - 1, inicio + alto)


def _recortar(im, caja):
    """Recorta a la caja y devuelve una copia."""
    return im.crop(caja)


def _ajustar(im, lado, relleno):
    """
    Escala la pieza a un cuadrado de `lado` con el relleno pedido, centrado.
    LANCZOS + realce: el origen es chico y sin esto los iconos grandes se ven
    como_MANCHAS_ mas que vectores.
    """
    lado_efectivo = max(1, int(lado * relleno))
    escala = lado_efectivo / max(im.size)
    nuevo = (max(1, int(im.size[0] * escala)), max(1, int(im.size[1] * escala)))

    escalada = im.resize(nuevo, Image.LANCZOS)
    # El realce solo cuando estamos ENAMPLIANDO: reducir una imagen grande ya
    # nitida con UnsharpMask solo le mete ringing.
    if escala > 1:
        escalada = escalada.filter(
            ImageFilter.UnsharpMask(radius=2.0, percent=80, threshold=3)
        )

    lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    lienzo.paste(escalada, ((lado - nuevo[0]) // 2, (lado - nuevo[1]) // 2))
    return lienzo


def _sobre_fondo(im, color):
    """Pega la imagen RGBA sobre un fondo opaco (para iOS y el favicon)."""
    fondo = Image.new("RGB", im.size, color)
    fondo.paste(im, (0, 0), im)
    return fondo


# ── Generacion ────────────────────────────────────────────────────────────────
def generar(origen, salida):
    if not os.path.isfile(origen):
        raise SystemExit(
            f"ERROR: no existe el logo de origen:\n  {origen}\n"
            f"Pasalo como argumento: python tools/generar_iconos.py <ruta.png>"
        )

    im = Image.open(origen).convert("RGBA")
    caja = _bbox_contenido(im)
    x0, y0, x1, y1 = caja
    print(f"origen: {origen}")
    print(f"  lienzo  {im.size[0]}x{im.size[1]}   contenido {x1-x0+1}x{y1-y0+1}")

    corte = _corte_horizontal(im, caja)
    if corte:
        y_marca_fin, y_texto_ini = corte
        print(f"  corte detectado: marca hasta y={y_marca_fin}, texto desde y={y_texto_ini}")

        # Marca: recorta arriba hasta el corte y vuelve a ajustar el lado.
        marca = _recortar(im, (x0, y0, x1, y_marca_fin))
        mb = _bbox_contenido(marca)
        marca = marca.crop(mb)

        # Lockup: el recorte completo, que ya incluye el texto.
        lockup = im.crop(caja)
    else:
        print("  SIN hueco detectable: se usa el recorte completo como marca.")
        print("  (si el logo tiene texto debajo del icono, separalo a mano)")
        marca = lockup = im.crop(caja)

    print(f"  marca  {marca.size[0]}x{marca.size[1]}   lockup {lockup.size[0]}x{lockup.size[1]}")

    # --- Logo principal (splash + chip del header) --------------------------
    # VA EN public/, no en la raíz del repo: Vite solo copia public/* al dist/,
    # y un PNG en la raíz no aparece en la build. El HTML lo pide como
    # /mailbox_logo.png, que es la ruta que resuelve tanto en dev como en dist.
    #
    # Se guarda con 4 px de aire: el header lo pinta en 34x34 con object-fit
    # cover, y sin margen el borde del arte se ve pegado a la esquina.
    PAD = 4
    dir_public = os.path.join(salida, "public")
    os.makedirs(dir_public, exist_ok=True)

    lockup_out = Image.new("RGBA", (lockup.size[0] + PAD * 2, lockup.size[1] + PAD * 2), (0, 0, 0, 0))
    lockup_out.paste(lockup, (PAD, PAD))
    _guardar(lockup_out, os.path.join(dir_public, "mailbox_logo.png"))

    marca_out = Image.new("RGBA", (marca.size[0] + PAD * 2, marca.size[1] + PAD * 2), (0, 0, 0, 0))
    marca_out.paste(marca, (PAD, PAD))
    _guardar(marca_out, os.path.join(dir_public, "mailbox_marca.png"))

    # --- Iconos del PWA -----------------------------------------------------
    dir_icons = os.path.join(salida, "public", "icons")
    os.makedirs(dir_icons, exist_ok=True)

    for lado in TAMANOS:
        icono = _ajustar(marca, lado, RELLENO_ICONO)
        if lado == 180:
            # El de 180 es el apple-touch-icon de iOS: sin alfa, sobre el fondo
            # del tema. iOS NO respeta la transparencia de este archivo.
            _guardar(_sobre_fondo(icono, FONDO_OPACO),
                     os.path.join(dir_icons, f"icon-{lado}x{lado}.png"))
        else:
            _guardar(icono, os.path.join(dir_icons, f"icon-{lado}x{lado}.png"))

    maskable = _ajustar(marca, 512, RELLENO_MASKABLE)
    _guardar(maskable, os.path.join(dir_icons, "icon-512-maskable.png"))

    # --- Apple touch icon + favicon (sin alfa) ------------------------------
    apple = _sobre_fondo(_ajustar(marca, 180, RELLENO_ICONO), FONDO_OPACO)
    _guardar(apple, os.path.join(salida, "public", "apple-touch-icon.png"))

    favicon_base = _sobre_fondo(_ajustar(marca, 64, RELLENO_ICONO), FONDO_OPACO)
    favicon_base.save(
        os.path.join(salida, "public", "favicon.ico"),
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    print(f"  favicon.ico 16/32/48 sobre {FONDO_OPACO}")

    print("\nOK. Archivos generados:")
    for nombre in ("public/mailbox_logo.png", "public/mailbox_marca.png"):
        print(f"  {nombre}")
    print(f"  public/icons/icon-{'_'.join(map(str, TAMANOS))}.png")
    print("  public/icons/icon-512-maskable.png")
    print("  public/apple-touch-icon.png")
    print("  public/favicon.ico")


def _guardar(im, ruta):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    im.save(ruta, format="PNG", optimize=True)
    kb = os.path.getsize(ruta) / 1024
    print(f"  {os.path.relpath(ruta, RAIZ):44} {im.size[0]}x{im.size[1]:<5} {kb:6.1f} KB")


def main():
    ap = argparse.ArgumentParser(description="Genera los iconos de Mailbox desde el logo.")
    ap.add_argument("origen", nargs="?", default=ORIGEN_POR_DEFECTO,
                    help=f"PNG de origen (default: {ORIGEN_POR_DEFECTO})")
    ap.add_argument("--salida", default=RAIZ, help="carpeta raíz del repo")
    args = ap.parse_args()

    print("=" * 62)
    print("ECCSA_Mailbox · generar iconos")
    print("=" * 62)
    generar(args.origen, args.salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())