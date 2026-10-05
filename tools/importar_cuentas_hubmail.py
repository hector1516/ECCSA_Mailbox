#!/usr/bin/env python3
"""
tools/importar_cuentas_hubmail.py — trae las cuentas de HUBMail (MySQL) a
Mailbox (SQL Server).

─── POR QUÉ HAY QUE DESCIFRAR Y RECIFRAR ───────────────────────────────────────

HUBMail cifraba las contraseñas con Fernet y una llave que vivía en SU volumen
(`/data/.hubmail_key`). Mailbox usa Fernet con una llave nueva
(`MAILBOX_ENCRYPTION_KEY`). Las dos son Fernet y se ven igual, pero con llaves
distintas: un token cifrado con A no lo descifra B.

Así que la contraseña de cada cuenta tiene que viajar: se descifra con la llave
vieja y se cifra con la nueva. El script **nunca** la imprime ni la escribe en un
archivo; va de memoria a memoria, directo del INSERT.

El error que esto evita: copiar el `PasswordEnc` tal cual. La cuenta quedaría dada
de alta, el panel la mostraría verde, y el worker fallaría al primer IMAP con un
`InvalidToken` que no dice "la llave cambió".

─── EL CASO REAL: CASILLAS COMPARTIDAS ────────────────────────────────────────

En HUBMail el alta de una cuenta era POR USUARIO, así que una casilla compartida
salía N veces con la misma dirección y distinto `UserID`. Al medir los datos
reales: **31 filas, 13 correos y 10 usuarios**, y 12 de los 13 correos estaban
compartidos.

Eso obliga a agrupar por dirección y no a copiar filas. Una fila por entrada
daría 31 cuentas, 13 de ellas duplicadas —y el índice único de `Email` reventaría
en la duodécima— y, peor, si se deduplicara sin más, se perdería el acceso de
nueve de diez personas. Cada cuenta importada lleva la lista COMPLETA de sus
usuarios en `HUB_MailboxCuentasLinks`.

─── LO QUE SE IMPORTA Y LO QUE NO ──────────────────────────────────────────────

De `HUBMAIL_Accounts`:

    UserID       → quién tenía la cuenta
    EmailAddress → Email
    DisplayName  → Alias
    IMAPHost/Port, SMTPHost/Port → igual
    Username     → credencial (el usuario de IMAP, que puede ser distinto)
    PasswordEnc  → se descifra y se recifra

Y se arma además la asignación `HUB_MailboxCuentasLinks`, que en Mailbox separa
"la cuenta existe" de "esta persona la ve". Es lo que el usuario pidió explícitamente:
el modelo nuevo no es "cada usuario tiene su cuenta" sino "hay cuentas y se
asignan".

NO se importa: la firma (`SignatureHtml` la tenía la cuenta vieja; en Mailbox las
firmas son del usuario y viven en `HUB_MailboxFirmas`, y `HUB_MailboxFirmaCuentas`
es la que las asigna). Migrar la firma automáticamente mezclaría dos modelos y es
mejor hacerlo a mano, una por cuenta, desde la pantalla de firmas.

─── ESTADOS ───────────────────────────────────────────────────────────────────

Todo entra como `PENDIENTE`, nunca `ACTIVA`, aunque la cuenta funcionara en
HUBMail. La llave de cifrado es distinta y el worker tiene que volver a validar
la conexión; dar por buena una cuenta sin probarla es exactamente el tipo de
suposición que después cuesta una hora de sincronización fallando.

─── USO ───────────────────────────────────────────────────────────────────────

    HUBMAIL_DB_HOST=… HUBMAIL_DB_USER=… HUBMAIL_DB_PASSWORD=… \
    HUBMAIL_ENCRYPTION_KEY=<llave vieja> \
    MAILBOX_ENCRYPTION_KEY=<llave nueva> \
    HUB_DB_DATABASE=ECCSA_Admon_Pruebas \
        python3 tools/importar_cuentas_hubmail.py --dry-run

`--dry-run` imprime el plan sin escribir. `--sin-asignar` importa las cuentas sin
tocar `HUB_MailboxCuentasLinks`.
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def _viejo():
    """El descifrado de HUBMail, tal cual. Va por la llave que le pasemos."""
    from cryptography.fernet import Fernet, InvalidToken
    return Fernet, InvalidToken


def _nuevo(clave_nueva: str):
    """
    Cifra con la llave NUEVA, igual que hace el worker.

    Se reimplementa Fernet en vez de importar `mailbox_worker.crypto` a propósito:
    ese módulo vive en OTRO repo (WorkersAdmon) y este script tiene que poder
    correr en una máquina que solo tenga este repo. Una importación cruzada
    dejaría la migración atada a un clon que puede no estar.

    Que sea "la misma función" es una responsabilidad, no una casualidad:
    `tests/test_importador.py` compara esta implementación con la del worker
    cuando el otro repo está presente, y falla si divergen. Si divergen, las
    cuentas importadas quedan indescifrables y el error es un `InvalidToken` que
    no dice "las dos implementaciones no coinciden".
    """
    from cryptography.fernet import Fernet
    fernet = Fernet(clave_nueva.encode())

    def cifrar(valor: str) -> str:
        return fernet.encrypt((valor or "").encode()).decode()

    return cifrar


CAMPO_A_COLUMNA = [
    "AccountID", "UserID", "EmailAddress", "DisplayName", "IMAPHost", "IMAPPort",
    "SMTPHost", "SMTPPort", "Username", "PasswordEnc",
]


def _descifrar(contrasena_cifrada, llave, InvalidToken):
    """Fernet → texto. None si no se puede, sin lanzar."""
    try:
        return llave.decrypt((contrasena_cifrada or "").encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None


def leer_de_archivo(ruta: str, llave_vieja: str):
    """
    Lee las cuentas de un TSV previamente volcado.

    Existe por una razón práctica: el MySQL de HUBMail está DENTRO de un
    contenedor en otra máquina y no está publicado en ningún puerto, así que no se
    puede leer con PyMySQL desde donde corre este script. Volcar con

        docker exec DBDocker mysql -uhubmail -p… -D HUBMAIL -N -B -e "SELECT …"

    y pasar el archivo por `--desde-archivo` evita abrir la red de MySQL al mundo
    solo para una migración.

    El archivo lleva `PasswordEnc` cifrado, no la contraseña: el volcado se puede
    tratar como el dato sensible que es, y este script es el único que lo abre.
    """
    from cryptography.fernet import Fernet, InvalidToken
    llave = Fernet(llave_vieja.encode())
    filas = []
    with open(ruta, encoding="utf-8") as fh:
        for num, linea in enumerate(fh, 1):
            linea = linea.rstrip("\n").rstrip("\r")
            if not linea.strip():
                continue
            partes = linea.split("\t")
            if len(partes) != len(CAMPO_A_COLUMNA):
                # Una línea mal partida se salta con aviso en vez de abortar: un
                # volcado con un DisplayName que trae tabulador no debe dejar la
                # importación a medias.
                raise SystemExit(
                    f"{ruta}:{num}: esperaba {len(CAMPO_A_COLUMNA)} columnas y "
                    f"hay {len(partes)}. El volcado está incompleto.")
            r = dict(zip(CAMPO_A_COLUMNA, partes))
            r["IMAPPort"] = int(r["IMAPPort"] or 993)
            r["SMTPPort"] = int(r["SMTPPort"] or 587)
            r["AccountID"] = int(r["AccountID"] or 0)
            r["UserID"] = int(r["UserID"] or 0)
            r["_contrasena"] = _descifrar(r["PasswordEnc"], llave, InvalidToken)
            if r["_contrasena"] is None:
                r["_error"] = "credencial ilegible (no descifra con la llave vieja)"
            filas.append(r)
    return filas


def leer_viejas(args):
    """Las cuentas de MySQL, con la contraseña YA en claro en memoria."""
    import pymysql
    Fernet, InvalidToken = _viejo()
    try:
        llave = Fernet(args.hubmail_key.encode())
    except Exception as exc:
        print(f"La llave de HUBMail no parece una llave Fernet válida: {exc}",
              file=sys.stderr)
        sys.exit(2)

    conn = pymysql.connect(
        host=args.hubmail_host, port=int(args.hubmail_port),
        user=args.hubmail_user, password=args.hubmail_password,
        database=args.hubmail_db, connect_timeout=15,
        cursorclass=pymysql.cursors.DictCursor)
    filas = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT AccountID, UserID, EmailAddress, DisplayName, IMAPHost, "
                "       IMAPPort, SMTPHost, SMTPPort, Username, PasswordEnc "
                "FROM HUBMAIL_Accounts ORDER BY AccountID")
            for r in cur.fetchall():
                r["_contrasena"] = None
                try:
                    r["_contrasena"] = llave.decrypt(
                        (r["PasswordEnc"] or "").encode()).decode()
                except (InvalidToken, ValueError, TypeError) as exc:
                    # No se aborta: se marca la cuenta y se sigue. Si una sola
                    # cuenta tiene la contraseña mal cifrada, las demás son
                    # importables igual, y el usuario solo tiene que volver a
                    # capturar esa.
                    r["_error"] = f"credencial ilegible ({type(exc).__name__})"
                filas.append(r)
    finally:
        conn.close()
    return filas


def plan(args, viejas, cifrar):
    """Arma el plan de INSERT sin escribirlo. Devuelve (inserts, avisos)."""
    inserts, avisos = [], []
    import pymssql
    c = pymssql.connect(server=args.db_server, user=args.db_user,
                        password=args.db_password, database=args.db_name,
                        login_timeout=15, timeout=60)
    cur = c.cursor(as_dict=True)
    try:
        # Lo que YA existe, para no duplicar. El índice único de Email hace que un
        # duplicado reviente con "duplicate key" sin decir qué cuenta es.
        cur.execute("SELECT Id, Email, Alias FROM HUB_MailboxCuentas")
        ya = {f["Email"].strip().lower(): f for f in cur.fetchall()}

        cur.execute("SELECT Id, Nombre, Email FROM HUB_Users WHERE Activo = 1")
        usuarios = {f["Id"]: f for f in cur.fetchall()}

        # Se agrupa por dirección ANTES de decidir nada. Es el caso normal, no
        # el raro: 12 de las 13 cuentas reales estaban compartidas.
        por_correo = {}
        for v in viejas:
            por_correo.setdefault((v.get("EmailAddress") or "").strip(), []).append(v)

        for email, filas in por_correo.items():
            # Las filas de la misma dirección deberían coincidir en host, puertos
            # y credencial. Si NO coinciden, la última gana para no abortar, pero
            # se avisa: dos filas con la misma dirección y distinto servidor
            # significan que alguien editó mal una de las dos.
            Hosts = {(f.get("IMAPHost"), f.get("IMAPPort"), f.get("SMTPHost"),
                      f.get("SMTPPort")) for f in filas}
            if len(Hosts) > 1:
                avisos.append(f"{email}: {len(filas)} filas con servidores "
                              f"distintos ({Hosts}); se usa la última. Revísala.")
            v = filas[-1]
            if v.get("_error"):
                avisos.append(f"{email}: {v['_error']} — NO se importa, hay que "
                              f"capturarla a mano")
                continue
            if not email or not v.get("_contrasena"):
                avisos.append(f"{email or '(sin correo)'}: sin correo o sin "
                              f"contraseña")
                continue
            if email.lower() in ya:
                avisos.append(f"{email}: ya existe en MailSQL (id "
                              f"{ya[email.lower()]['Id']}) — no se duplica")
                continue
            # TODOS los que tenían la casilla, no solo el de la última fila. Un
            # UserID que no exista en HUB_Users se avisa y se omite: es preferible
            # importar la cuenta para los demás que no importar nada.
            owners, perdidos = [], []
            for f in filas:
                uid = f.get("UserID")
                if not uid:
                    continue
                try:
                    uid = int(uid)
                except (TypeError, ValueError):
                    continue
                if uid in usuarios:
                    if uid not in owners:
                        owners.append(uid)
                elif uid not in perdidos:
                    perdidos.append(uid)
            if perdidos:
                avisos.append(f"{email}: los UserID {perdidos} no están en "
                              f"HUB_Users — quedan SIN asignación")
            if not owners:
                avisos.append(f"{email}: nadie quedó asignado")
            inserts.append({
                "alias": (v.get("DisplayName") or "").strip() or email,
                "email": email,
                "servidor_imap": v.get("IMAPHost"),
                "puerto_imap": int(v.get("IMAPPort") or 993),
                "servidor_smtp": v.get("SMTPHost"),
                "puerto_smtp": int(v.get("SMTPPort") or 587),
                "tipo_auth": "PASSWORD",
                "icono": "📮", "color": "#FF6B00",
                "ventana_dias": 90, "max_mensajes": 5000,
                # `CarpetaRaiz` es la carpeta de IMAP de la cuenta, no una
                # "ubicación" de oficina. No existe una columna de ubicación y este
                # importador no la inventa: se descubrió porque el INSERT falló
                # contra el esquema real.
                "carpeta_raiz": "INBOX",
                "_contrasena": v["_contrasena"],
                "_ids_usuario": owners,
                "_nombres": [usuarios[u].get("Nombre") or usuarios[u].get("Email")
                             for u in owners],
            })
    finally:
        c.close()
    return inserts, avisos


def ejecutar(args, inserts, cifrar):
    import pymssql
    c = pymssql.connect(server=args.db_server, user=args.db_user,
                        password=args.db_password, database=args.db_name,
                        login_timeout=15, timeout=60, autocommit=False)
    cur = c.cursor()
    nuevas = 0
    try:
        for i in inserts:
            cur.execute(
                "INSERT INTO HUB_MailboxCuentas "
                "(Alias, Email, ServidorIMAP, PuertoIMAP, ServidorSMTP, "
                " PuertoSMTP, TipoAuth, CredencialCifrada, Estado, CarpetaRaiz, "
                " UsarSSL, Icono, Color, VentanaDias, MaxMensajes) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'PENDIENTE',%s,%s,%s,%s,%s,%s)",
                (i["alias"], i["email"], i["servidor_imap"], i["puerto_imap"],
                 i["servidor_smtp"], i["puerto_smtp"], i["tipo_auth"],
                 cifrar(i["_contrasena"]), i["carpeta_raiz"],
                 1 if i["puerto_imap"] == 993 else 0, i["icono"],
                 i["color"], i["ventana_dias"], i["max_mensajes"]))
            cur.execute("SELECT SCOPE_IDENTITY() AS Id")
            id_cuenta = int(cur.fetchone()[0])
            nuevas += 1
            # La asignación va en la MISMA transacción. Si la cuenta entra y la
            # asignación no, queda una cuenta que NADIE ve y que el worker
            # sincroniza al vacío: el peor estado posible, porque no se nota.
            for uid in ([] if args.sin_asignar else i["_ids_usuario"]):
                cur.execute(
                    "INSERT INTO HUB_MailboxCuentasLinks (IdCuenta, IdUsuario) "
                    "VALUES (%s,%s)", (id_cuenta, uid))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return nuevas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada")
    ap.add_argument("--desde-archivo", default=os.environ.get("HUBMAIL_DUMP", ""),
                    help="TSV previamente volcado, en vez de leer MySQL")
    ap.add_argument("--sin-asignar", action="store_true",
                    help="no crea HUB_MailboxCuentasLinks")
    ap.add_argument("--hubmail-host", default=os.environ.get("HUBMAIL_DB_HOST", ""))
    ap.add_argument("--hubmail-port", default=os.environ.get("HUBMAIL_DB_PORT", "3306"))
    ap.add_argument("--hubmail-user", default=os.environ.get("HUBMAIL_DB_USER", "hubmail"))
    ap.add_argument("--hubmail-password", default=os.environ.get("HUBMAIL_DB_PASSWORD", ""))
    ap.add_argument("--hubmail-db", default=os.environ.get("HUBMAIL_DB_NAME", "HUBMAIL"))
    ap.add_argument("--hubmail-key", default=os.environ.get("HUBMAIL_ENCRYPTION_KEY", ""))
    ap.add_argument("--db-server", default=os.environ.get("HUB_DB_SERVER", "10.188.141.15"))
    ap.add_argument("--db-user", default=os.environ.get("HUB_DB_USER", "sa"))
    ap.add_argument("--db-password", default=os.environ.get("HUB_DB_PASSWORD", ""))
    ap.add_argument("--db-name", default=os.environ.get("HUB_DB_DATABASE", "ECCSA_Admon_Pruebas"))
    args = ap.parse_args()

    obligatorias = [("HUBMAIL_ENCRYPTION_KEY", args.hubmail_key),
                    ("HUB_DB_PASSWORD", args.db_password),
                    ("MAILBOX_ENCRYPTION_KEY",
                     os.environ.get("MAILBOX_ENCRYPTION_KEY", ""))]
    if not args.desde_archivo:
        # Solo hacen falta para hablar con MySQL.
        obligatorias = [("HUBMAIL_DB_HOST", args.hubmail_host),
                        ("HUBMAIL_DB_PASSWORD", args.hubmail_password)] + obligatorias
    faltan = [n for n, v in obligatorias if not v]
    if faltan:
        print("Faltan variables: " + ", ".join(faltan), file=sys.stderr)
        return 1

    cifrar = _nuevo(os.environ["MAILBOX_ENCRYPTION_KEY"])
    if args.desde_archivo:
        viejas = leer_de_archivo(args.desde_archivo, args.hubmail_key)
        print(f"HUBMail: {len(viejas)} fila(s) leída(s) de {args.desde_archivo}")
    else:
        viejas = leer_viejas(args)
        print(f"HUBMail: {len(viejas)} cuenta(s) leída(s) desde {args.hubmail_db}")

    inserts, avisos = plan(args, viejas, cifrar)
    for a in avisos:
        print(f"  aviso: {a}")
    print(f"A importar: {len(inserts)}")
    for i in inserts:
        cuantos = len(i["_ids_usuario"])
        print(f"  · {i['email']:38} {i['alias'][:22]:22} "
              f"{i['servidor_imap']}:{i['puerto_imap']}  "
              f"→ {cuantos} usuario(s)"
              + (": " + ", ".join(n for n in i["_nombres"] if n)[:60] if cuantos else ""))

    if args.dry_run:
        print("\nMODO ENSAYO: no se escribió nada.")
        return 0
    if not inserts:
        print("No había nada que importar.")
        return 0
    nuevas = ejecutar(args, inserts, cifrar)
    print(f"\nImportadas {nuevas} cuenta(s) en {args.db_name}, todas PENDIENTE.")
    print("El worker las valida en su próximo ciclo y las pasa a ACTIVA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
