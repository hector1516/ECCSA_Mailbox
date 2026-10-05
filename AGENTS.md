# AGENTS.md — Mailbox ECCSA

Buzón corporativo de ECCSA. PWA (iOS / Android / escritorio), URL
`https://mailbox.ecc-sa.com.mx` detrás de Cloudflare.

---

## 1. La regla que define la app

> **El buzón tiene UN SOLO DUEÑO, y no es la app.**
> El worker (`mailbox_worker`, en `workersadmon`) es el único que habla IMAP y
> SMTP, y el único que ve la credencial. Esta app **nunca** abre una conexión
> IMAP.

| | App Mailbox | workersadmon |
|---|---|---|
| IMAP / SMTP | ❌ nunca | ✅ dueño único |
| Credencial del buzón | ❌ nunca la ve | ✅ cifrada en reposo |
| Cuerpo del correo | ❌ no lo guarda | ✅ lo baja a disco |
| Adjuntos | **proxy** de la descarga | ✅ hace el fetch |
| Firmas, reglas, cola de envío | ✅ escribe | ✅ ejecuta |
| Cuentas (crear/asignar) | ❌ | ✅ panel |

Por qué está así, y no es purismo:

- **Una descarga colgada tumba la app.** Un adjunto de 200 MB en un request
  bloquea un hilo del threadpool; si se repite, la app deja de responder. El
  worker puede caerse 20 minutos sin que nadie lo note.
- **La credencial nunca sale del worker.** Un admin escribe la contraseña del
  buzón en el panel; no existe ningún camino por el que pase por el navegador.
- **Un worker que se cae no se lleva la app.** Con el reparto inverso, un ciclo
  de IMAP de 5 minutos bloquea el deploy.

### Cómo se coordinan sin hablar

La app **escribe filas de cola**; el worker las **ejecuta**. Ejemplo: marcar un
correo como leído pone una fila en `HUB_MailboxColaOperaciones`; en su siguiente
ciclo el worker la aplica en IMAP. La app nunca ve el resultado de inmediato y
por eso el botón es optimista.

---

## 2. Lo que NO se edita a mano (se genera)

| Archivo | Lo escribe |
|---|---|
| `src/styles/app.css` | `ECCSA-Shell/tools/build_shell.py` → `sync_shell.py` |
| `src/lib/shell.js` | `sync_shell.py` (estampa versiones) |
| `src/components/{SyncHeader,ActionsBar,Changelog}.svelte` | copia canónica del shell |
| `src/lib/changelog.js` | copia canónica del shell |
| `api/lugar.py` | copia canónica del shell |
| `ECCSA_SHELL_VERSION` / `ECCSA_SHELL_SHA` | `sync_shell.py` |

`check.yml` **falla el build** si `src/styles/app.css` se editó a mano (compara
el SHA). **No lo esquives: cambialo en el shell.**

```bash
# si hay que cambiar el diseño (colores, tarjetas, botones, banner):
vim ECCSA-Shell/tokens.css          # o src/body.css
python ECCSA-Shell/tools/build_shell.py
python ECCSA-Shell/tools/sync_shell.py --target . --variant t3
python ECCSA-Shell/tools/sync_shell.py --target . --check    # sale 1 si divergió
```

Mailbox usa la variante **t3** (Tailwind v3, Svelte). Ojo: su CSS vive en
`src/styles/app.css`, **no** en `src/app.css` (ese es el de Field).

## 3. Lo que SÍ es de la app: el cableado

Los componentes del shell no importan nada del proyecto. Todo llega por props:

```svelte
<SyncHeader estado={...} usuario={...} appVersion={APP_VERSION}
             shellVersion={SHELL_VERSION} fetcher={shellFetch} onsync={shellSync} />
<ActionsBar onlogout={...} />          <!-- un botón se pinta solo si hay manejador -->
<Changelog appId="mailbox" version={APP_VERSION} url="/changelog.json" />
```

- **`fetcher` es obligatorio.** `GET /api/shell/state` exige sesión y Mailbox
  autentica con `Authorization: Bearer`, no con cookie. Sin `fetcher` da 401 y
  el 🏢/🏠 del banner se queda en `📍` **sin ningún error visible**.
- **`<Changelog>` se monta UNA vez**, en `App.svelte`. Si viviera en el header
  no saltaría al entrar por cualquier ruta.

---

## 4. Versión: una sola fuente

```
package.json  ──sync_shell.py──▶  src/lib/shell.js
                                        ├── banner  v{app} · shell {shell}
                                        ├── .version-badge
                                        └── popup 📋 de novedades
```

`public/changelog.json` debe llevar **la misma versión** o CI falla; cada línea
de `cambios` máximo **160 caracteres** (más no entra en un iPhone). Al
liberar: subir `package.json`, bajar la versión en `public/changelog.json` +
`index.html` (`var cur`) + `sw.js` (`CACHE`), y anotar en `CHANGELOG.md`.

---

## 5. Almacenamiento: por qué los adjuntos NO se guardan

SQL Server es **2014 Express**: tope de **10 GB por base**, y esa base la
comparten toda la parte administrativa. Meter adjuntos la llena; y a expres
también se le va la memoria con un `SELECT` de un blob grande.

| Capa | Qué | Dónde |
|---|---|---|
| Índice | Headers, flags, manifiesto de adjuntos | SQL Express |
| Cuerpos | HTML/texto **gzip** | volumen `mailbox_data:/data/mailbox` |
| Inline `cid:` ≤256 KB | Bytes | mismo volumen |
| Imágenes de firma | Pocas (5 por usuario) | SMB `\\Fileserver\hub\Mailbox` |
| **Adjuntos** | **nada** | — se transmiten al dispositivo |

**Retención en dos niveles:** 0–90 días headers + cuerpo + inline · 90 días–1 año
solo headers (búsqueda y contexto, sin abrir) · >1 año nada.

⚠️ Antecedente: `HUBMail` empezó guardando adjuntos como `LONGBLOB` en MySQL y
tuvo que hacer la migración `0010_attachments_file_path.sql` para moverlos a
disco. El `almacen.py` que ya existía en ese worker es la abstracción correcta;
no se descarta, se porta.

---

## 6. Firmas

- El HTML se **sanitiza en el servidor** (`api/main.py::_sanitizar_html`).
  Nunca en el cliente: un sanitizado en el navegador se salta por la consola.
- **No se usa `bleach`**: está deprecado y sin mantenimiento. La lista blanca
  está escrita con `html.parser` de la stdlib y tiene 35 pruebas en
  `tools/test_sanitizador.py`.
- **Nunca base64 dentro del HTML.** Un logo de 300 KB inlineado pesa 400 KB, va
  en cada correo y se multiplica cuando alguien responde. Las imágenes van por
  `Content-ID` (`cid:`) y el worker las adjunta al enviar.
- Se guarda un **snapshot** del HTML usado al enviar: cambiar la firma mañana no
  debe alterar un correo de hoy.

---

## 7. Notificaciones: iOS es el caso difícil

La mayoría del uso será iPhone, y en iOS el Web Push tiene tres condiciones que
el navegador **no avisa**:

1. **iOS 16.4+**
2. **La PWA tiene que estar instalada** en la pantalla de inicio
3. **`requestPermission()` solo funciona dentro de un gesto del usuario**

Por eso `src/lib/push.js` no llama a la API: la **envuelve** y devuelve un estado
con el motivo, para que `views/Notificaciones.svelte` le diga al usuario qué
hacer. Y en iOS el permiso nunca llega a `'denied'`, se queda en `'default'`: por
eso se exige ver `'granted'` explícitamente.

**El botón de activar tiene que seguir siendo un `onclick`.** Si se mueve a un
`onMount`, en iPhone no aparece ningún diálogo y parece que la app está rota.

El badge tiene **dos formatos** y el SW traduce: en iOS `badge` es un **número**,
en Android es la **URL de una imagen**. Mandar el mismo valor en los dos se ve
mal en alguno.

---

## 8. Trampas de SQL Server 2014 (ya resueltas en las migraciones)

| Trampa | Cómo se resolvió |
|---|---|
| Tope de 900 bytes en índices | Todo lleva `Id INT IDENTITY`; los únicos compuestos son `NVARCHAR(160)` o menos |
| `PK (Id, Carpeta NVARCHAR(500))` = 1004 bytes → **el CREATE TABLE falla** | Clave surrogada |
| Collation case-insensitive: `INBOX` y `inbox` colisionan | `COLLATE ..._BIN2` en columnas de carpeta |
| Índice de prefijo no existe | `EndpointHash` calculado y `PERSISTED` + hash SHA2_256 |
| `executemany` no existe | bucles |
| `NOW()` / `LIMIT` / `AUTO_INCREMENT` / `ON DUPLICATE KEY` | `GETDATE()` / `TOP` / `IDENTITY` / UPDATE-then-INSERT |
| `VARCHAR` rompe acentos y `ñ` | `NVARCHAR` en todo |
| `LONGBLOB` → `NVARCHAR(MAX)` devuelve `str`, no `bytes` | `VARBINARY(MAX)` |
| `TRIM()` no existe en 2014 | `LTRIM(RTRIM(...))` |
| Sin `?` en SQL (DB-Lib) | `%s` |
| `_push_new_mail` armaba un parámetro por UID | tope de 2100 parámetros |
| Columnas nuevas **al final** de la tabla | HUB lee por posición posicional |

---

## 9. Reglas del service worker

- **Solo intercepta GET.** `respondWith(fetch(request))` sobre POST/PUT con
  FormData **pierde el body** → el backend recibe `size=0` → FastAPI 422. Ya se
  rompió dos veces en el ecosistema.
- `api/`, `docs/` y `openapi.json` **nunca** se cachean: un correo listado desde
  caché puede ser uno que el usuario ya borró.
- Navegaciones: red primero, y **solo** se guarda la respuesta si fue buena.
  Cachear un 403 envenena el armazón y no se recupera sin borrar la caché a mano.

---

## 10. Comandos

```bash
npm install && npm run build          # compila a dist/ (dist/ NO se versiona)
npm run dev                           # vite en :5174
npm run iconos                        # regenera el logo y los 9 iconos

python3 -m py_compile api/*.py tools/*.py
python3 tools/test_sanitizador.py     # 35 casos, sin base de datos
bash tools/prueba_visual/capturar.sh 430|900|1440   # renderiza la home

python ECCSA-Shell/tools/sync_shell.py --target . --check
```

### El logo

El PNG de origen trae el globo y la palabra "Mail". `tools/generar_iconos.py` los
parte solo (busca la mayor banda de filas vacías entre ambos) y genera el set
completo: `public/mailbox_logo.png` (lockup, para el splash), `public/mailbox_marca.png`
(solo el globo, para los iconos y el chip del header) y los 9 iconos del PWA.

Los iconos se hacen desde **la marca y no del lockup** porque Android recorta a
círculo con un safe zone del 80% e iOS redondea esquinas: con el texto abajo, se
cortaría. Y el `apple-touch-icon.png` va **sin alfa** sobre `--color-bg`, porque
iOS pinta el alfa como negro.

⚠️ **La fuente es chica**: el contenido real del PNG ocupa ~210×255 px, así que
ampliar a 512 es un factor de ~2.4 y los iconos grandes salen suaves. Con un
original de 1024+ el salto de calidad es notorio; basta con
`npm run iconos -- <ruta_del_nuevo.png>`.

---

## 11. Migraciones

Van en `migrations/NNNN_nombre.sql`, numeradas desde `0048`. **La serie es
independiente** de la del HUB pero comparte la tabla `schema_migrations` (que hoy
vive en `WorkersAdmon`, con `apply_migrations.py`).

Reglas: **idempotentes** (`IF COL_LENGTH(...) IS NULL`, `IF NOT EXISTS (SELECT 1
FROM sys.tables ...)`) · `GO` solo en su línea · cabecera con `-- Migración`,
`-- Fecha`, `-- Descripción` y **por qué** · columnas nuevas al final.

**Probar primero en `ECCSA_Admon_Pruebas`.**

---

## 12. Deploy

El servidor es **WebbApps (Debian) 10.188.141.17**, no ServerVM. Ver
`deploy/DEPLOY.md`.

- Puerto host **8104** → 8000 del contenedor
- Imagen `ghcr.io/hector1516/eccsa-mailbox`, el CI compila en `ubuntu-latest` y
  el servidor solo hace `docker pull` (1 vCPU / 1.9 GB no compila nada)
- Secrets en `/etc/mailbox.env` (600 root:root), **nunca** en GitHub
- `APP_AUTO_START=0`: un push **no** cambia producción; alguien arranca a mano
- Crear el contenedor es la lógica compartida de `/opt/apps/_lib/run_app.sh`;
  Mailbox solo aporta `deploy/app.conf`

---

## 13. Seguridad (no negociables)

1. **El visor de correos va en `<iframe sandbox>` SIN `allow-scripts`.** Nunca
   `innerHTML`. El HTML de un correo ajeno es un vector de XSS y de phishing.
2. **Imágenes remotas bloqueadas por defecto** con botón "Cargar imágenes":
   si no, leer un correo confirma que estás vivo al que lo mandó.
3. **Validar el acceso por request en cada descarga.** Las cuentas son
   compartidas: `_cuenta_del_usuario` comprueba el vínculo y devuelve 404 (no
   403, que confirmaría que el buzón existe).
4. **Credenciales cifradas** (Fernet), clave en un archivo del volumen del
   worker. **Esa clave tiene que estar en el respaldo** o las cuentas quedan
   ilegibles.
5. **Suscripciones push propias** (`HUB_MailboxSuscripciones`), no
   `HUB_PushSubscriptions`: la global está indexada por usuario **sin columna de
   app**, y compartirla haría que un aviso de correo saliera como alerta de
   kilómetros.

---

## 14. Lo que falta (por fases)

| Fase | Estado |
|---|---|
| 0 · esqueleto, shell, login, home | ✅ hecho |
| 1 · migraciones, `db.py`, cuentas | ✅ esquema listo · falta el panel que las crea |
| 2 · `mailbox_worker` (sync) | ⬜ pendiente — es lo más risky, va primero |
| 3 · lectura, búsqueda, streaming | ⬜ el listado ya existe; falta el visor y el worker |
| 4 · firmas completas | ⬜ CRUD y sanitizado listos; falta el editor rico con imágenes |
| 5 · envío | ⬜ falta la cola y el worker SMTP |
| 6 · reglas y auto-respuestas | ⬜ falta |