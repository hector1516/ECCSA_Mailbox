#!/usr/bin/env python3
"""
tools/test_firmas.py — pruebas de la lógica de firmas, firmas por token.

Por qué un archivo propio y no más casos en `test_sanitizador.py`: el
sanitizador prueba QUÉ HTML se acepta. Estas pruebas prueban una propiedad que
se rompe sin ningún error visible:

**Lo que se GUARDA lleva `cid:` y lo que se MUESTRA lleva URL.** Son dos cosas
distintas y ambas necesarias, porque el `cid:` no resuelve en el navegador (haría
falta la URL para pintar) y la URL no sirve para enviar (el destinatario no
resuelve `/api/sigimg/...`, y el worker convierte `cid:` en un adjunto inline
real, que es lo único que funciona en todos los clientes).

Cuando esa frontera se cruzó, el correo salía con la firma sin logo y sin ningún
error en ninguna parte: la URL se guardaba, el worker buscaba `cid:`, no
encontraba nada y mandaba el HTML tal cual.

Ejecución:  python3 tools/test_firmas.py
"""
import importlib.util
import os
import re
import sys
import types

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cargar_main():
    """Importa api/main.py con `pymssql` simulado.

    Igual que `test_sanitizador.py`: lo único que bloquea el import sin base de
    datos es `pymssql`. `fastapi` sí tiene que estar —está en requirements y
    check.yml lo instala—, porque main.py importa nombres concretos de ahí y
    simularlo no sirve de nada.
    """
    sys.modules.setdefault("pymssql", types.ModuleType("pymssql"))
    sys.path.insert(0, os.path.join(RAIZ, "api"))
    spec = importlib.util.spec_from_file_location(
        "mailbox_main_firmas", os.path.join(RAIZ, "api", "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _cargar_main()


class Base:
    """Nada; se usa como marca para el runner de abajo."""


fallos = []


def chk(nombre, condicion, detalle=""):
    if condicion:
        print(f"  ok     {nombre}")
    else:
        print(f"  FALLA  {nombre}   {detalle}")
        fallos.append(nombre)


print("\n=== cid -> URL para la vista previa ===")
# Dos imágenes de la firma 7, como si estuvieran en la base.
IMAGENES = [
    {"Cid": "f7-4242@eccsa", "Token": "aaaabbbbccccddddeeeeffff00001111"},
    {"Cid": "logo@eccsa", "Token": "11112222333344445555666677778888"},
]
M._filas = lambda sql, params=(): (IMAGENES if params == (7,) else [])

chk("reemplaza el cid de la firma",
    M._cid_a_url('<img src="cid:f7-4242@eccsa">', 7)
    == '<img src="/api/sigimg/aaaabbbbccccddddeeeeffff00001111">')
chk("reemplaza un segundo cid",
    M._cid_a_url('<img src="cid:logo@eccsa">', 7)
    == '<img src="/api/sigimg/11112222333344445555666677778888">')
chk("reemplaza todos los cid de golpe",
    "cid:" not in M._cid_a_url(
        '<img src="cid:f7-4242@eccsa"><img src="cid:logo@eccsa">', 7))

print("\n=== lo que NO debe tocar ===")
chk("un cid inventado se deja como estaba",
    M._cid_a_url('<img src="cid:inventado">', 7) == '<img src="cid:inventado">',
    "no se puede pedir una imagen de otra firma")
chk("otra firma no se mezclada",
    M._cid_a_url('<img src="cid:f7-4242@eccsa">', 99) == '<img src="cid:f7-4242@eccsa">')
chk("sin firma no reescribe",
    M._cid_a_url('<img src="cid:f7-4242@eccsa">', None) == '<img src="cid:f7-4242@eccsa">')
chk("html sin imagenes pasa intacto",
    M._cid_a_url("<p>Saludos</p>", 7) == "<p>Saludos</p>")
chk("html vacio no revienta", M._cid_a_url("", 7) == "")

print("\n=== el cid que genera el servidor ===")
# `_cid_para` es lo que decide el token del Content-ID. Si dos firmas con una
# imagen del mismo nombre generaran el MISMO cid, al enviar se pisarían: ambas
# partes MIME se llamarían igual y el cliente mostraría una sola imagen.
cid_a = M._cid_para(7, "logo.png")
cid_b = M._cid_para(8, "logo.png")
cid_c = M._cid_para(7, "otro.png")
chk("dos firmas distintas con el mismo archivo dan cid distintos",
    cid_a != cid_b, f"{cid_a} vs {cid_b}")
chk("dentro de una firma archivos distintos dan cid distintos",
    cid_a != cid_c)
chk("es estable (misma firma + archivo = mismo cid)",
    cid_a == M._cid_para(7, "logo.png"))
chk("acepta el formato que valida el sanitizador",
    re.match(r"^cid:[a-z0-9._%+@-]{1,200}$", f"cid:{cid_a}") is not None,
    f"cid:{cid_a}")
chk("no se valida el nombre con caracteres raros",
    re.match(r"^cid:[a-z0-9._%+@-]{1,200}$", f"cid:{M._cid_para(7, 'a b.png')}")
    is not None, "el sanitizer rechazaria este y la subida fallaria")

print("\n=== el html que devuelve la subida de imagen ===")
# Debe llevar SIEMPRE cid: y NUNCA la URL. Es lo que se inserta en el editor y
# lo que se guarda.
cid = M._cid_para(7, "logo.png")
html = f'<img src="cid:{cid}" alt="{("logo.png").replace(chr(34), "")}">'
chk("el html lleva cid:", f'src="cid:{cid}"' in html)
chk("el html NO lleva /api/sigimg", "/api/sigimg" not in html)

print("\n=== el sanitizador deja pasar el cid, no una URL con javascript ===")
chk("acepta cid:",
    M._ESQUEMAS_OK[3] == "cid:", M._ESQUEMAS_OK)
chk("rechaza javascript como cid",
    M._ESQUEMAS_OK[0] != "javascript:")
limpio = M._sanitizar_html('<img src="cid:logo@eccsa"><img src="cid:javascript:alert(1)">')
chk("el cid malicioso se elimina y el bueno se queda",
    "cid:logo@eccsa" in limpio and "javascript" not in limpio,
    limpio[:120])

print("\n" + "=" * 70)
if fallos:
    print(f"FALLARON {len(fallos)}: {', '.join(fallos)}")
    sys.exit(1)
print("OK · todos los casos")