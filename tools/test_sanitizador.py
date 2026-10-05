#!/usr/bin/env python3
"""
tools/test_sanitizador.py — pruebas del sanitizador de HTML de firmas.

Por qué existe: el sanitizador es la frontera de seguridad del módulo de
firmas. El HTML que guarda pasa a formar parte del correo que sale de la
empresa, y si deja pasar un `<script>` o un `javascript:` la app se convierte
en un vector de envío de phishing a todo el que tiene una firma.

Son 24 casos y NO necesitan base de datos ni servidor: se importa el módulo
con `pymssql` simulado, que es lo único que main.py importa al cargar.

Ejecución:
    python tools/test_sanitizador.py

Sale 1 si algún caso falla, para poder engancharlo a check.yml.
"""
import importlib.util
import os
import sys
import types

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cargar_main():
    """Importa api/main.py con pymssql simulado.

    El sanitizador es código puro de la stdlib: si hay que probarlo sin base de
    datos, se simula lo único que lo bloquea al importar.
    """
    sys.modules.setdefault("pymssql", types.ModuleType("pymssql"))
    sys.path.insert(0, os.path.join(RAIZ, "api"))
    spec = importlib.util.spec_from_file_location(
        "mailbox_main", os.path.join(RAIZ, "api", "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MB = _cargar_main()

# (nombre, entrada, [fragmentos que NO deben aparecer en la salida])
PELIGROSOS = [
    "script", "javascript:", "onerror", "onclick", "onload", "<iframe",
    "<style", "<svg", "<form", "<input", "<base", "<meta", "expression(",
    "data:", "vbscript:", "-moz-binding", "@import",
]

# (nombre, entrada, [fragmentos que SÍ deben aparecer])
VALIDOS = [
    ("basico",      "<p>Hola <b>mundo</b></p>",                    ["<b>", "Hola"]),
    ("tabla",       '<table><tr><td align="center">c</td></tr></table>', ["<table>", 'align="center"']),
    ("cid",         '<img src="cid:logo@ecc-sa" width="120">',     ["cid:logo@ecc-sa", 'width="120"']),
    ("link",        '<a href="https://ecc-sa.com.mx">web</a>',    ["https://ecc-sa.com.mx"]),
    ("mailto",      '<a href="mailto:a@ecc-sa.com.mx">m</a>',    ["mailto:a@ecc-sa.com.mx"]),
    ("ancla",       '<a href="#fin">ir</a>',                       ['href="#fin"']),
    ("acentos",     "<p>Saludos, Juan Ñuñez Áñez</p>",            ["Ñuñez", "Áñez"]),
    ("style_bueno", '<div style="color:#FF6B00;font-weight:bold">x</div>', ["color:#FF6B00"]),
    ("tabla_ancho", '<table width="100%" cellpadding="0"><tr><td>x</td></tr></table>', ['width="100%"', 'cellpadding="0"']),
    ("lista",       "<ul><li>uno</li><li>dos</li></ul>",          ["<ul>", "<li>"]),
]


def _hay_peligro(salida: str) -> list:
    baja = salida.lower()
    return [p for p in PELIGROSOS if p in baja]


def main() -> int:
    fallos = 0

    print("=" * 72)
    print("Mailbox · sanitizador de firmas")
    print("=" * 72)

    print("\n[1] Vectores que deben quedar NEUTRALIZADOS")
    casos_malos = [
        ("script",            "<script>alert(1)</script><p>ok</p>"),
        ("onerror",           "<img src=x onerror=alert(1)>"),
        ("js href",           '<a href="javascript:alert(1)">x</a>'),
        ("js con tab",        '<a href="jav&#x09;ascript:alert(1)">x</a>'),
        ("js con entity",     '<a href="&#106;avascript:alert(1)">x</a>'),
        ("css url js",        '<div style="background:url(javascript:alert(1))">x</div>'),
        ("css expression",    '<div style="width:expression(alert(1))">x</div>'),
        ("css moz-binding",   '<div style="-moz-binding:url(http://evil)">x</div>'),
        ("css import",        '<div style="@import url(http://evil)">x</div>'),
        ("iframe",            '<iframe src="http://evil"></iframe><p>ok</p>'),
        ("style",             "<style>body{display:none}</style><p>ok</p>"),
        ("form",              '<form action=x><input name=y></form><p>ok</p>'),
        ("svg",               "<svg onload=alert(1)><circle/></svg><p>ok</p>"),
        ("base",              '<base href="http://evil">'),
        ("meta refresh",      '<meta http-equiv=refresh content="0;url=evil">'),
        ("data uri svg",      '<img src="data:image/svg+xml,<svg onload=alert(1)>">'),
        ("onclick",           '<p onclick="alert(1)">t</p>'),
        ("objeto",            '<object data="http://evil"></object><p>ok</p>'),
        ("cid malicioso",     '<img src="cid:javascript:alert(1)">'),
        ("script sin cerrar", "<script>var x = '</p><script>alert(1)"),
    ]
    for nombre, entrada in casos_malos:
        salida = MB._sanitizar_html(entrada)
        restos = _hay_peligro(salida)
        if restos:
            print(f"  FALLA  {nombre:20} dejó pasar: {restos}")
            print(f"         entrada: {entrada}")
            print(f"         salida:  {salida}")
            fallos += 1
        else:
            print(f"  ok     {nombre:20} → {salida[:44]}")

    print("\n[2] HTML legítimo que debe SOBREVIVIR intacto")
    for nombre, entrada, esperados in VALIDOS:
        salida = MB._sanitizar_html(entrada)
        faltan = [e for e in esperados if e not in salida]
        if faltan:
            print(f"  FALLA  {nombre:20} perdió: {faltan}")
            print(f"         entrada: {entrada}")
            print(f"         salida:  {salida}")
            fallos += 1
        else:
            print(f"  ok     {nombre:20} → {salida[:44]}")

    print("\n[3] Texto plano (fallback para clientes sin HTML)")
    t1 = MB._a_texto_plano("<p>Saludos,</p><p><b>Juan</b></p><style>x{}</style>")
    t2 = MB._a_texto_plano("<table><tr><td>A</td><td>B</td></tr></table>")
    if "Juan" not in t1 or "x{}" in t1:
        print(f"  FALLA  texto plano con style: {t1!r}")
        fallos += 1
    else:
        print(f"  ok     descarta contenido de <style> → {t1!r}")
    if t2 != "A\nB":
        print(f"  FALLA  texto plano de tabla: {t2!r}")
        fallos += 1
    else:
        print(f"  ok     celdas de tabla → {t2!r}")

    print("\n[4] HTML roto no debe guardar nada a medias")
    for nombre, entrada in [("vacío", ""), ("nulo", None), ("sin cerrar", "<p><b>sin cierre")]:
        salida = MB._sanitizar_html(entrada)
        if salida is None:
            print(f"  FALLA  {nombre}: devolvió None en vez de str")
            fallos += 1
        else:
            print(f"  ok     {nombre:12} → {str(salida)[:44]!r}")

    print("\n" + "=" * 72)
    total = len(casos_malos) + len(VALIDOS) + 5
    if fallos:
        print(f"FALLARON {fallos} de {total}")
        return 1
    print(f"OK · {total} casos")
    return 0


if __name__ == "__main__":
    sys.exit(main())