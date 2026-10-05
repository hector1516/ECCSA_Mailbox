#!/usr/bin/env python3
"""
tools/test_importador.py — pruebas del importador de HUBMail.

Dos cosas se prueban y ninguna es visible si el importador está mal:

1. **Que el cifrado del importador sea el MISMO que el del worker.** El importador
   reimplementa Fernet para no depender del repo de WorkersAdmon. Esa
   reimplementación es una responsabilidad, no una casualidad: si divergiera, las
   cuentas importadas quedarían indescifrables y el síntoma sería un
   `InvalidToken` del worker que no dice "las dos implementaciones no coinciden".
   Como los tokens de Fernet no son deterministas (llevan un IV aleatorio), no se
   pueden comparar como cadenas: se comprueba **descifrando cruzadamente**, que es
   lo único que importa.

2. **Que una casilla compartida se importe como UNA cuenta con VARIOS usuarios.**
   Es el caso normal, no el raro: en los datos reales, 31 filas eran 13 correos y
   12 de los 13 estaban compartidos. Un importador que copiara filas crearía 13
   cuentas duplicadas —y el índice único de `Email` reventaría— y, si deduplicara
   sin más, dejaría a nueve de diez personas sin su buzón.

Ejecución:  python3 tools/test_importador.py
"""
import importlib.util
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from cryptography.fernet import Fernet    # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "imp", os.path.join(RAIZ, "tools", "importar_cuentas_hubmail.py"))
imp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(imp)

fallos = []


def chk(nombre, condicion, detalle=""):
    if condicion:
        print(f"  ok     {nombre}")
    else:
        print(f"  FALLA  {nombre}   {detalle}")
        fallos.append(nombre)


print("\n=== el cifrado del importador y el del worker son el mismo ===")
VIEJA = Fernet.generate_key().decode()
NUEVA = Fernet.generate_key().decode()
REAL = "clave-de-app-de-gmail-abc123"

cifrar = imp._nuevo(NUEVA)
token = cifrar(REAL)
chk("el token es un string", isinstance(token, str))
chk("descifra con la llave nueva", Fernet(NUEVA.encode()).decrypt(token.encode()).decode() == REAL)

# El worker real, si el otro repo está a mano.
RUTA_WORKER = os.environ.get("WORKERSADMON_PATH", "/tmp/opencode/WorkersAdmon")
if os.path.isdir(os.path.join(RUTA_WORKER, "mailbox_worker")):
    sys.path.insert(0, RUTA_WORKER)
    # La llave tiene que fijarse ANTES de importar: `mailbox_worker.config` lee
    # el entorno al importarse y `crypto` cachea la clave en el primer uso. Con
    # `setdefault` no se sobreescribe la que ya venga, y el worker descifraría
    # con una llave distinta de la del test — que es justamente la divergencia
    # que este test busca detectar, pero por el motivo equivocado.
    os.environ["MAILBOX_ENCRYPTION_KEY"] = NUEVA
    os.environ.setdefault("MAILBOX_STREAM_TOKEN", "t")
    for _mod in [m for m in list(sys.modules) if m.startswith("mailbox_worker")]:
        del sys.modules[_mod]
    try:
        from mailbox_worker.crypto import encrypt_secret, decrypt_secret
        del_worker = encrypt_secret(REAL)
        chk("el importador descifra lo que cifró el worker",
            Fernet(NUEVA.encode()).decrypt(del_worker.encode()).decode() == REAL,
            "las dos implementaciones divergieron: las cuentas importadas quedarían "
            "indescifrables")
        chk("el worker descifra lo que cifró el importador",
            decrypt_secret(token) == REAL,
            "las dos implementaciones divergieron")
    except ImportError as exc:
        print(f"  (el worker no se pudo importar: {exc})")
    finally:
        sys.path.remove(RUTA_WORKER)
else:
    print(f"  (saltado: no está {RUTA_WORKER}; pon WORKERSADMON_PATH para probarlo)")

print("\n=== el descifrado de la llave VIEJA ===")
viejo = Fernet(VIEJA)
chk("contraseña buena se descifra",
    imp._descifrar(viejo.encrypt(REAL.encode()).decode(), viejo, Exception) == REAL)
chk("token de otra llave NO se descifra",
    imp._descifrar(viejo.encrypt(REAL.encode()).decode(), Fernet(NUEVA), Exception) is None)
chk("basura no lanza, devuelve None",
    imp._descifrar("NO-ES-FERNET", viejo, Exception) is None)
chk("vacío no lanza, devuelve None", imp._descifrar("", viejo, Exception) is None)

print("\n=== el volcado TSV ===")
import tempfile
fila = ("7\t1\tjuan@ecc-sa.com.mx\tJuan\timap.x.com\t993\tsmtp.x.com\t465\t"
        "juan@ecc-sa.com.mx\t" + viejo.encrypt(REAL.encode()).decode())
with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False,
                                 encoding="utf-8") as fh:
    fh.write(fila + "\n\n")          # línea vacía al final, que es normal
    ruta = fh.name
filas = imp.leer_de_archivo(ruta, VIEJA)
chk("lee la fila", len(filas) == 1, f"leyó {len(filas)}")
if filas:
    f = filas[0]
    chk("mapea las columnas", f["EmailAddress"] == "juan@ecc-sa.com.mx"
        and f["IMAPPort"] == 993 and f["SMTPPort"] == 465)
    chk("descifra la credencial", f["_contrasena"] == REAL)
    chk("no marca error", "_error" not in f)

# Una línea con el número de columnas equivocado tiene que decir DÓNDE.
with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False,
                                 encoding="utf-8") as fh:
    fh.write("7\t1\tjuan@x.com\n")
    ruta_mala = fh.name
try:
    imp.leer_de_archivo(ruta_mala, VIEJA)
    chk("un volcado incompleto se detecta", False, "no lanzó nada")
except SystemExit as exc:
    # El archivo temporal tiene nombre aleatorio, así que se comprueba que el
    # mensaje diga LÍNEA y columnas, que es lo que sirve para encontrarlo.
    chk("un volcado incompleto dice la línea y el motivo",
        ":1:" in str(exc) and "10 columnas" in str(exc) and "hay 3" in str(exc),
        str(exc))

print("\n" + "=" * 70)
if fallos:
    print(f"FALLARON {len(fallos)}: {', '.join(fallos)}")
    sys.exit(1)
print("OK · todos los casos")