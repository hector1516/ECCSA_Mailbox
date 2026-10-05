# Changelog — Mailbox ECCSA

Registro por versión liberada y, entre versiones, por commit.
Formato basado en [Keep a Changelog](https://keepachangelog.com/).

---

## [Pendiente] — Trabajo no liberado

### 2026-10-05 — Importador de cuentas desde HUBMail

`tools/importar_cuentas_hubmail.py` trae las cuentas del HUBMail viejo (MySQL)
a `HUB_MailboxCuentas` (SQL Server), incluida la asignación de usuarios.

**La contraseña se descifra con la llave vieja y se recifra con la nueva.** Las
dos son Fernet y se ven igual, pero un token cifrado con A no lo descifra B. Por
eso la credencial viaja de memoria a memoria, directa al INSERT: **nunca** se
imprime ni se escribe en un archivo.

Copiar el `PasswordEnc` tal cual es el error que esto evita: la cuenta quedaría
dada de alta, el panel la mostraría en verde, y el worker fallaría al primer IMAP
con un `InvalidToken` que no dice "la llave cambió".

Otras decisiones:

- **Todo entra como `PENDIENTE`**, nunca `ACTIVA`, aunque la cuenta funcionara en
  HUBMail. La llave es distinta y el worker tiene que volver a validar; dar por
  buena una cuenta sin probarla es una suposición que después cuesta una hora de
  sincronización fallando.
- **Una credencial ilegible no tumba el resto.** Se avisa y esa cuenta queda fuera
  para capturarla a mano; las demás se importan.
- **No se duplica una cuenta que ya existe**: el índice único de `Email` haría
  fallar el INSERT sin decir qué cuenta es.
- La asignación (`HUB_MailboxCuentasLinks`) va en la **misma transacción** que la
  cuenta. Si la cuenta entra y la asignación no, queda una cuenta que nadie ve y
  que el worker sincroniza al vacío: el peor estado posible, porque no se nota.
- **La firma vieja no se migra.** En Mailbox las firmas son del usuario y se
  asignan por cuenta (`HUB_MailboxFirmaCuentas`); migrarlas automáticamente
  mezclaría dos modelos. Mejor a mano, desde la pantalla de firmas.

Verificado contra `ECCSA_Admon_Pruebas` con MySQL simulado: 3 cuentas de entrada,
una con la credencial rota (queda fuera, sin tumbar las otras), y el round trip
completo — la contraseña descifrada con la llave **nueva** coincide con el
original, y la llave vieja ya no la descifra.

#### Ejecutado contra los datos reales

El MySQL de HUBMail está **dentro** del contenedor `DBDocker` en ServerVM y no
está publicado en ningún puerto, así que se volcó a un TSV y se importó con
`--desde-archivo` (que queda como opción del script: evita abrir MySQL al mundo
para una migración).

Lo que salió al medir los datos, y que cambió el diseño del importador:

**31 filas, 13 correos, 10 usuarios — y 12 de los 13 correos compartidos.** El
alta de HUBMail era por usuario, así que una casilla compartida salía repetida
con distinto `UserID`. Copiar filas habría dado 13 cuentas duplicadas (y el
índice único de `Email` revienta en la duodécima) y, deduplicando sin más, se
habría perdido el buzón de nueve de diez personas. Por eso el importador agrupa
por dirección y guarda la lista **completa** de usuarios.

Resultado en `ECCSA_Admon_Pruebas`: 13 cuentas, todas `PENDIENTE`, **0
credenciales que no descifren** con la llave nueva, y los buzones por persona
cuadran con los datos viejos.

Dos cosas que conviene que revise una persona:

- **`UserID 1` (IT Support) aparece en las 13 cuentas.** Es lo que dice el origen,
  pero significa que esa cuenta ve todos los buzones. Si no es lo que quiere, se
  quita desde el panel.
- Los servidores **no son todos Gmail**: 11 de 13 son `imap.secureserver.net`
  (Hostinger) y uno es `imap.infinitummail.com`, con SMTP en 465 (TLS implícito,
  que el worker maneja). El importador toma los valores reales, no los defaults.

`tools/test_importador.py` (gate 3b-5) fija dos cosas: que el volcado se lea bien
y que **el cifrado del importador sea el mismo del worker**, comprobado
descifrando cruzadamente — los tokens de Fernet llevan un IV aleatorio y nunca son
iguales, así que comparar cadenas no probaría nada.


### 2026-10-05 — Las respuestas automáticas no se podían crear

La pestaña listaba las respuestas automáticas pero no había forma de **dar de
alta ninguna**: el botón nunca estuvo. La API sí tenía su CRUD completo
(`POST`/`PUT`/`DELETE`), así que el hueco era solo de pantalla — y el estado vacío
mandaba a `/firmas`, que es otro módulo y no ayuda.

Ahora hay editor con: mensaje, cuenta (o todas), dominios exentos, "solo fuera de
horario" y "es la predeterminada", más activar/desactivar, editar y borrar.

De paso se arregló una incoherencia que hacía que el mensaje saliera mal:

- **La app guardaba el mensaje sanitizado como HTML y el worker lo escapaba como
  texto plano.** El worker arma el correo con `escapar(cuerpo)`, así que un
  `<b>negrita</b>` escrito en la respuesta llegaba al destinatario **como texto
  literal**. Ahora se guarda texto plano, con los saltos de línea normalizados
  (un `textarea` en Windows manda CR+LF y el CR suelto se veía como un carácter
  raro al final de cada línea) y un tope de 4000 caracteres.
- El editor es un `textarea` y no el editor rico de las firmas, **a propósito**:
  es la consecuencia de lo anterior, y una auto-respuesta es un aviso, no una
  carta.
- El mensaje ya **no se pinta en un iframe con `srcdoc`**: era la misma frontera
  cid:/URL del resto de la app, vista del otro lado. Aquí lo que hay que proteger
  es al administrador que lo ve, así que se muestra como texto con
  `white-space: pre-wrap`.


### 2026-10-05 — Las migraciones eran inaplicables, y eso solo se vio contra la base real

Las 4 migraciones (`0048`–`0051`) estaban escritas pero **nadie las había corrido
nunca**: no había runner. La consecuencia no era visible — el contenedor arrancaba, el
login funcionaba, y la primera consulta a `HUB_MailboxCuentas` contestaba
"invalid object name". Se agrega `apply_migrations.py` y, al correrlo de verdad,
salieron dos cosas:

- **`CREATE UNIQUE INDEX ... ON t (LTRIM(RTRIM(Email)))` es un error de sintaxis.**
  SQL Server no admite una expresión de función en la clave de un índice: solo
  columnas simples o columnas calculadas **persistidas**. El índice va ahora
  sobre la columna cruda, y para que siga siendo correcto se agrega un `CHECK
  (Email = LTRIM(RTRIM(Email)))`, que sí admite funciones. Sin ese `CHECK`,
  `"juan@x.com"` y `"juan@x.com "` pasarían como dos cuentas distintas, que es
  justo lo que el índice único evita.
- **`schema_migrations` es una tabla COMPARTIDA con HUB/Admon y su esquema no es
  el que este runner asumía.** Es `id / version / created_at / applied_by`, y el
  primer runner inventaba una columna `Archivo` que no existe. Se adaptó a leer y
  escribir la tabla real, **sin alterarla**: cada app llevando su propio historial
  haría que se pierda el único registro de qué se aplicó y qué no. De paso,
  `applied_by` ahora se llena con `usuario@host` (las 56 filas viejas siguen en
  `NULL`, que no es información).

Estado: las 4 aplicadas y verificadas en `ECCSA_Admon_Pruebas` — 13 tablas, 14
foreign keys. **Correr el runner dos veces no cambia nada.**

Guards del runner, y por qué existen:

- **Aborta si el destino no es una base de pruebas**, salvo `HUB_MIGRATE_PRODUCTION=1`
  *y* una confirmación escrita. Es lo que evita aplicar DDL en producción por un
  `export` mal pegado.
- **Una transacción por archivo.** Una migración a medias deja la base en un
  estado que ninguna otra sabe reparar.
- **Ya aplicada no se re-aplica**, y el registro va en la MISMA transacción que
  el DDL: si el INSERT quedara fuera, la siguiente corrida fallaría con "la tabla
  ya existe".

### 2026-10-05 — Dos tests que finds cosas que ningún otro gate veía

- **`tools/test_esquema.py`** — compara el SQL del código contra el esquema REAL
  de la base. Un `INSERT` con una columna que la migración no creó no falla en el
  build ni en el linter: falla el primer request en producción. Sin credenciales
  se salta con aviso y sale 0, porque un test que falla por falta de
  configuración entrena a ignorar el rojo.
  Extracte el SQL con `tokenize` + `ast.literal_eval` en vez de escanear el
  archivo crudo: la versión anterior reportaba como columnas inexistentes
  variables de Python que quedaban al lado de una cadena (`c.Alias`, `ip`).
  Se verificó **inyectando** una columna y una tabla falsas: las detecta.
- **`tools/test_migraciones.py`** — el troceado por `GO`. `GO` es un separador de
  lotes del SSMS, no SQL: mandarlo al servidor contesta `Incorrect syntax near
  'GO'`, o sea que sin trocear **ninguna** migración es aplicable. Cubre `GO` a
  secas, con espacios, en minúsculas, dos seguidos, y el `GO` dentro de un
  literal (que no es separador).


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