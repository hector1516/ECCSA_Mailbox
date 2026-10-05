#!/usr/bin/env python3
"""
tools/test_migraciones.py — pruebas del troceado de los `.sql`.

Por qué este archivo existe: `GO` es un separador de **lotes** del SSMS y de
`sqlcmd`, no es SQL. `pymssql` lo manda al servidor tal cual y el servidor
contesta `Incorrect syntax near 'GO'`. O sea: sin trocear, NINGUNA de las
migraciones de Mailbox es aplicable, y eso no se ve hasta que se corre el runner
en una base real.

Peor: el fallo se descubre tarde y parece un problema de SQL. Un archivo que se
parte mal se aplica a medias, y una migración a medias deja la base en un estado
que ninguna otra sabe reparar.

Los casos usan las formas que aparecen de verdad en estos archivos: `GO` a secas,
`GO` con espacios, dos `GO` seguidos, y el `GO` dentro de un literal de SQL (que
NO es separador y partirlo ahí rompe la sentencia).

Ejecución:  python3 tools/test_migraciones.py
"""
import importlib.util
import os
import re
import sys


def _sin_comentarios_ni_textos(sql: str) -> str:
    """
    El lote sin comentarios ni literales, para contar paréntesis de verdad.

    Hace falta porque un paréntesis en un comentario o en un string no es una
    sentencia mal cerrada: `Incorrect syntax near '('` aparece justamente como
    texto entre comillas en el comentario que explica ese error, y el conteo
   ="… abre 6, cierra 5…" sin que haya nada que arreglar. Se señaló un falso positivo
    exactamente así.
    """
    sin_comentarios = re.sub(r"--[^\n]*", "", sql)
    # Los literales con comillas simples se vacían; los '' (comilla escapada) se
    # respetan para no partir un string en el punto equivocado.
    return re.sub(r"'(?:''|[^'])*'", "''", sin_comentarios)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "am", os.path.join(RAIZ, "apply_migrations.py"))
am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(am)


fallos = []


def chk(nombre, condicion, detalle=""):
    if condicion:
        print(f"  ok     {nombre}")
    else:
        print(f"  FALLA  {nombre}   {detalle}")
        fallos.append(nombre)


print("\n=== trocear(): GO es separador de lotes, no SQL ===")
CASOS = [
    ("GO\nSELECT 1", 1, "GO al principio"),
    ("SELECT 1\nGO\nSELECT 2", 2, "GO entre dos sentencias"),
    ("SELECT 1\nGO\nSELECT 2\nGO\n", 2, "GO final no genera un lote vacío"),
    ("SELECT 1\nGO\nGO\nSELECT 2", 2, "dos GO seguidos no generan lote vacío"),
    ("  go  \nSELECT 1", 1, "GO en minúsculas y con espacios"),
    ("\tGO\t\nSELECT 1", 1, "GO con tabuladores"),
    ("SELECT 1\nGO 5\nSELECT 2", 2, "GO 5 se parte como separador (avisa)"),
]
for sql, esperado, nota in CASOS:
    chk(nota, len(am.trocear(sql)) == esperado,
        f"obtuvo {len(am.trocear(sql))}, esperaba {esperado}")

print("\n=== lo que NO es un separador ===")
chk("GO dentro de un literal no parte",
    len(am.trocear("SELECT 'GO' AS x")) == 1)
chk("GOO no es GO", len(am.trocear("SELECT 1\nGOO\nSELECT 2")) == 1)
chk("GOTO no es GO", len(am.trocear("SELECT 1\nGOTO etiqueta\nSELECT 2")) == 1)
chk("comentario que empieza con GO no parte",
    len(am.trocear("SELECT 1\n-- GO aqui\nSELECT 2")) == 1)

print("\n=== lotes vacíos y de solo comentarios ===")
chk("archivo vacío → 0 lotes", len(am.trocear("")) == 0)
chk("solo espacios → 0 lotes", len(am.trocear("   \n\n  ")) == 0)
chk("lote de solo comentarios se descarta",
    len(am.trocear("-- nada que ejecutar\nGO\n")) == 0)
chk("contenido real entre comentarios sí se queda",
    len(am.trocear("PRINT 'x'\nGO\n-- comentario\nGO\nPRINT 'y'\nGO\n")) == 2)

print("\n=== los archivos de este repo se trocean ===")
import glob
for ruta in sorted(glob.glob(os.path.join(RAIZ, "migrations", "*.sql"))):
    nombre = os.path.basename(ruta)
    with open(ruta, encoding="utf-8") as fh:
        sql = fh.read()
    lotes = am.trocear(sql)
    chk(f"{nombre} produce lotes", len(lotes) > 0, "quedó en 0 lotes")

    # Ningún lote puede quedar con un `GO` sin partir: si aparece, es que el
    # regex no lo vio y el servidor lo va a rechazar.
    con_go = [i + 1 for i, l in enumerate(lotes)
              if any(am._GO_RE.match(x) for x in l.splitlines())]
    chk(f"{nombre} ningún lote conserva un GO", not con_go, f"lotes {con_go}")

    # Y ningún lote debe quedar con una sentencia sin cerrar, que es el síntoma
    # de haber partido en el lugar equivocado.
    for i, lote in enumerate(lotes):
        limpio = _sin_comentarios_ni_textos(lote)
        if limpio.count("(") != limpio.count(")"):
            chk(f"{nombre} lote {i + 1} paréntesis balanceados", False,
                f"abre {limpio.count('(')}, cierra {limpio.count(')')}")
            break
    else:
        chk(f"{nombre} todos los lotes con paréntesis balanceados", True)

print("\n" + "=" * 70)
if fallos:
    print(f"FALLARON {len(fallos)}: {', '.join(fallos)}")
    sys.exit(1)
print("OK · todos los casos")