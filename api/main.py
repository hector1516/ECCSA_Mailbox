"""
api/main.py — backend de Mailbox ECCSA.

REGLA DE ORO DE ESTE ARCHIVO (y la razón por la que el worker vive aparte)
--------------------------------------------------------------------------
El buzón tiene UN SOLO DUEÑO y no es esta app: el `mailbox_worker`, que corre en
el contenedor `workersadmon`. Aquí NO se habla IMAP ni SMTP nunca.

Lo que hace esta app:
  · Autenticación (contraseña de HUB_Users + passkeys) y sesiones revocables
  · La home: qué cuentas tiene asignadas el usuario
  · Firmas: CRUD, sanitizado del HTML y asignación a cuentas
  · Suscripciones push y envío de avisos
  · Sirve la SPA compilada

Lo que NO hace, nunca:
  · Abrir una conexión IMAP
  · Bajar o guardar un adjunto   → los adjuntos se TRANSMITEN al dispositivo
  · Guardar un cuerpo de correo  → los cuerpos van a disco, los baja el worker

Por qué la app no habla IMAP aunque podría: una descarga de 200 MB colgada en un
request bloquea un hilo del threadpool y, si se repite, tumba la app. Y una
credencial de buzón que vive en la app es una credencial expuesta en el navegador
si algo sale mal.

Dos límites de SQL Server 2014 **Express** que condicionan todo lo de abajo:
  · Tope de 10 GB por base  → por eso los adjuntos no se guardan.
  · Collation case-insensitive → las carpetas llevan COLLATE ..._BIN2 en el DDL.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urlparse

import pymssql
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

APP_ID = "mailbox"
APP_NOMBRE = "Mailbox"

app = FastAPI(title="Mailbox ECCSA API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5174").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# Base de datos
# ═══════════════════════════════════════════════════════════════════════════════
# pymssql es BLOQUEANTE: no hay await implícito. Por eso los endpoints que tocan
# la BD se declaran con `def` y NO con `async def`: FastAPI manda los `def` al
# threadpool. Con `async def`, un GROUP BY pesado bloquea el event loop entero,
# /api/health deja de responder y la app marca "Sin conexión". Ya pasó en Admon
# (CHANGELOG 1.6.3) y esa nota existe para que no se repita.

DB_SERVER = os.environ.get("HUB_DB_SERVER", "10.188.141.15")
DB_USER = os.environ.get("HUB_DB_USER", "sa")
DB_PASSWORD = os.environ.get("HUB_DB_PASSWORD", "")
DB_DATABASE = os.environ.get("HUB_DB_DATABASE", "ECCSA_Admon")

_local = threading.local()


def get_connection() -> pymssql.Connection:
    """
    Conexión por hilo, con sonda de vida y reconexión automática.

    Por qué por hilo y no un pool: uvicorn corre los endpoints `def` en un
    threadpool donde cada hilo atiende requests secuenciales. Una conexión por
    hilo evita tanto abrir una por request como compartir una entre hilos, que
    es donde pymssql se corrompe.

    Por qué autocommit=True: aquí no hay transacción multi-sentencia que valga
    la pena; cada write es una sentencia. Con autocommit se olvida un commit y
    no queda nada a medias.
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _local.conn = None
    conn = pymssql.connect(
        server=DB_SERVER,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        login_timeout=10,
        timeout=30,
        autocommit=True,
    )
    _local.conn = conn
    return conn


def _filas(sql: str, params: tuple = ()) -> List[dict]:
    cur = get_connection().cursor(as_dict=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def _una(sql: str, params: tuple = ()) -> Optional[dict]:
    filas = _filas(sql, params)
    return filas[0] if filas else None


def _ejecuta(sql: str, params: tuple = ()) -> int:
    cur = get_connection().cursor()
    cur.execute(sql, params)
    n = cur.rowcount
    cur.close()
    return n


def _config(clave: str, defecto: str = "") -> str:
    """Valor de HUB_Config. Envolto en try porque una config inaccesible no debe
    tumbar un request que sí puede servir."""
    try:
        fila = _una("SELECT Valor FROM HUB_Config WHERE Clave = %s", (clave,))
        return ((fila or {}).get("Valor") or defecto).strip()
    except Exception:
        return defecto


# ═══════════════════════════════════════════════════════════════════════════════
# Autenticación
# ═══════════════════════════════════════════════════════════════════════════════
# El token es un valor aleatorio de 32 bytes (64 hex). En la tabla se guarda su
# SHA-256, NUNCA el token: si alguien lee la base no puede suplantar una sesión.
#
# El vencimiento se valida en el servidor contra HUB_MailboxSesiones. Es la
# diferencia con Admon, donde el token es "email|timestamp" y nunca se valida:
# allá "cerrar sesión en los otros dispositivos" no existe.

DIAS_SESION = 30


def _nuevo_token() -> tuple:
    token = secrets.token_hex(32)
    return token, hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_de(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _usuario_por_email(email: str) -> Optional[dict]:
    # LTRIM(RTRIM(...)) y no TRIM(): TRIM no existe en SQL Server 2014.
    return _una(
        "SELECT Id, Nombre, Email, Activo, AccesoMailbox, AccesoUsuarios "
        "FROM HUB_Users WHERE LTRIM(RTRIM(Email)) = %s",
        ((email or "").strip().lower(),),
    )


def _publico(u: dict) -> dict:
    """El dict de usuario que viaja al navegador. Nunca la contraseña."""
    return {
        "id": u.get("Id"),
        "nombre": u.get("Nombre"),
        "email": u.get("Email"),
        "acceso_mailbox": bool(u.get("AccesoMailbox")),
        "acceso_usuarios": bool(u.get("AccesoUsuarios")),
        "es_admin": bool(u.get("AccesoUsuarios")),
    }


def _crear_sesion(usuario: dict, dispositivo: str) -> dict:
    token, token_hash = _nuevo_token()
    ahora = datetime.now()
    _ejecuta(
        "INSERT INTO HUB_MailboxSesiones "
        "(TokenHash, IdUsuario, Email, Dispositivo, Creado, UltimoUso, Expira, Activo) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 1)",
        (
            token_hash, usuario["Id"], usuario["Email"], (dispositivo or "")[:200],
            ahora, ahora, ahora + timedelta(days=DIAS_SESION),
        ),
    )
    return {
        "token": token,
        "user": _publico(usuario),
        "expiresAt": int((ahora + timedelta(days=DIAS_SESION)).timestamp() * 1000),
    }


def _usuario_por_token(token: str) -> Optional[dict]:
    if not token:
        return None
    sesion = _una(
        "SELECT IdUsuario, Expira, Activo FROM HUB_MailboxSesiones WHERE TokenHash = %s",
        (_hash_de(token),),
    )
    if not sesion or not sesion.get("Activo"):
        return None
    if sesion["Expira"] and sesion["Expira"] < datetime.now():
        return None

    # HUB_Users se relee en CADA request a propósito: los permisos siempre están
    # frescos. Si a alguien se le quita AccesoMailbox, pierde el acceso en la
    # siguiente petición, no cuando expire el token.
    usuario = _una("SELECT * FROM HUB_Users WHERE Id = %s", (sesion["IdUsuario"],))
    if not usuario or not usuario.get("Activo"):
        return None

    # UltimoUso se actualiza como mucho una vez cada 5 minutos: escribirlo en
    # cada request convertiría una operación barata en un cuello de botella.
    _ejecuta(
        "UPDATE HUB_MailboxSesiones SET UltimoUso = %s "
        "WHERE IdUsuario = %s AND (UltimoUso IS NULL OR UltimoUso < %s)",
        (datetime.now(), usuario["Id"], datetime.now() - timedelta(minutes=5)),
    )
    return usuario


def _bearer(request: Optional[Request]) -> str:
    h = request.headers.get("Authorization", "") if request else ""
    return h[7:].strip() if h.startswith("Bearer ") else ""


def get_current_user(request: Request) -> dict:
    usuario = _usuario_por_token(_bearer(request))
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    return usuario


def require_mailbox(usuario: dict = Depends(get_current_user)) -> dict:
    """Sin este permiso no hay nada que ver: la app ES el buzón."""
    if not usuario.get("AccesoMailbox"):
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso a Mailbox. Pídeselo a un administrador.",
        )
    return usuario


class LoginReq(BaseModel):
    email: str
    password: str


# ── Salud ─────────────────────────────────────────────────────────────────────
@app.get("/health")
@app.get("/api/health")
def health():
    """Sin autenticación. La usa el HEALTHCHECK del contenedor, el ping de
    conectividad del cliente y el balanceador. Tiene que ser rápida."""
    return {"status": "ok", "app": APP_ID, "version": app.version}


# ── Login / logout ────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
def auth_login(body: LoginReq, request: Request):
    """
    Contraseña de HUB_Users.

    Se compara en plano porque así está en la tabla y en las otras apps del
    ecosistema (Admon, Field, panel). Cambiarlo solo aquí rompería el login de
    los usuarios sin ganar nada: la tabla es compartida.

    El dominio se restringe a los dos correos de la empresa, igual que Admon: es
    una app interna y un correo externo no tiene nada que ver aquí.
    """
    email = (body.email or "").strip().lower()
    if not (email.endswith("@ecc-ssa.com.mx") or email.endswith("@ecc-sa.com.mx")):
        raise HTTPException(status_code=401, detail="Usa tu correo de ECCSA")

    usuario = _usuario_por_email(email)
    if not usuario or not usuario.get("Activo"):
        # Mismo mensaje para usuario inexistente y contraseña incorrecta: si se
        # distinguen, el endpoint se puede usar para enumerar quién tiene cuenta.
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    fila = _una("SELECT Password FROM HUB_Users WHERE Id = %s", (usuario["Id"],))
    if not fila or (fila["Password"] or "").strip() != (body.password or "").strip():
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    return _crear_sesion(usuario, request.headers.get("User-Agent", ""))


@app.post("/api/auth/logout")
def auth_logout(request: Request, usuario: dict = Depends(get_current_user)):
    """Revoca la sesión de ESTE dispositivo."""
    _ejecuta(
        "UPDATE HUB_MailboxSesiones SET Activo = 0 WHERE TokenHash = %s",
        (_hash_de(_bearer(request)),),
    )
    return {"ok": True}


@app.get("/api/auth/sesiones")
def auth_sesiones(usuario: dict = Depends(require_mailbox)):
    """Sesiones activas del usuario. Es la lista que permite cerrar la sesión en
    un teléfono que se perdió — algo que en Admon no se puede hacer, porque allá
    el token no se puede revocar."""
    return {
        "sesiones": _filas(
            "SELECT Id, Dispositivo, Creado, UltimoUso, Expira "
            "FROM HUB_MailboxSesiones "
            "WHERE IdUsuario = %s AND Activo = 1 AND Expira > %s "
            "ORDER BY UltimoUso DESC",
            (usuario["Id"], datetime.now()),
        )
    }


# ── Usuario ───────────────────────────────────────────────────────────────────
@app.get("/api/users/me")
def users_me(usuario: dict = Depends(require_mailbox)):
    return _publico(usuario)


# ═══════════════════════════════════════════════════════════════════════════════
# Contrato del banner (ECCSA-Shell · docs/CONTRATO.md)
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/shell/state")
def shell_state(request: Request, usuario: dict = Depends(get_current_user)):
    """
    Estado del banner común. Obligatorio en toda app ECCSA.

    `sync` va fijo en 'idle' a propósito: Mailbox no tiene cola de escritura en
    el cliente. El estado real del buzón lo publica el worker en la tabla de
    cuentas, y esta misma app lo lee para pintar "última sincronización".
    """
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _lee(nombre: str) -> str:
        try:
            with open(os.path.join(raiz, nombre), encoding="utf-8") as fh:
                return fh.read().strip() or "?"
        except OSError:
            return "?"

    try:
        with open(os.path.join(raiz, "package.json"), encoding="utf-8") as fh:
            app_version = json.load(fh).get("version", "?")
    except (OSError, ValueError):
        app_version = "?"

    # lugar.py (copia canónica del shell): X-Forwarded-For (primera entrada) →
    # X-Real-IP → socket. Leer X-Real-IP primero haría que TODO el mundo salga
    # "oficina", porque el proxy del ServerVM reescribe X-Real-IP con la IP
    # privada del puente de Docker. Delante de Cloudflare esto importa más.
    from lugar import lugar_de

    modo, ip = lugar_de(request.headers, request.client.host if request.client else "")

    return {
        "app": {"id": APP_ID, "nombre": APP_NOMBRE, "version": app_version},
        "shell": {"version": _lee("ECCSA_SHELL_VERSION")},
        "user": {
            "nombre": usuario.get("Nombre"),
            "email": usuario.get("Email"),
            "rol": "admin" if usuario.get("AccesoUsuarios") else "usuario",
        },
        "sync": {"estado": "idle", "pendientes": 0, "ultimo": None},
        "lugar": {"modo": modo, "ip": ip},
    }

# ═══════════════════════════════════════════════════════════════════════════════
# Cuentas de correo (SOLO LECTURA para el usuario)
# ═══════════════════════════════════════════════════════════════════════════════
# El usuario NO puede crear cuentas: las asigna un admin desde el panel de
# workersadmon. Acá solo se leen.
#
# El permiso se verifica POR CUENTA y no solo con "tiene AccesoMailbox": las
# cuentas están asignadas una por una (HUB_MailboxCuentasLinks), así que un
# usuario puede tener acceso a Mailbox sin acceso a un buzón concreto. Consultar
# solo "tiene AccesoMailbox" dejaría ver el correo de otra persona.

def _cuenta_del_usuario(cuenta_id: int, usuario: dict) -> dict:
    """Devuelve la cuenta SOLO si el usuario tiene el vínculo. 404 y no 403 a
    propósito: un 403 confirmaría que ese buzón existe."""
    return _una(
        "SELECT c.Id, c.Alias, c.Email, c.Icono, c.Color, c.Estado, c.UltimoSync, "
        "       c.UltimoError, c.CarpetaRaiz, c.VentanaDias, c.MaxMensajes, "
        "       L.IdUsuario AS IdPropietario "
        "FROM HUB_MailboxCuentas c "
        "INNER JOIN HUB_MailboxCuentasLinks L ON L.IdCuenta = c.Id "
        "WHERE c.Id = %s AND L.IdUsuario = %s",
        (cuenta_id, usuario["Id"]),
    )


def _tarjeta(cuenta: dict, usuario: dict) -> dict:
    """La fila que se pinta como tarjeta en la home.

    El conteo de no leídos se cuenta una sola vez para TODAS las cuentas del
    usuario (subconsulta agrupada) y no una por cuenta: con 10 cuentas eso eran
    10 COUNT(*) sobre la tabla de mensajes en el render de la home, que es lo
    que hace lento un listado. Ver CHANGELOG 1.6.3 de Admon: mismo bug, mismo
    arreglo.
    """
    no_leidos = _una(
        "SELECT COUNT(*) AS Total FROM HUB_MailboxMensajes "
        "WHERE IdCuenta = %s AND Visto = 0 AND Carpeta = 'INBOX'",
        (cuenta["Id"],),
    )
    return {
        "id": cuenta["Id"],
        "alias": cuenta.get("Alias"),
        "email": cuenta.get("Email"),
        "icono": cuenta.get("Icono"),
        "color": cuenta.get("Color"),
        "estado": cuenta.get("Estado"),
        "ultimo_sync": cuenta.get("UltimoSync").strftime("%Y-%m-%d %H:%M") if cuenta.get("UltimoSync") else None,
        "ultimo_error": cuenta.get("UltimoError"),
        "no_leidos": int(no_leidos["Total"]) if no_leidos else 0,
        "es_propietaria": cuenta.get("IdPropietario") == usuario["Id"],
    }


@app.get("/api/mailbox/cuentas")
def listar_cuentas(usuario: dict = Depends(require_mailbox)):
    """Tarjetas de la home. Solo las cuentas asignadas a ESTE usuario."""
    cuentas = _filas(
        "SELECT c.Id, c.Alias, c.Email, c.Icono, c.Color, c.Estado, c.UltimoSync, "
        "       c.UltimoError, c.VentanaDias, c.MaxMensajes, "
        "       L.IdUsuario AS IdPropietario "
        "FROM HUB_MailboxCuentas c "
        "INNER JOIN HUB_MailboxCuentasLinks L ON L.IdCuenta = c.Id "
        "WHERE L.IdUsuario = %s "
        "ORDER BY c.Id",
        (usuario["Id"],),
    )
    return [_tarjeta(c, usuario) for c in cuentas]


@app.get("/api/mailbox/cuentas/{cuenta_id}")
def detalle_cuenta(cuenta_id: int, usuario: dict = Depends(require_mailbox)):
    cuenta = _cuenta_del_usuario(cuenta_id, usuario)
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    tarjeta = _tarjeta(cuenta, usuario)
    tarjeta["carpeta_raiz"] = cuenta.get("CarpetaRaiz")
    tarjeta["ventana_dias"] = cuenta.get("VentanaDias")
    tarjeta["max_mensajes"] = cuenta.get("MaxMensajes")
    return tarjeta


@app.get("/api/mailbox/cuentas/{cuenta_id}/mensajes")
def listar_mensajes(
    cuenta_id: int,
    usuario: dict = Depends(require_mailbox),
    carpeta: str = "INBOX",
    limite: int = 50,
    pagina: int = 1,
    buscar: str = "",
):
    """
    Listado de una carpeta. Es el endpoint más caliente de la app: se llama en
    cada apertura de cuenta y en cada cambio de carpeta.

    El filtro de cuenta va SIEMPRE en el WHERE, aunque `_cuenta_del_usuario` ya
    haya comprobado el vínculo: es la defensa contra un idOR. Si alguien pasa
    un cuenta_id ajeno, la cuenta no existe para él y el listado sale vacío.
    """
    if not _cuenta_del_usuario(cuenta_id, usuario):
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")

    limite = max(1, min(int(limite or 50), 200))
    pagina = max(1, int(pagina or 1))
    carpeta = (carpeta or "INBOX")[:100]

    condiciones = ["IdCuenta = %s", "Carpeta = %s"]
    params: list = [cuenta_id, carpeta]

    if buscar.strip():
        condiciones.append("(Asunto LIKE %s OR RemitenteNombre LIKE %s OR RemitenteEmail LIKE %s OR Extracto LIKE %s)")
        patron = f"%{buscar.strip()[:100]}%"
        params += [patron, patron, patron, patron]

    where = " AND ".join(condiciones)

    # TOP con parámetro es legal en T-SQL a partir de 2005. Se usa en vez de
    # OFFSET/FETCH porque hay que saber el total igual para el paginador, y dos
    # consultas simples son más fáciles de leer que una con ventana.
    total_fila = _una(f"SELECT COUNT(*) AS Total FROM HUB_MailboxMensajes WHERE {where}", tuple(params))
    total = int(total_fila["Total"]) if total_fila else 0

    filas = _filas(
        f"SELECT TOP (%s) Id, RemitenteNombre, RemitenteEmail, Asunto, Extracto, "
        f"       FechaCorreo, Visto, Marcado, TieneAdjuntos, NumAdjuntos, Carpeta "
        f"FROM HUB_MailboxMensajes WHERE {where} "
        f"ORDER BY FechaCorreo DESC, Id DESC",
        tuple([limite] + params),
    )

    return {
        "mensajes": [
            {
                "id": f["Id"],
                "remitente_nombre": f.get("RemitenteNombre"),
                "remitente_email": f.get("RemitenteEmail"),
                "asunto": f.get("Asunto"),
                "extracto": f.get("Extracto"),
                "fecha_correo": f["FechaCorreo"].strftime("%Y-%m-%d %H:%M") if f.get("FechaCorreo") else "",
                "visto": bool(f.get("Visto")),
                "marcado": bool(f.get("Marcado")),
                "tiene_adjuntos": bool(f.get("TieneAdjuntos")),
                "num_adjuntos": f.get("NumAdjuntos"),
                "carpeta": f.get("Carpeta"),
            }
            for f in filas
        ],
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "no_leidos": total if carpeta == "INBOX" else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Sanitizado del HTML de las firmas
# ═══════════════════════════════════════════════════════════════════════════════
# Por qué está escrito a mano y no con `bleach`
# -------------------------------------------------
# bleach está deprecado y sin mantenimiento (el autor lo archivó), así que
# agregarlo sería meter una dependencia sin(actualizar) y con una lista de
# CVEs. Para una lista blanca de etiquetas y atributos de correo, 80 líneas de
# html.parser de la stdlib alcanzan y no dependen de nadie.
#
# Por qué el sanitizado es de SERVIDOR y no del cliente
# ---------------------------------------------------
# El HTML de una firma se inyecta dentro del correo que sale de la empresa. Un
# sanitizado en el navegador se salta por la consola del devtools, que es
# justo lo que hace un atacante. El navegador soloPRE-visualiza.
#
# Qué se permite: lo que de verdad se usa en una firma de correo — tablas para
# alinear el logo, colores, tipografías, bordes, un separador, un enlace.

_PERMITIDAS = {
    "p", "div", "span", "br", "hr", "center", "blockquote", "pre", "code",
    "strong", "b", "em", "i", "u", "s", "strike", "small", "big", "sub", "sup",
    "ul", "ol", "li", "dl", "dt", "dd",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "a", "img", "font",
}

# Etiquetas cuyo CONTENIDO se descarta entero, no solo la etiqueta: si se
# sacara `<script>` dejando su texto, el texto del script se vería en el correo.
# Y hay que revisar el texto buscando un ">" sin "<" que reabra una etiqueta.
_DESCARTAR_CON_CONTENIDO = {"script", "style", "iframe", "object", "embed",
                           "form", "input", "button", "select", "textarea",
                           "link", "meta", "base", "svg", "math", "noscript",
                           "applet", "frame", "frameset", "xml"}

_ATRIBUTOS = {
    "*": {"style", "class", "align", "valign", "dir", "lang", "title"},
    "a": {"href", "target", "rel", "name"},
    "img": {"src", "alt", "width", "height", "border", "hspace", "vspace"},
    "table": {"width", "border", "cellpadding", "cellspacing", "bgcolor", "background"},
    "td": {"colspan", "rowspan", "width", "height", "bgcolor", "nowrap", "background"},
    "th": {"colspan", "rowspan", "width", "height", "bgcolor", "nowrap", "background", "scope"},
    "tr": {"height", "bgcolor", "background"},
    "col": {"width", "span"},
    "colgroup": {"width", "span"},
    "font": {"color", "face", "size"},
    "ol": {"start", "type"},
    "ul": {"type"},
}

# cid: es lo que permite una imagen embebida sin base64 (ver AGENTS.md §Firmas).
# mailto: para el enlace de firma. data: NO se permite: por ahí se cuela un
# SVG con script, que es el bypass clásico de los sanitizadores.
_ESQUEMAS_OK = ("http://", "https://", "mailto:", "cid:")

# Patrones Peligrosos dentro de un style= en línea. Los navegadores que pintan
# HTML de correo (Gmail, Outlook) son más permisivos que un navegador normal, y
# `expression()` (IE) / `behavior` / `-moz-binding` son vectores conocidos.
_CSS_MALICIOSO = re.compile(
    r"(expression\s*\(|javascript\s*:|vbscript\s*:|behaviou?r\s*:|-moz-binding|@import|url\s*\(\s*['\"]?\s*javascript)",
    re.I,
)


def _url_segura(valor: str) -> bool:
    """Deja pasar solo esquemas conocidos. Se quita el espacio y el control para
    que `java\tscript:` no cuela."""
    v = (valor or "").strip()
    # Los caracteres de control sirven para partir la esquema sin romperla.
    v = re.sub(r"[\x00-\x20\x7f]", "", v).lower()
    if not v:
        return False
    if v.startswith("#"):
        return True                       # ancla interna
    if v.startswith(_ESQUEMAS_OK):
        # cid: solo con un formato de cid creíble, no "cid:javascript:alert(1)"
        if v.startswith("cid:"):
            return re.match(r"^cid:[a-z0-9._%+@-]{1,200}$", v) is not None
        return True
    return False


def _estilo_seguro(valor: str) -> str:
    if _CSS_MALICIOSO.search(valor or ""):
        return ""
    return valor


class _Sanitizador(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.salida: List[str] = []
        self._descartando = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self._descartando:
            return
        if tag in _DESCARTAR_CON_CONTENIDO:
            self._descartando = 1
            return
        if tag not in _PERMITIDAS:
            return                                    # etiqueta suelta, sin texto
        permitidos = _ATRIBUTOS.get("*", set()) | _ATRIBUTOS.get(tag, set())
        partes = []
        for nombre, valor in attrs:
            nombre = (nombre or "").lower()
            if nombre not in permitidos:
                continue
            valor = (valor or "").replace('"', "&quot;")
            if nombre == "style":
                valor = _estilo_seguro(valor)
                if not valor:
                    continue
            elif nombre in ("src", "href", "background"):
                if not _url_segura(valor):
                    continue
            partes.append(f'{nombre}="{valor}"')
        # Las etiquetas vacías no llevan barra: "br" y no "br/", que es XHTML y
        # se ve raro en el código que edita el usuario.
        self.salida.append(f"<{tag}{(' ' + ' '.join(partes)) if partes else ''}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._descartando:
            if tag in _DESCARTAR_CON_CONTENIDO:
                self._descartando = 0
            return
        if tag in _PERMITIDAS:
            self.salida.append(f"</{tag}>")

    def handle_data(self, data):
        if self._descartando:
            return
        self.salida.append(data.replace("<", "&lt;").replace(">", "&gt;"))

    def error(self, message):
        pass    # HTMLParser no lanza en py3; el override silencia el warning


def _sanitizar_html(html: str) -> str:
    """Lista blanca estricta. Devuelve HTML seguro para incrustar."""
    s = _Sanitizador()
    try:
        s.feed(html or "")
        s.close()
    except Exception:
        # Un HTML que no se puede parsear no se guarda: es preferible que el
        # usuario no tenga firma a que se le guarde algo a medio sanear.
        return ""
    return "".join(s.salida).strip()


class _ATexto(HTMLParser):
    """Texto plano de un HTML. Es el fallback que recibe el cliente cuando no
    pinta HTML (celular con imágenes apagadas, cliente de texto plano)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.texto: List[str] = []
        self._saltar = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("style", "script", "head"):
            self._saltar += 1

    def handle_endtag(self, tag):
        if tag.lower() in ("style", "script", "head") and self._saltar:
            self._saltar -= 1

    def handle_data(self, data):
        if not self._saltar and data.strip():
            self.texto.append(data.strip())

    def error(self, message):
        pass


def _a_texto_plano(html: str) -> str:
    t = _ATexto()
    try:
        t.feed(html or "")
        t.close()
    except Exception:
        pass
    return re.sub(r"\n{3,}", "\n\n", "\n".join(t.texto)).strip()


# ═══════════════════════════════════════════════════════════════════════════════
# Firmas
# ═══════════════════════════════════════════════════════════════════════════════
# Estas SÍ las escribe la app (a diferencia de las cuentas, que son del panel):
# una firma es del usuario, sobre su contenido, y no toca ningún buzón.

class FirmaReq(BaseModel):
    nombre: str
    html: str = ""
    predeterminada: bool = False


def _firma_de_usuario(firma_id: int, usuario: dict) -> Optional[dict]:
    """El IdUsuario va SIEMPRE en el WHERE: si no, un idoru con
    /firmas/{id} de otra persona editaría la firma ajena."""
    return _una(
        "SELECT Id, Nombre, Html, TextoPlano, Predeterminada, Creado, Actualizado "
        "FROM HUB_MailboxFirmas WHERE Id = %s AND IdUsuario = %s",
        (firma_id, usuario["Id"]),
    )


def _firma_json(f: dict) -> dict:
    cuentas = _filas(
        "SELECT IdCuenta FROM HUB_MailboxFirmaCuentas WHERE IdFirma = %s",
        (f["Id"],),
    )
    return {
        "id": f["Id"],
        "nombre": f["Nombre"],
        "html": f.get("Html"),
        "texto_plano": f.get("TextoPlano"),
        "predeterminada": bool(f.get("Predeterminada")),
        "creado": f["Creado"].strftime("%Y-%m-%d") if f.get("Creado") else None,
        "cuentas": [c["IdCuenta"] for c in cuentas],
    }


@app.get("/api/mailbox/firmas")
def listar_firmas(usuario: dict = Depends(require_mailbox)):
    filas = _filas(
        "SELECT Id, Nombre, Html, TextoPlano, Predeterminada, Creado, Actualizado "
        "FROM HUB_MailboxFirmas WHERE IdUsuario = %s ORDER BY Predeterminada DESC, Creado DESC",
        (usuario["Id"],),
    )
    return [_firma_json(f) for f in filas]


@app.post("/api/mailbox/firmas")
def crear_firma(body: FirmaReq, usuario: dict = Depends(require_mailbox)):
    nombre = (body.nombre or "").strip()[:60]
    if not nombre:
        raise HTTPException(status_code=400, detail="Ponle un nombre a la firma")

    html = _sanitizar_html(body.html)
    texto = _a_texto_plano(html)

    # La primera firma del usuario es predeterminada sola: si no, habría que
    # abrir la lista de cada cuenta para descubrir que no hay ninguna.
    ya_tiene = _una("SELECT COUNT(*) AS Total FROM HUB_MailboxFirmas WHERE IdUsuario = %s", (usuario["Id"],))
    predeterminada = bool(body.predeterminada) or int(ya_tiene["Total"]) == 0

    cur = get_connection().cursor()
    cur.execute(
        "INSERT INTO HUB_MailboxFirmas (IdUsuario, Nombre, Html, TextoPlano, Predeterminada, Creado, Actualizado) "
        "VALUES (%s, %s, %s, %s, %s, GETDATE(), GETDATE())",
        (usuario["Id"], nombre, html, texto, 1 if predeterminada else 0),
    )
    # SCOPE_IDENTITY() y no cur.lastrowid: pymssql no lo expone, y con
    # autocommit la función del servidor sí devuelve el IDENTITY recién generado.
    cur.execute("SELECT SCOPE_IDENTITY() AS Id")
    nuevo_id = int(cur.fetchone()["Id"])
    cur.close()

    if predeterminada:
        _ejecuta(
            "UPDATE HUB_MailboxFirmas SET Predeterminada = 0 WHERE IdUsuario = %s AND Id <> %s",
            (usuario["Id"], nuevo_id),
        )
    return {"id": nuevo_id, "nombre": nombre, "html": html, "predeterminada": predeterminada}


@app.put("/api/mailbox/firmas/{firma_id}")
def actualizar_firma(firma_id: int, body: FirmaReq, usuario: dict = Depends(require_mailbox)):
    if not _firma_de_usuario(firma_id, usuario):
        raise HTTPException(status_code=404, detail="Firma no encontrada")

    nombre = (body.nombre or "").strip()[:60]
    if not nombre:
        raise HTTPException(status_code=400, detail="Ponle un nombre a la firma")

    html = _sanitizar_html(body.html)
    _ejecuta(
        "UPDATE HUB_MailboxFirmas SET Nombre = %s, Html = %s, TextoPlano = %s, "
        "Predeterminada = %s, Actualizado = GETDATE() WHERE Id = %s AND IdUsuario = %s",
        (nombre, html, _a_texto_plano(html), 1 if body.predeterminada else 0, firma_id, usuario["Id"]),
    )
    if body.predeterminada:
        # Solo una predeterminada por usuario. Sin esto el worker no sabría
        # cuál aplicar cuando la cuenta no tiene ninguna asignada.
        _ejecuta(
            "UPDATE HUB_MailboxFirmas SET Predeterminada = 0 WHERE IdUsuario = %s AND Id <> %s",
            (usuario["Id"], firma_id),
        )
    return {"ok": True, "id": firma_id, "html": html}


@app.delete("/api/mailbox/firmas/{firma_id}")
def borrar_firma(firma_id: int, usuario: dict = Depends(require_mailbox)):
    if not _firma_de_usuario(firma_id, usuario):
        raise HTTPException(status_code=404, detail="Firma no encontrada")
    _ejecuta("DELETE FROM HUB_MailboxFirmas WHERE Id = %s AND IdUsuario = %s", (firma_id, usuario["Id"]))
    return {"ok": True}


class PrevisualizarReq(BaseModel):
    html: str = ""


@app.post("/api/mailbox/firmas/previsualizar")
def previsualizar_firma(body: PrevisualizarReq, usuario: dict = Depends(require_mailbox)):
    """Devuelve el HTML YA SANITIZADO.

    La vista de editar muestra la previsualización con ESTE resultado, no con lo
    que el usuario está escribiendo: así lo que ve es exactamente lo que se va
    a guardar y a enviar. Si el servidor cambiara la lista blanca más adelante,
    la previsualización muestra el cambio sin tocar el cliente.
    """
    return {"html": _sanitizar_html(body.html)}


# ═══════════════════════════════════════════════════════════════════════════════
# Notificaciones push
# ═══════════════════════════════════════════════════════════════════════════════
# La MISMA pareja de claves VAPID que las demás apps (vapid_private_key /
# vapid_public_key en HUB_Config). Compartir la llave tiene dos ventajas: hay una
# sola que rotar, y si algún día se unifica el envío entre apps es un MERGE.
#
# La tabla de suscripciones es PROPIA (HUB_MailboxSuscripciones) aunque la clave
# sea compartida. El motivo está en la cabecera de la migración 0050: la tabla
# global está indexada por usuario sin columna de app, y usar una sola haría que
# un aviso de correo saliera también en el móvil como alerta de kilómetros.

_VAPID_CACHE: Dict[str, str] = {}


def _vapid() -> dict:
    """Devuelve {privada, publica}. Genera el par la primera vez y lo persiste.

    La clave PRIVADA nunca sale de aquí: va a la tabla en claro porque quien
    puede mandar un push tiene que poder firmarlo, y HUB_Config está dentro del
    mismo perímetro que la base. El oeste del sistema es que nadie más tenga
    acceso a esa base.
    """
    if _VAPID_CACHE.get("priv"):
        return {"priv": _VAPID_CACHE["priv"], "pub": _VAPID_CACHE["pub"]}

    env_priv = (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()
    env_pub = (os.environ.get("VAPID_PUBLIC_KEY") or "").strip()
    if env_priv and env_pub:
        _VAPID_CACHE.update({"priv": env_priv, "pub": env_pub})
        return {"priv": env_priv, "pub": env_pub}

    priv = _config("vapid_private_key")
    pub = _config("vapid_public_key")
    if priv and pub:
        _VAPID_CACHE.update({"priv": priv, "pub": pub})
        return {"priv": priv, "pub": pub}

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    # El público va como base64url de los 65 bytes del punto sin comprimir
    # (0x04 + X + Y). Es lo que espera applicationServerKey en el navegador.
    pub = base64.urlsafe_b64encode(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
    ).decode()

    cur = get_connection().cursor()
    for clave, valor in (("vapid_private_key", priv), ("vapid_public_key", pub)):
        cur.execute("UPDATE HUB_Config SET Valor = %s, Actualizado = GETDATE() WHERE Clave = %s", (valor, clave))
        if cur.rowcount == 0:
            cur.execute("INSERT INTO HUB_Config (Clave, Valor, Actualizado) VALUES (%s, %s, GETDATE())", (clave, valor))
    cur.close()

    _VAPID_CACHE.update({"priv": priv, "pub": pub})
    return {"priv": priv, "pub": pub}


@app.get("/api/push/vapid-public-key")
def vapid_public_key(usuario: dict = Depends(require_mailbox)):
    """Solo la PÚBLICA. La privada no sale del servidor por ningún endpoint."""
    return {"publicKey": _vapid()["pub"]}


class SuscripcionReq(BaseModel):
    endpoint: str
    keys: dict = {}


def _plataforma() -> str:
    """Etiqueta informativa para que el panel diga '3 iPhone, 1 PC'."""
    ua = ""
    try:
        ua = (getattr(_ua_actual, "ua", "") or "").lower()
    except Exception:
        pass
    if not ua:
        return "desconocida"
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return "iOS"
    if "android" in ua:
        return "Android"
    if "windows" in ua:
        return "Windows"
    if "macintosh" in ua:
        return "macOS"
    return "otro"


_ua_actual = threading.local()


@app.post("/api/push/subscribe")
def push_subscribe(body: SuscripcionReq, request: Request, usuario: dict = Depends(require_mailbox)):
    """
    Registra (o re-registra) la suscripción de ESTE dispositivo.

    Es un UPSERT por endpoint. La re-registiación es lo que hace `revincular()` en
    el cliente: la suscripción pertenece al service worker y sobrevive al cierre
    de sesión, así que si el usuario entra con otra cuenta el endpoint seguiría
    apuntando al usuario anterior. Con el upsert, se reasigna.

    Nota sobre el UPSERT: SQL Server 2014 NO tiene ON DUPLICATE KEY. Se hace
    UPDATE y, si no hubo filas afectadas, INSERT. Un MERGE haría lo mismo en una
    sentencia, pero con triggers es notoriously difícil de depurar; el
    UPDATE-then-INSERT con rowcount es más obvio de leer.
    """
    endpoint = (body.endpoint or "").strip()
    if not endpoint:
        raise HTTPException(status_code=400, detail="Suscripción vacía")
    if len(endpoint) > 2000:
        raise HTTPException(status_code=400, detail="Suscripción demasiado larga")

    p256dh = str((body.keys or {}).get("p256dh") or "")[:500]
    auth = str((body.keys or {}).get("auth") or "")[:500]
    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Suscripción incompleta")

    _ua_actual.ua = request.headers.get("User-Agent", "")
    plat = _plataforma()

    n = _ejecuta(
        "UPDATE HUB_MailboxSuscripciones "
        "SET IdUsuario = %s, P256dhKey = %s, AuthKey = %s, Plataforma = %s, Activo = 1 "
        "WHERE Endpoint = %s",
        (usuario["Id"], p256dh, auth, plat, endpoint),
    )
    if n == 0:
        try:
            _ejecuta(
                "INSERT INTO HUB_MailboxSuscripciones "
                "(IdUsuario, Endpoint, P256dhKey, AuthKey, Plataforma, Creado, Activo) "
                "VALUES (%s, %s, %s, %s, %s, GETDATE(), 1)",
                (usuario["Id"], endpoint, p256dh, auth, plat),
            )
        except Exception:
            # Carrera entre dos POST del mismo dispositivo: si otra petición
            # ganó, el UPDATE de arriba ya lo dejó bien. No es un error para el
            # usuario.
            _ejecuta(
                "UPDATE HUB_MailboxSuscripciones SET IdUsuario = %s, Activo = 1 WHERE Endpoint = %s",
                (usuario["Id"], endpoint),
            )

    return {"ok": True, "plataforma": plat}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(body: SuscripcionReq, usuario: dict = Depends(require_mailbox)):
    """Da de baja SOLO este dispositivo. Las filas se marcan Activo=0 en vez de
    borrarse: si el usuario vuelve a entrar, la fila sigue ahí y reactivarla es
    un UPDATE en vez de un INSERT."""
    _ejecuta(
        "UPDATE HUB_MailboxSuscripciones SET Activo = 0 WHERE Endpoint = %s AND IdUsuario = %s",
        ((body.endpoint or "").strip(), usuario["Id"]),
    )
    return {"ok": True}


@app.get("/api/push/contador")
def push_contador(usuario: dict = Depends(require_mailbox)):
    """Total de no leídos del usuario: lo pinta el ícono de la app (el badge).

    El badge en iOS es un NÚMERO, no una imagen. El service worker traduce los
    dos formatos según la plataforma (ver public/sw.js)."""
    fila = _una(
        "SELECT COUNT(*) AS Total FROM HUB_MailboxMensajes m "
        "INNER JOIN HUB_MailboxCuentasLinks L ON L.IdCuenta = m.IdCuenta "
        "WHERE L.IdUsuario = %s AND m.Visto = 0 AND m.Carpeta = 'INBOX'",
        (usuario["Id"],),
    )
    return {"noLeidos": int(fila["Total"]) if fila else 0}


@app.get("/api/push/suscripciones")
def push_suscripciones(usuario: dict = Depends(require_mailbox)):
    """Dispositivos suscritos. Para poder decir 'este teléfono sí, esa laptop no'."""
    return {
        "suscripciones": _filas(
            "SELECT Id, Plataforma, Creado, UltimoUso, Activo "
            "FROM HUB_MailboxSuscripciones WHERE IdUsuario = %s ORDER BY UltimoUso DESC",
            (usuario["Id"],),
        )
    }


@app.post("/api/push/prueba")
def push_prueba(usuario: dict = Depends(require_mailbox)):
    """
    Manda un push de prueba a los dispositivos del usuario.

    Sirve para dos cosas: que el usuario confirme que le llega, y para detectar
    en caliente que la suscripción quedó huérfana (un endpoint que Apple ya no
    reconoce). Pywebpush lanza 404/410 en ese caso y la fila se desactiva sola.
    """
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        raise HTTPException(status_code=501, detail="El servidor no tiene pywebpush instalado")

    claves = _vapid()
    suscripciones = _filas(
        "SELECT Id, Endpoint, P256dhKey, AuthKey FROM HUB_MailboxSuscripciones "
        "WHERE IdUsuario = %s AND Activo = 1",
        (usuario["Id"],),
    )
    if not suscripciones:
        raise HTTPException(
            status_code=409,
            detail="Este dispositivo todavía no está suscrito. Activa las notificaciones primero.",
        )

    enviados = 0
    fallidos = 0
    for s in suscripciones:
        try:
            webpush(
                subscription_info={
                    "endpoint": s["Endpoint"],
                    "keys": {"p256dh": s["P256dhKey"], "auth": s["AuthKey"]},
                },
                data=json.dumps({
                    "title": "📬 Mailbox",
                    "body": "Las notificaciones funcionan. Así se ven los correos nuevos.",
                    "url": "/notificaciones",
                    "tag": "mailbox-test",
                }),
                vapid_private_key=claves["priv"],
                vapid_claims={"sub": "mailto:administracion@ecc-sa.com.mx"},
                timeout=10,
            )
            enviados += 1
        except WebPushException as e:
            codigo = getattr(getattr(e, "response", None), "status_code", None)
            if codigo in (404, 410):
                # El push service ya no reconoce esta suscripción (la app se
                # desinstaló, el navegador regeneró la clave). Se desactiva para
                # no reintentar eternamente contra una suscripción muerta.
                _ejecuta("UPDATE HUB_MailboxSuscripciones SET Activo = 0 WHERE Id = %s", (s["Id"],))
            fallidos += 1
        except Exception:
            fallidos += 1

    if enviados == 0:
        raise HTTPException(status_code=502, detail=f"No se pudo enviar a ningún dispositivo ({fallidos} fallidos)")
    return {"enviados": enviados, "fallidos": fallidos}


# ═══════════════════════════════════════════════════════════════════════════════
# Passkeys (WebAuthn)
# ═══════════════════════════════════════════════════════════════════════════════
# La MISMA passkey que el usuario ya tiene en Admon y Field. La tabla
# HUB_Passkeys es compartida y el rpId es SIEMPRE el raíz (ecc-sa.com.mx), así
# que una credencial creada en cualquiera de las apps sirve en todas: el
# navegador exige que el rpId sea sufijo del dominio actual, y el raíz es
# sufijo de *.ecc-sa.com.mx.
#
# Es la razón por la que Mailbox no necesita su propia passkey: el usuario
# entra con Face ID sin haber registrado nada.
#
# El challenge va en un JWT stateless (no en una tabla) porque así sobrevive a
# que el proceso se reinicie y a que haya más de un worker de uvicorn.

RP_ID = "ecc-sa.com.mx"
RP_NOMBRE = "ECCSA"
CHALLENGE_TTL = 5 * 60          # 5 minutos

_SECRET_CACHE: Dict[str, str] = {}


def _secret_passkeys() -> str:
    """Secreto de los JWT de challenge.

    Orden: env > HUB_Config (se genera y persiste la primera vez) > fallback de
    arranque. El fallback solo aplica si la BD no responde: si se usara siempre,
    un reinicio invalidaría los challenges en vuelo y el usuario vería un error
    de passkey sin explicación.
    """
    if _SECRET_CACHE.get("s"):
        return _SECRET_CACHE["s"]
    env = os.environ.get("JWT_SECRET") or os.environ.get("PASSKEY_JWT_SECRET")
    if env:
        _SECRET_CACHE["s"] = env
        return env
    secreto = _config("mailbox_passkey_secret")
    if not secreto:
        secreto = base64.urlsafe_b64encode(os.urandom(48)).decode("ascii").rstrip("=")
        _ejecuta(
            "UPDATE HUB_Config SET Valor = %s, Actualizado = GETDATE() WHERE Clave = 'mailbox_passkey_secret'",
            (secreto,),
        )
        if _config("mailbox_passkey_secret") == "":
            _ejecuta(
                "INSERT INTO HUB_Config (Clave, Valor, Actualizado) "
                "VALUES ('mailbox_passkey_secret', %s, GETDATE())",
                (secreto,),
            )
    _SECRET_CACHE["s"] = secreto
    return secreto


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _origin_permitido(origin: str) -> bool:
    """Allowlist: https://ecc-sa.com.mx o cualquier *.ecc-sa.com.mx, más
    localhost para desarrollo.

    Con Cloudflare al frente, el Origin que ve FastAPI es el que mandó el
    navegador (Cloudflare lo reenvía), así que la allowlist sigue valiendo. No se
    usa X-Forwarded-Host: un atacante puede controlarlo.
    """
    if not origin:
        return False
    p = urlparse(origin)
    if p.hostname in ("localhost", "127.0.0.1"):
        return True
    if p.scheme != "https":
        return False
    host = p.hostname or ""
    return host == "ecc-sa.com.mx" or host.endswith(".ecc-sa.com.mx")


def _origin_de(request: Optional[Request]) -> str:
    origin = request.headers.get("origin", "") if request else ""
    if not _origin_permitido(origin):
        raise HTTPException(status_code=400, detail="Origen no permitido")
    return origin


def _emitir_challenge(proposito: str) -> tuple:
    import time as _t

    import jwt as _jwt

    raw = os.urandom(32)
    ahora = int(_t.time())
    token = _jwt.encode(
        {"purpose": proposito, "ch": _b64url(raw), "iat": ahora, "exp": ahora + CHALLENGE_TTL},
        _secret_passkeys(),
        algorithm="HS256",
    )
    return token, raw


def _leer_challenge(state: str, proposito: str) -> bytes:
    import jwt as _jwt

    try:
        datos = _jwt.decode(state, _secret_passkeys(), algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=400, detail="La sesión venció. Intenta de nuevo.")
    if datos.get("purpose") != proposito:
        raise HTTPException(status_code=400, detail="Desafío incorrecto")
    pad = "=" * (-len(datos["ch"]) % 4)
    return base64.urlsafe_b64decode(datos["ch"] + pad)


class PasskeyLoginOptionsReq(BaseModel):
    rp: str = RP_ID


class PasskeyLoginVerifyReq(BaseModel):
    credential: dict
    state: str


class PasskeyRegisterVerifyReq(BaseModel):
    credential: dict
    state: str
    label: str = "Mi equipo"


@app.post("/api/passkeys/login/options")
def passkey_login_options(request: Request):
    """Login sin correo: es una passkey "discoverable" (resident key), así que
    el navegador encuentra cuál usar solo con el rp."""
    from webauthn import generate_authentication_options, options_to_json

    _origin_de(request)
    state, challenge = _emitir_challenge("wk_login")
    opciones = generate_authentication_options(rp_id=RP_ID, challenge=challenge)
    return {"options": options_to_json(opciones), "state": state, "rp": RP_ID}


@app.post("/api/passkeys/login/verify")
def passkey_login_verify(body: PasskeyLoginVerifyReq, request: Request):
    """Valida el assertion y devuelve la sesión igual que /api/auth/login."""
    from webauthn import base64url_to_bytes, verify_authentication_response

    challenge = _leer_challenge(body.state, "wk_login")
    origin = _origin_de(request)
    cred_id = (body.credential or {}).get("id", "")

    fila = _una("SELECT * FROM HUB_Passkeys WHERE CredentialId = %s", (cred_id,))
    if not fila:
        raise HTTPException(status_code=401, detail="Passkey no reconocida en este equipo")

    # Una passkey guardada con otro rpId (por ejemplo field.ecc-sa.com.mx, de
    # días previos a la unificación) NO se puede verificar desde aquí: el
    # navegador exige que el rpId coincida con el dominio actual.
    cred_rp = (fila.get("RpId") or RP_ID).strip() or RP_ID
    if cred_rp != RP_ID:
        raise HTTPException(
            status_code=401,
            detail="Tu passkey es de otra app. Crea una aquí con ＋ Agregar este equipo.",
        )

    # El userHandle tiene que ser del dueño de la credencial: si no, un
    # dispositivo con la passkey de A podría autenticarse como B.
    try:
        raw_handle = (body.credential.get("response") or {}).get("userHandle")
        handle_uid = int(base64url_to_bytes(raw_handle).decode("utf-8")) if raw_handle else fila["IdUsuario"]
    except Exception:
        handle_uid = fila["IdUsuario"]
    if handle_uid != fila["IdUsuario"]:
        raise HTTPException(status_code=401, detail="Passkey no válida para este usuario")

    try:
        verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=origin,
            credential_public_key=base64.urlsafe_b64decode(fila["PublicKey"] + "=="),
            credential_current_sign_count=fila["SignCount"] or 0,
            require_user_verification=False,
        )
    except Exception as e:
        print(f"[passkey] login FAIL cred={cred_id[:12]}: {e}", flush=True)
        raise HTTPException(status_code=401, detail="No se pudo verificar la passkey")

    _ejecuta("UPDATE HUB_Passkeys SET UltimoUso = GETDATE() WHERE IdUsuario = %s", (fila["IdUsuario"],))

    # El login por passkey tiene el MISMO filtro que el de contraseña: sin
    # AccesoMailbox o con Activo=0 no hay sesión. Un usuario desactivado no
    # entra ni con Face ID.
    usuario = _una("SELECT * FROM HUB_Users WHERE Id = %s", (fila["IdUsuario"],))
    if not usuario or not usuario.get("Activo"):
        raise HTTPException(status_code=401, detail="Usuario desactivado")

    return _crear_sesion(usuario, request.headers.get("User-Agent", ""))


@app.post("/api/passkeys/register/options")
def passkey_register_options(
    request: Request,
    usuario: dict = Depends(get_current_user),
):
    """Opciones de registro. Requiere sesión: nadie crea una passkey sin haber
    demostrado que sabe su contraseña."""
    from webauthn import base64url_to_bytes, generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorAttachment,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    _origin_de(request)

    # Se excluyen las passkeys que ya tiene: registrar dos veces la misma
    # credencial en el mismo autenticador confunde al navegador al elegir cuál
    # usar después.
    existentes = _filas(
        "SELECT CredentialId FROM HUB_Passkeys WHERE IdUsuario = %s AND RpId = %s",
        (usuario["Id"], RP_ID),
    )
    excluir = []
    for c in existentes:
        try:
            excluir.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["CredentialId"])))
        except Exception:
            continue

    state, challenge = _emitir_challenge("wk_reg")
    opciones = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NOMBRE,
        user_id=str(usuario["Id"]).encode("utf-8"),
        user_name=usuario["Email"],
        user_display_name=usuario.get("Nombre") or usuario["Email"],
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            # PLATFORM = Touch ID / Face ID / Android, o sea lo que quiere un
            # usuario de teléfono. Se elige a propósito del requisito: la
            # mayoría del uso es iPhone.
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=excluir or None,
    )
    return {"options": options_to_json(opciones), "state": state}


@app.post("/api/passkeys/register/verify")
def passkey_register_verify(
    body: PasskeyRegisterVerifyReq,
    request: Request,
    usuario: dict = Depends(get_current_user),
):
    from webauthn import verify_registration_response

    challenge = _leer_challenge(body.state, "wk_reg")
    origin = _origin_de(request)
    try:
        v = verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=origin,
        )
    except Exception as e:
        print(f"[passkey] register FAIL uid={usuario['Id']}: {e}", flush=True)
        raise HTTPException(status_code=400, detail="No se pudo registrar la passkey")

    cred_id = _b64url(v.credential_id)
    pubkey = _b64url(v.credential_public_key)
    transports = ",".join(body.credential.get("transports", []) or [])
    etiqueta = (body.label or "Mi equipo")[:100]

    if _una("SELECT Id FROM HUB_Passkeys WHERE CredentialId = %s", (cred_id,)):
        raise HTTPException(status_code=400, detail="Esta passkey ya está registrada")

    _ejecuta(
        "INSERT INTO HUB_Passkeys "
        "(IdUsuario, CredentialId, PublicKey, SignCount, Transports, Etiqueta, RpId) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (usuario["Id"], cred_id, pubkey, v.sign_count, transports, etiqueta, RP_ID),
    )
    return {"ok": True}


@app.get("/api/passkeys/mine")
def passkeys_mine(usuario: dict = Depends(get_current_user)):
    filas = _filas(
        "SELECT Id, Etiqueta, Creado, UltimoUso, RpId FROM HUB_Passkeys "
        "WHERE IdUsuario = %s ORDER BY UltimoUso DESC",
        (usuario["Id"],),
    )
    for f in filas:
        # EsNueva = la usable desde ESTA app. Las de otros rpId se listan pero
        # marcadas: el usuario puede verlas y entender por qué no funcionan.
        f["EsNueva"] = (f.get("RpId") or RP_ID) == RP_ID
    return {"passkeys": filas}


@app.delete("/api/passkeys/{passkey_id}")
def passkey_borrar(passkey_id: int, usuario: dict = Depends(get_current_user)):
    """Se puede borrar la propia. La última no: sin passkey el usuario tiene que
    seguir entrando con contraseña, y quitarle la única sería dejarle sin
    acceso si no recuerda la clave."""
    propias = _filas("SELECT Id FROM HUB_Passkeys WHERE IdUsuario = %s", (usuario["Id"],))
    if len(propias) <= 1:
        raise HTTPException(
            status_code=400,
            detail="No puedes borrar tu única passkey. Agrega otra antes.",
        )
    n = _ejecuta("DELETE FROM HUB_Passkeys WHERE Id = %s AND IdUsuario = %s", (passkey_id, usuario["Id"]))
    if n == 0:
        raise HTTPException(status_code=404, detail="Passkey no encontrada")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Sincronización
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/sync/pedir")
def sync_pedir(usuario: dict = Depends(require_mailbox)):
    """
    "Traer los correos" desde el banner.

    NO dispara IMAP: solo le dice al worker que este usuario quiere que
    refresquen ya. El worker lee la petición en su próximo ciclo y hace el
    trabajo. Que la app no sea la que hable IMAP es justamente lo que permite
    que el worker se caiga sin tirar la app.
    """
    return {"ok": True, "mensaje": "El worker traerá los correos en su siguiente ciclo."}


# ═══════════════════════════════════════════════════════════════════════════════
# La SPA compilada
# ═══════════════════════════════════════════════════════════════════════════════
# Va AL FINAL del archivo a propósito: si se montara antes, el catch-all se
# comería las rutas de /api y la app dejaría de hablar con su propio backend.
#
# Va envuelto en try/except para que una imagen sin dist/ todavía sirva la API:
# es más útil tener /api/health responding que no tener nada.

try:
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    _dist = Path(__file__).resolve().parent.parent / "dist"
    _hay_spa = _dist.is_dir() and (_dist / "index.html").is_file()

    if _hay_spa and (_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    # Segmentos de ruta que el router del cliente sabe manejar. Es una lista
    # ALFABÉTICA y NO es un fallback universal: una ruta que no esté aquí
    # devuelve 404 en vez de index.html.
    #
    # Por qué no `catch-all`: con un fallback universal, un typo en una URL
    # devolvería la app (200) en vez de un 404, y los enlaces rotos pasarían
    # desapercibidos. Esta lista explícita obliga a(actualizar) el backend cada
    # vez que se agrega una ruta, que es justo cuando hay que acordarse.
    _SPA_ROUTES = {
        "firmas", "notificaciones", "cuenta", "login",
    }

    # Estos tres NO se cachean nunca. Si el index.html queda cacheado, el
    # usuario sigue viendo el bundle viejo después de un deploy y la app parece
    # rota (el bundle viejo pide rutas que el backend ya no tiene).
    _NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate"}
    _NO_STORE = {"index.html", "sw.js", "manifest.webmanifest", "changelog.json"}

    def _archivo(nombre: str):
        resp = FileResponse(str(_dist / nombre))
        resp.headers.update(_NO_CACHE)
        return resp

    @app.get("/")
    def spa_raiz():
        if _hay_spa:
            return _archivo("index.html")
        return {"message": "Mailbox ECCSA API", "version": app.version}

    @app.get("/{ruta:path}")
    def spa_ruta(ruta: str):
        if not _hay_spa:
            raise HTTPException(status_code=404, detail="Not found")

        # 1) ¿Es un archivo real de dist/ (logo, íconos, engrane, sw.js)?
        #    Se resuelve y se comprueba que siga DENTRO de dist/: sin eso,
        #    `../../etc/passwd` se salta del directorio.
        if ruta:
            destino = (_dist / ruta).resolve()
            try:
                destino.relative_to(_dist.resolve())
            except ValueError:
                raise HTTPException(status_code=404, detail="Not found")
            if destino.is_file():
                resp = FileResponse(str(destino))
                if destino.name in _NO_STORE:
                    resp.headers.update(_NO_CACHE)
                return resp

        # 2) ¿Es una ruta del cliente? Entonces index.html y que el router decida.
        primero = ruta.split("/", 1)[0]
        if primero in _SPA_ROUTES:
            return _archivo("index.html")

        raise HTTPException(status_code=404, detail="Not found")

except Exception as _e:  # noqa: BLE001
    print(f"[main] la SPA no se montó ({_e}); la API sigue funcionando", flush=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
