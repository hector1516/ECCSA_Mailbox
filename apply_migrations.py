#!/usr/bin/env python3
"""
apply_migrations.py — aplica las migraciones de Mailbox a SQL Server.

Por qué este archivo existe: sin él la app **no se puede desplegar**. Los `.sql`
están, pero nadie los aplicaba, así que el contenedor arrancaba, el login
funcionaba y la PRIMERA consulta a `HUB_MailboxCuentas` daba un error de "invalid
object name". Eso es la peor forma de descubrir que falta un paso.

─── LAS TRES GUARDAS ──────────────────────────────────────────────────────────

**1. Aborta si el destino NO es una base de pruebas**, salvo que se pase
   explícitamente `HUB_MIGRATE_PRODUCTION=1`. Es la guarda que evita aplicar DDL
   en la base de producción por un `export` mal pegado. Las migraciones de Mailbox
   solo crean tablas (no modifican nada ajeno), pero el principio no se negocia:
   una herramienta que escribe en producción tiene que exigir que se le pida a
   propósito.

**2. Cada archivo corre dentro de su propia transacción.** Una migración a medio
aplicar deja la base en un estado que ninguna otra migración sabe reparar. Con
transacción, o entró completa o no entró.

**3. Un archivo ya aplicado no se vuelve a aplicar.** `schema_migrations` es la
   que lleva la cuenta. Sin esto, volver a correr el runner sobre una base ya
   migrada falla en el primer `CREATE TABLE` que ya existe.

─── POR QUÉ NO SE USA `GO` ────────────────────────────────────────────────────

Los `.sql` usan `GO`, que es un separador de **lotes** del SSMS/sqlcmd: no es
SQL y `pymssql` no lo entiende, lo manda al servidor y el servidor contesta
`Incorrect syntax near 'GO'`. Por eso `_trocear()` parte el archivo en los `GO`
antes de mandar cada trozo. `GO` en su propia línea es una convención; si algún
día aparece `GO 5` (repite el lote 5 veces), `_trocear` lo trata como `GO` y lo
advierte, porque un `GO 5` accidental cambia la semántica del archivo entero.

Uso:

    # base de pruebas (lo normal)
    HUB_DB_DATABASE=ECCSA_Admon_Pruebas python3 apply_migrations.py

    # producción, a propósito
    HUB_DB_DATABASE=ECCSA_Admon HUB_MIGRATE_PRODUCTION=1 python3 apply_migrations.py

    # ver qué haría, sin escribir
    python3 apply_migrations.py --dry-run

Sale 0 si todo quedó aplicado, 1 si algo falló.
"""
import getpass
import glob
import os
import re
import socket
import sys

import pymssql

RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_MIGRACIONES = os.path.join(RAIZ, "migrations")

# La base que se considera de pruebas. Todo lo demás exige confirmación.
BASES_PRUEBA = {"ECCSA_Admon_Pruebas", "DB_Tester"}

# `GO` a secas es el caso normal; `GO 5` (repetir el lote 5 veces) es la forma
# larga. El número es OPCIONAL: si el regex lo exigiera, un `GO` normal no
# casaría, el archivo entero se mandaría como un solo lote y el servidor lo
# rechazaría con "Incorrect syntax near 'GO'".
_GO_RE = re.compile(r"^\s*GO(?:\s+(\d+))?\s*$", re.IGNORECASE)


def config() -> dict:
    """Las variables de entorno, con los defaults que usa el backend."""
    return {
        "server": os.environ.get("HUB_DB_SERVER", "10.188.141.15"),
        "user": os.environ.get("HUB_DB_USER", "sa"),
        "password": os.environ.get("HUB_DB_PASSWORD", ""),
        "database": os.environ.get("HUB_DB_DATABASE", "ECCSA_Admon"),
    }


def trocear(sql: str) -> list:
    """
    Parte un archivo en lotes por `GO`.

    `GO` tiene que estar SOLO en su línea; si viene pegado al final de una
    sentencia, no es un separador y partir ahí rompe el SQL. Por eso la
    expresión regular exige que no haya nada más en la línea.
    """
    lotes, actual = [], []
    for linea in sql.splitlines():
        m = _GO_RE.match(linea)
        if m:
            n = m.group(1)
            if n and n != "1":
                # `GO 5` significa "repite este lote 5 veces". No se soporta, y
                # silenciarlo cambiaría lo que la migración hace.
                print(f"  AVISO: '{linea.strip()}' repite el lote; se trata como un "
                      f"separador simple. Revisa esa migración a mano.")
            if _tiene_sql(actual):
                lotes.append("\n".join(actual))
            actual = []
            continue
        actual.append(linea)
    if _tiene_sql(actual):
        lotes.append("\n".join(actual))
    return lotes


def _tiene_sql(lineas) -> bool:
    """
    ¿El lote tiene algo que ejecutar?

    Un lote de puros comentarios se descarta. SQL Server lo aceptaría, así que no
    es un error: es un round trip de sobra. Las migraciones dejan varios
    comentarios de título y separadores entre secciones, así que saltarlos deja
    el número de lotes limpio en el log.
    """
    return any(l.strip() and not l.strip().startswith("--") for l in lineas)


# La tabla de control es COMPARTIDA con HUB/Admon (la creó la migración 0001 de
# aquel repo). Su esquema real es `id / version / created_at / applied_by`, y NO se
# toca: agregarle columnas ni crear una segunda tabla de control: cada app llevaría su
# propio historial y se perdería el único que dice qué se aplicó y qué no.
#
# `version` guarda el NOMBRE DEL ARCHIVO, no un número suelto ("0048_mailbox_cuentas.sql").
# Eso es lo que permite que el mismo número aparezca en apps distintas.
_COL_VERSION = "version"


def _existe_control(conn) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM sys.tables WHERE name = 'schema_migrations'")
        return bool(cur.fetchone()[0])
    finally:
        cur.close()


def aplicadas(conn) -> set:
    """Los nombres de archivo ya registrados en `schema_migrations`."""
    if not _existe_control(conn):
        return set()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute(f"SELECT {_COL_VERSION} FROM dbo.schema_migrations")
        return {(f.get(_COL_VERSION) or "").strip() for f in cur.fetchall()}
    except pymssql.ProgrammingError as exc:
        # Si la tabla existe pero con otro esquema, es mejor decirlo que dejar
        # pasar archivos como si no estuvieran aplicados.
        raise SystemExit(
            f"FALLO: dbo.schema_migrations existe pero no tiene la columna "
            f"{_COL_VERSION}: {exc}")
    finally:
        cur.close()


def registrar(conn, archivo: str):
    """
    Deja el archivo como aplicado, en la MISMA transacción que el DDL.

    Es lo importante: si el DDL entra y el INSERT queda fuera, el runner vuelve a
    correr el archivo en la siguiente invocación y falla con "la tabla ya existe".

    `applied_by` se llena con usuario@host para que en una base compartida por
    varias apps se sepa QUIÉN aplicó cada migración. La migración 0001 de HUB dejó
    esa columna con todos sus valores en NULL, que no es información: "no sabemos".
    """
    quien = f"{getpass.getuser()}@{socket.gethostname()}"[:100]
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO dbo.schema_migrations ({_COL_VERSION}, created_at, applied_by) "
        f"VALUES (%s, GETDATE(), %s)", (archivo, quien))
    cur.close()


def main() -> int:
    cfg = config()
    dry = "--dry-run" in sys.argv

    if not cfg["password"]:
        print("FALTA HUB_DB_PASSWORD. Sin ella no se puede conectar.", file=sys.stderr)
        return 1

    # ── Guarda 1: no escribir en producción por accidente ──────────────────
    if cfg["database"] not in BASES_PRUEBA:
        if os.environ.get("HUB_MIGRATE_PRODUCTION") != "1":
            print(f"FALLO: '{cfg['database']}' no es una base de pruebas "
                  f"({', '.join(sorted(BASES_PRUEBA))}).", file=sys.stderr)
            print("       Para hacerlo a propósito, exporta HUB_MIGRATE_PRODUCTION=1.",
                  file=sys.stderr)
            return 1
        print(f"⚠️  MIGRANDO {cfg['database']} (PRODUCCIÓN). Lo pediste explícitamente.")
        if not dry and input("     ¿Escribir de verdad? [escribi SI] ").strip().upper() != "SI":
            print("       Cancelado.")
            return 1

    archivos = sorted(glob.glob(os.path.join(DIR_MIGRACIONES, "*.sql")))
    if not archivos:
        print(f"No hay migraciones en {DIR_MIGRACIONES}", file=sys.stderr)
        return 1

    print(f"Servidor: {cfg['server']} · Base: {cfg['database']} · "
          f"{len(archivos)} archivo(s)")
    if dry:
        print("MODO ENSAYO: no se escribe nada.\n")

    try:
        # autocommit apagado a propósito: cada migración es su transacción.
        conn = pymssql.connect(server=cfg["server"], user=cfg["user"],
                               password=cfg["password"], database=cfg["database"],
                               login_timeout=15, timeout=120)
    except pymssql.OperationalError as exc:
        print(f"No pude conectarme: {exc}", file=sys.stderr)
        return 1

    try:
        ya = aplicadas(conn)
        if ya:
            print(f"Ya aplicadas: {len(ya)} migración(es).\n")

        fallos = 0
        aplicadas_esta_vez = 0
        for ruta in archivos:
            nombre = os.path.basename(ruta)
            if nombre in ya:
                print(f"  --    {nombre} (ya aplicada)")
                continue
            with open(ruta, encoding="utf-8") as fh:
                sql = fh.read()

            lotes = trocear(sql)
            if dry:
                print(f"  DRY   {nombre} ({len(lotes)} lote(s))")
                continue

            print(f"  >>    {nombre} ({len(lotes)} lote(s))", end="", flush=True)
            try:
                cur = conn.cursor()
                for i, lote in enumerate(lotes):
                    try:
                        cur.execute(lote)
                    except Exception as exc:
                        print(f"\n        FALLO en el lote {i + 1}/{len(lotes)}: "
                              f"{type(exc).__name__}: {exc}")
                        # La primera línea del lote: casi siempre es el CREATE
                        # que falló, y sin esto el error no dice qué objeto.
                        primero = next((l.strip() for l in lote.splitlines()
                                        if l.strip()
                                        and not l.strip().startswith(("--", "PRINT"))), "")
                        if primero:
                            print(f"        Empezaba en: {primero[:100]}")
                        conn.rollback()
                        fallos += 1
                        break
                else:
                    registrar(conn, nombre)
                    conn.commit()
                    aplicadas_esta_vez += 1
                    print("  ok")
            except Exception as exc:
                print(f"\n        FALLO: {type(exc).__name__}: {exc}")
                try:
                    conn.rollback()
                except Exception:
                    pass
                fallos += 1

        print()
        if fallos:
            print(f"{fallos} migración(es) fallaron. La base quedó como estaba antes "
                  f"de cada una (transacción por archivo).", file=sys.stderr)
            return 1
        if not dry:
            print(f"Listo. {aplicadas_esta_vez} migración(es) aplicada(s) en esta "
                  f"corrida ({len(ya)} ya estaban en la base).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())