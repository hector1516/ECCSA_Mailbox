# Changelog — Mailbox ECCSA

Registro por versión liberada y, entre versiones, por commit.
Formato basado en [Keep a Changelog](https://keepachangelog.com/).

---

## [Pendiente] — Trabajo no liberado

### 2026-10-05 — La firma guardaba una URL donde debía guardar un `cid:`

El peor bug de esta tanda, porque no daba ningún error y rompía el envío.

Subir una imagen a una firma insertaba en el editor `r.url` (la URL con token
`/api/sigimg/...`) en vez de `r.html` (que lleva `src="cid:..."`). Y como
`guardar()` persiste el `innerHTML` del editor, **la URL quedaba guardada dentro
de la firma**. Al enviar, el worker busca los `cid:` del HTML para pegarle las
imágenes como adjuntos inline, no encontraba ninguno, y mandaba el HTML tal cual:
el destinatario veía la firma sin logo. Además la URL queda atada al host, así
que cambiar de dominio la rompía para siempre —justo lo que advierte el
comentario de `_cid_para`.

El arreglo son las dos mitades, porque son dos cosas distintas y las dos hacen
falta:

- **Lo que se guarda lleva `cid:`** (el worker lo convierte en adjunto inline real,
  que es lo único que funciona en todos los clientes de correo).
- **Lo que se muestra lleva URL** (`_cid_a_url`, nuevo en el servidor): un `cid:`
  no resuelve en el navegador, así que la vista previa lo necesita.

La reescritura vive en el servidor y no en el cliente porque el servidor es quien
tiene los tokens y quien decide qué es una imagen válida; y porque el mapa sale
de la base, un `cid:` inventado por el usuario simplemente no se encuentra y se
queda como estaba: sin imágenes, no con la imagen de otro.

### 2026-10-05 — Sesiones: `UltimoUso` marcaba todas y no había cómo revocarlas

- **`UltimoUso` se actualizaba por `IdUsuario`**, así que un request marcaba como
  usadas **todas** las sesiones del usuario. La lista de dispositivos mostraba el
  mismo `UltimoUso` en todas —que es justo lo que esa pantalla existe para
  decir— y además cada request escribía en N filas.
- **No existía forma de revocar una sesión concreta.** El endpoint `GET
  /api/auth/sesiones` ya prometía en su docstring "cerrar la sesión en un teléfono
  que se perdió", y lo único que había era `logout`, que revoca la sesión
  **actual**. La lista era de adorno. Se agrega `DELETE /api/auth/sesiones/{id}`,
  con `IdUsuario` en el WHERE (sin eso, adivinar un `Id` de sesión ajena —son
  enteros correlativos— dejaría al usuario sin acceso) y 404 en vez de 403, para
  no confirmar que ese Id existe.


### 2026-10-05 — Cuatro bugs que rompían funciones completas

Ninguno daba error visible. Son de la clase que se descubre cuando alguien usa
la app de verdad, y por eso se documentan con su modo de falla.

- **El visor de mensajes era inalcanzable.** `App.svelte` ruteaba con
  `$path.endsWith('/mensaje')`, pero la ruta del mensaje es
  `/cuenta/<id>/mensaje/<idMensaje>`: **termina en el id del mensaje**, así que la
  condición nunca era cierta. La cadena `{#if}` caía al caso genérico de
  `/cuenta/` y se veía la lista con el mensaje "dentro". La navegación funcionaba y
  la URL era correcta, así que nada se veía mal hasta que se abría un correo.
  Ahora se comparan los segmentos por posición.
- **Subir una imagen de firma fallaba siempre.** `api.post` hacía
  `JSON.stringify(body)`, y `JSON.stringify(new FormData())` es la cadena `"{}"`.
  Con eso el `body` dejaba de ser FormData, `request()` lo tomaba por JSON y
  ponía `Content-Type: application/json`: FastAPI recibía un objeto vacío y
  contestaba 422. El mismo bug de la lección del service worker (ver `AGENTS.md`
  §Trampas), por el mismo motivo: **nunca forzar el Content-Type con FormData**.
- **La casilla de "aplicar firma" no se podía desmarcar.** Usaba
  `bind:checked={firmaEfectiva}` sobre un `$derived`: asignarle descarta el valor,
  y encima `checked` sobre un objeto no significa nada. Ahora hay un booleano
  propio y el id que se manda al backend se deriva de él, para que "desmarcar" y
  "no mandar firma" no puedan quedar desincronizados.
- **Subir una imagen daba 500 y dejaba un archivo huérfano.** El endpoint
  importaba `PIL` —que `requirements.txt` excluía a propósito— **fuera** del
  `try`, y el archivo ya se había escrito en disco para entonces: cada intento
  fallido dejaba basura en el volumen. Ahora la imagen se valida por sus bytes
  mágicos y las dimensiones se leen de la cabecera PNG/GIF/JPEG/WEBP, sin
  Pillow. Los bytes mágicos además son una medida de seguridad: la imagen se
  sirve después en un endpoint **público**, y si el `content_type` dijera PNG
  mientras los bytes fueran HTML, un navegador viejo lo ejecutaría en el origen
  de la app.


### 2026-10-05 — Esqueleto de la app, shell, login y home (0.1.0)

**Decisiones de arquitectura que quedan fijadas** (el detalle está en `AGENTS.md`):

- **El buzón tiene un solo dueño: el worker.** La app nunca habla IMAP ni SMTP
  y nunca ve la credencial. Se coordinan por colas en la base: la app escribe,
  el worker ejecuta. Motivo: una descarga de 200 MB colgada tumba la app, y el
  worker puede caerse sin arrastrarla.
- **Los adjuntos no se guardan.** Se transmiten al dispositivo. Motivo: SQL
  Server 2014 **Express** tiene tope de 10 GB por base y la comparte con toda la
  parte administrativa. `HUBMail` ya pagó este aprendizaje con la migración
  `0010_attachments_file_path.sql`, que movió los adjuntos de `LONGBLOB` a disco.
- **Las cuentas las crea y asigna un admin desde el panel de workersadmon.** El
  usuario no puede crearlas ni ver contraseñas; solo ve las suyas. Así la
  credencial del buzón nunca pasa por el navegador.
- **La misma passkey de Admon y Field.** `rpId` raíz `ecc-sa.com.mx` + tabla
  `HUB_Passkeys` compartida ⇒ el usuario entra con Face ID sin registrar nada.
- **Token con expiración en la base** (`HUB_MailboxSesiones`, se guarda el SHA-256
  del token, nunca el token). Admon no puede revocar sesiones; en un buzón
  "cerrar sesión en el teléfono que se perdió" sí tiene que existir.

**Agregado**

- 📬 **Repo `hector1516/ECCSA_Mailbox`** con el esqueleto de la app.
- 🎨 **Mailbox registrado en el ECCSA-Shell** (`sync_shell.py`, `propagate.py`,
  `check_versiones.py`) y con el CSS propagado: variante **t3**, shell **v1.11.0**.
- 🔑 **Login** con correo de ECCSA + contraseña, y **passkey** con la misma
  tabla `HUB_Passkeys` que las otras apps. Pantalla intermedia que sugiere
  guardar una passkey la primera vez que se entra con contraseña.
- 🏠 **Home**: grilla `.module-grid` del shell, **una tarjeta por cuenta** con
  el contador de no leídos **superpuesto** en la esquina (`.module-badge`, tope
  `99+`), más tarjetas fijas de herramientas. Estados vacíos y de error pensados
  (usuario sin cuentas, cuenta sin sincronizar, error de red).
- 🔔 **Módulo de alertas** construido para iOS: detecta iOS 16.4+, si la PWA está
  instalada y si el permiso está concedido, y **explica qué hacer** en cada
  caso en vez de mostrar un error genérico. Botón de prueba de extremo a extremo.
  El badge se manda en los dos formatos (número en iOS, URL de imagen en
  Android) y el SW traduce.
- ✍️ **Firmas**: CRUD, sanitizado de HTML en servidor, predeterminada única y
  texto plano de fallback para clientes que no pintan HTML.
- 🛡️ **Sanitizador de HTML propio** (lista blanca con `html.parser` de la stdlib)
  en vez de `bleach`, que está deprecado y sin mantenimiento. **35 casos de
  prueba** que corren en CI sin base de datos.
- 🗄️ **Migraciones `0048`–`0050`**: permiso `AccesoMailbox`, cuentas, vínculos,
  sesiones, firmas, imágenes de firma, asignación firma↔cuentas y suscripciones
  push. Todas idempotentes y con las 12 trampas de SQL Server 2014 resueltas.
- 🧪 **Herramientas**: `tools/generar_iconos.py` (parte el logo solo y genera los
  9 iconos del PWA) y `tools/prueba_visual/` (renderiza la home con el CSS
  compilado a 430 / 900 / 1440 px para ver el look sin desplegar).
- 🚀 **CI**: `check.yml` con 4 gates (CSS del shell sin editar, versiones
  alineadas, backend + sanitizador + manifest + `dist/` completo) y
  `deploy-linux.yml` que compila en `ubuntu-latest`, sube a GHCR y recrea el
  contenedor con la lógica compartida `_lib/run_app.sh`.

**Por qué las decisiones se escriben antes que el código**

Cada una de las cinco decisiones de arriba (*el worker es el dueño*, *los
adjuntos no se guardan*, *las cuentas las crea un admin*, *la misma passkey*,
*token revocable*) cierra una alternativa que se discutió y que se puede volver a
discutir. Dejarlas solo en la conversación del chat hizo que HUBMail tuviera dos
versiones del mismo modulo de adjuntos y que la app de Panel del ecosistema
tuviera que inventarse un `.btn.off` propio por no haber heredado el del shell.

**Verificación**

- `npm run build` compila; `dist/` = 96 KB de JS (34 KB gzip) + 28 KB de CSS.
- `python3 -m py_compile api/*.py tools/*.py` limpio.
- `python3 tools/test_sanitizador.py` → **35/35**.
- 38 endpoints registrados; `GET /health` responde 200.
- Comprobado con el server arriba: `/` 200 · `/notificaciones` 200 (fallback SPA)
  · `/no-existe` **404** (la allowlist `_SPA_ROUTES` funciona) ·
  `/api/mailbox/cuentas` sin sesión **401** · `/manifest.webmanifest` con el
  content-type correcto · los tres logos y `sw.js` servidos desde `dist/`.
- Captura visual de la home a 430 / 900 / 1440 px.

**Notas / deuda conocida**

- ⬜ **Falta el `mailbox_worker`.** El esquema de `HUB_MailboxMensajes`,
  `HUB_MailboxAdjuntos`, `HUB_MailboxReglas` y `HUB_MailboxColaEnvio` **no está
  todavía**: es la migración `0051`, y es lo que impide que la bandeja se llene.
  El listado ya está coded y devuelve vacío hasta que exista.
- ⬜ **El editor de firmas es un textarea de HTML**, no un editor rico con
  inserción de imágenes. El sanitizado y la previsualización ya son los
  definitivos (la previsualización muestra lo que devuelve el servidor, no lo
  que se está escribiendo).
- ⬜ **El visor de correo no existe.** La lista de mensajes funciona; abrir uno no.
  Cuando exista, va en `<iframe sandbox>` sin `allow-scripts` (ver `AGENTS.md` §13).
- ⬜ **Falta el paso de deploy en el servidor**: crear `/opt/apps/mailbox/app.conf`
  y `/etc/mailbox.env`. Ambos requieren root (`deploy` tiene sudo acotado).
- ⚠️ **Los iconos salen suaves.** El PNG de origen tiene el contenido real en
  ~210×255 px, así que ampliar a 512 es ×2.4. Se compensa con LANCZOS +
  UnsharpMask; con un original de 1024+ el salto es notorio.