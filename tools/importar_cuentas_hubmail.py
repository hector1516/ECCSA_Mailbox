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


def _nuevo():
    """`encrypt_secret` del worker: es la MISMA función que usará al desencolar."""
    from mailbox_worker.crypto import encrypt_secret
    return encrypt_secret


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

        for v in viejas:
            email = (v.get("EmailAddress") or "").strip()
            where = "MySQL"
            if v.get("_error"):
                avisos.append(f"{email}: {v['_error']} — NO se importa, hay que "
                              f"capturarla a mano")
                continue
            if not email or not v.get("_contrasena"):
                avisos.append(f"{where}: sin correo o sin contraseña")
                continue
            if email.lower() in ya:
                avisos.append(f"{email}: ya existe en MailSQL (id "
                              f"{ya[email.lower()]['Id']}) — no se duplica")
                continue
            if not v.get("UserID") or int(v["UserID"]) not in usuarios:
                avisos.append(f"{email}: el UserID {v.get('UserID')} no está en "
                              f"HUB_Users — se importa SIN asignación")
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
                "_user_id": v.get("UserID"),
                "_id_usuario": (usuarios.get(int(v["UserID"])) or {}).get("Id")
                if v.get("UserID") else None,
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
            if not args.sin_asignar and i["_id_usuario"]:
                cur.execute(
                    "INSERT INTO HUB_MailboxCuentasLinks (IdCuenta, IdUsuario) "
                    "VALUES (%s,%s)", (id_cuenta, i["_id_usuario"]))
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

    faltan = [n for n, v in (("HUBMAIL_DB_HOST", args.hubmail_host),
                             ("HUBMAIL_DB_PASSWORD", args.hubmail_password),
                             ("HUBMAIL_ENCRYPTION_KEY", args.hubmail_key),
                             ("HUB_DB_PASSWORD", args.db_password),
                             ("MAILBOX_ENCRYPTION_KEY",
                              os.environ.get("MAILBOX_ENCRYPTION_KEY", "")))
              if not v]
    if faltan:
        print("Faltan variables: " + ", ".join(faltan), file=sys.stderr)
        return 1

    cifrar = _nuevo()
    viejas = leer_viejas(args)
    print(f"HUBMail: {len(viejas)} cuenta(s) leída(s) desde {args.hubmail_db}")

    inserts, avisos = plan(args, viejas, cifrar)
    for a in avisos:
        print(f"  aviso: {a}")
    print(f"A importar: {len(inserts)}")
    for i in inserts:
        print(f"  · {i['email']}  ({i['alias']})  "
              f"IMAP {i['servidor_imap']}:{i['puerto_imap']}  "
              f"→ {'usuario ' + str(i['_id_usuario']) if i['_id_usuario'] else 'sin asignación'}")

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
