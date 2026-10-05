#!/usr/bin/env python3
"""
tools/test_esquema.py — el código contra el esquema real.

Por qué existe: un `INSERT` con una columna que la migración no creó no falla al
desplegar, no falla en el build y no falla en el linter. Falla la PRIMERA vez que
un usuario toca esa pantalla, en producción, con un error que dice "invalid column
name" y sin decir qué código lo pidió. Este archivo encuentra eso antes.

Qué compara, y por qué JUSTO esas tres cosas:

  · `INSERT INTO t (cols)` — la lista de columnas es explícita, así que no hay
    ambigüedad. Es el caso que más fácil se equivoca al copiar de otra tabla.
  · `UPDATE t SET col =` — un nombre mal escrito aquí también es 500.
  · `ALTER`/`REFERENCES` — lo mismo, y además es lo que ata las tablas entre sí.

Lo que NO hace: no valida el SQL sintácticamente (eso lo hace el servidor al
aplicar las migraciones) ni revisa los `SELECT` complexes, donde las listas con
alias y JOIN dan demasiados falsos positivos para valer la pena.

Necesita credenciales de SQL Server. Sin ellas se salta con un aviso y sale 0:
en `check.yml` no hay base de datos, y un test que falla por falta de
configuración entrena al equipo a ignorar el rojo.

Uso:
    HUB_DB_SERVER=… HUB_DB_USER=… HUB_DB_PASSWORD=… HUB_DB_DATABASE=ECCSA_Admon_Pruebas \
        python3 tools/test_esquema.py
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Sólo las tablas de Mailbox: el resto del esquema es de otros apps y sus
# migraciones no están en este repo.
PREFIJO = "HUB_Mailbox"


def conectar():
    """(esquema, mensaje_de_error). `esquema` es None si no hay credenciales."""
    server = os.environ.get("HUB_DB_SERVER")
    password = os.environ.get("HUB_DB_PASSWORD")
    database = os.environ.get("HUB_DB_DATABASE")
    if not (server and password and database):
        return None, ("faltan HUB_DB_SERVER / HUB_DB_PASSWORD / HUB_DB_DATABASE "
                      "(el test se salta)")
    try:
        import pymssql
    except ImportError:
        return None, "pymssql no está instalado (el test se salta)"
    try:
        conn = pymssql.connect(server=server, user=os.environ.get("HUB_DB_USER", "sa"),
                               password=password, database=database,
                               login_timeout=10, timeout=30)
    except Exception as exc:
        return None, f"no pude conectarme ({str(exc).strip().splitlines()[0][:80]})"

    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT t.name AS tabla, c.name AS columna "
        "FROM sys.tables t "
        "INNER JOIN sys.columns c ON c.object_id = t.object_id "
        "WHERE t.name LIKE %s", (PREFIJO + "%",))
    esquema = {}
    for f in cur.fetchall():
        esquema.setdefault(f["tabla"], set()).add(f["columna"])
    cur.close()
    conn.close()
    return esquema, None


def _sql_del_codigo() -> str:
    """
    Devuelve SOLO los literales de cadena del módulo, unidos.

    Esto es lo que hace que el test sea confiable. Escanear el archivo crudo
    mezcla el SQL con el código Python que lo rodea, y los falsos positivos
    distraen tanto que el rojo deja de verse: una versión anterior reportaba como
    "columnas inexistentes" cosas como `c.Alias`, `sesion["Id"` o incluso `ip`,
    que en realidad son variables de Python que quedaron al lado de una cadena.

    `tokenize` separa literales de código sin adivinar. Los f-strings se parten en
    varios trozos (Python 3.12+); se concatenan y se pierden las expresiones
    `{...}` del medio, lo cual no importa: un nombre de columna nunca vive ahí.
    """
    import ast
    import tokenize

    ruta = os.path.join(RAIZ, "api", "main.py")
    pedazos = []
    with open(ruta, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type != tokenize.STRING:
                continue
            # Un f-string es UN token en Python < 3.12 y varios en >= 3.12 (los
            # trozos literales son STRING y lo de dentro es FSTRING_MIDDLE). Se
            # salta el token de f-string completo y se toman los trozos sueltos.
            if re.match(r"^[a-zA-Z]*[fF][a-zA-Z]*['\"]", tok.string):
                continue
            try:
                # `ast.literal_eval` devuelve el VALOR de la cadena. No se usa
                # `tokenize.untokenize`, que sobre un token suelto devuelve el
                # contenido escapado (con barras entre las palabras) y rompe
                # cualquier expresión regular que espere espacios.
                valor = ast.literal_eval(tok.string)
                if isinstance(valor, str):
                    pedazos.append(valor)
            except Exception:
                continue
    sql = " ".join(pedazos)
    # Las cadenas contiguas se unen con `+` o por simple yuxtaposición en el
    # código, pero en el texto plano quedan separadas: se pegan los `", "` y los
    # código, pero en el texto plano quedan separadas: se pegan los literales
    # seguidos por una coma para que `INSERT INTO t (a, b)` quede en un caso.
    sql = re.sub(r'"\s*,\s*"', " ", sql)
    return re.sub(r"\s+", " ", sql)


def revisar(esquema: dict, sql: str):
    """Lista de (where, tabla, columna, motivo)."""
    problemas = []

    # ── INSERT ────────────────────────────────────────────────────────────
    # `INSERT INTO [dbo.]tabla ( c1, c2 ) VALUES`
    for m in re.finditer(
            r"INSERT\s+INTO\s+(?:\[?dbo\]?\.)?(\[?(\w+)\]?)\s*\(([^)]*)\)", sql, re.I):
        tabla = m.group(2)
        cols = [c.strip().strip("[]").split()[0]
                for c in m.group(3).split(",") if c.strip()]
        for col in cols:
            if not _existe(esquema, tabla, col):
                problemas.append(("INSERT", tabla, col,
                                  "la migración no creó esta columna"))

    # ── UPDATE ────────────────────────────────────────────────────────────
    # `UPDATE tabla SET a = …, b = … WHERE …` — se corta en el WHERE.
    for m in re.finditer(
            r"UPDATE\s+(?:\[?dbo\]?\.)?(\[?(\w+)\]?)\s+SET\s+(.+?)(?=\s+WHERE\b|\s+ORDER\s+BY\b|$)",
            sql, re.I):
        tabla = m.group(2)
        for asignacion in re.split(r",(?![^()]*\))", m.group(3)):
            col = asignacion.strip().split("=")[0].strip().strip("[]")
            # Solo la parte izquierda, y SOLO si es un identificador pelado.
            #
            # El archivo que se escanea es Python, no SQL: después del cierre de
            # la cadena hay una tupla de parámetros (`UPDATE … SET x = %s",
            # (valor,)`), y sin este filtro se reportarían como columnas cosas
            # como `c.Alias`, `sesion["Id"` o `}`. Aceptar solo `[A-Za-z_]\w*`
            # deja pasar los identificadores de verdad y descarta el resto.
            if not re.match(r"^[A-Za-z_]\w*$", col):
                continue
            if not _existe(esquema, tabla, col):
                problemas.append(("UPDATE", tabla, col, "la migración no creó esta columna"))

    return problemas


def _existe(esquema: dict, tabla: str, col: str) -> bool:
    """
    ¿La columna existe?

    Solo se valida lo que es de Mailbox. `HUB_Config`, `HUB_Users` y
    `HUB_Passkeys` las creó otro repo y sus migraciones no están aquí: avisar por
    ellas sería ruido que entrena a ignorar el test.
    """
    if not tabla.startswith(PREFIJO):
        return True
    cols = esquema.get(tabla)
    if cols is None:
        return False          # tabla de Mailbox que no existe: se reporta aparte
    return col in cols


def tablas_faltantes(esquema: dict, sql: str) -> set:
    """Tablas Mailbox que el código usa y que no existen."""
    usadas = set()
    for m in re.finditer(r"\b(" + PREFIJO + r"\w+)\b", sql):
        usadas.add(m.group(1))
    return {t for t in usadas if t not in esquema}


def main() -> int:
    esquema, motivo = conectar()
    if esquema is None:
        print(f"· test de esquema saltado: {motivo}")
        return 0
    if not esquema:
        print("FALLO: hay HUB_Mailbox* en el código pero ninguna tabla en la base.\n"
              "       ¿Faltó correr las migraciones?  python3 apply_migrations.py")
        return 1

    sql = _sql_del_codigo()
    problemas = revisar(esquema, sql)
    faltantes = tablas_faltantes(esquema, sql)

    print(f"Base: {os.environ.get('HUB_DB_DATABASE')} · "
          f"{len(esquema)} tablas HUB_Mailbox* en el esquema\n")

    for tabla in sorted(faltantes):
        print(f"  FALLA  la tabla {tabla} se usa en el código pero NO existe")
    for clase, tabla, col, motivo in sorted(problemas):
        print(f"  FALLA  {clase} en {tabla}: la columna «{col}» {motivo}")

    total = len(faltantes) + len(problemas)
    if total:
        print(f"\n{total} problema(s). Son 500 garantizado en el primer request.")
        return 1
    print("OK · cada tabla y cada columna que el código usa existe en la base")
    return 0


if __name__ == "__main__":
    sys.exit(main())