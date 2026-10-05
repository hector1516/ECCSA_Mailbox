# Deploy — Mailbox ECCSA

`https://mailbox.ecc-sa.com.mx` → Cloudflare → **WebbApps (Debian) `10.188.141.17:8104`**

OJO: este es el esquema **nuevo** (Linux), no el de ServerVM con PowerShell y
`schtasks`. La diferencia no es un cambio de estilo: en Debian el script de
deploy es la lógica compartida de `/opt/apps/_lib/`, y una app nueva es **un
archivo de datos**, no un script nuevo.

- Formato y reglas: `/opt/apps/_lib/ESTANDAR.md` (en el servidor)
- Ejemplo de referencia: `WorkersAdmon` (`migracion/workersadmon/deploy-linux.yml`)

---

## 1. Topología

| | |
|---|---|
| Servidor | WebbApps, Debian, `10.188.141.17` |
| Recursos | 1 vCPU · 1.9 GB RAM · el build **no** corre ahí |
| Puerto host | **8104** → 8000 del contenedor (8000/8200 son de workersadmon, 8100 field, 8101 dashboard, 8103 admon) |
| Contenedor | `mailbox` |
| Imagen | `ghcr.io/hector1516/eccsa-mailbox` |
| Red | `mailbox_net` |
| Volumen | `mailbox_data:/data/mailbox` (cuerpos + inline; **no** adjuntos) |
| Secrets | `/etc/mailbox.env` (600 root:root) |
| Subdominio | `*.ecc-sa.com.mx` → el host |

## 2. Qué hay que hacer UNA vez (necesita root)

El usuario `deploy` tiene sudo **acotado a rutas exactas** (`docker` y los tres
scripts de `_lib/`), así que esto no lo puede hacer el CI:

```bash
ssh <root>@10.188.141.17

sudo mkdir -p /opt/apps/mailbox
sudo cp app.conf /opt/apps/mailbox/app.conf

sudo install -m 600 -o root -g root /dev/null /etc/mailbox.env
sudo nano /etc/mailbox.env      # ver deploy/env.local.example
```

`/etc/mailbox.env`:

```ini
HUB_DB_SERVER=10.188.141.15
HUB_DB_USER=sa
HUB_DB_PASSWORD=<la de producción>
HUB_DB_DATABASE=ECCSA_Admon
```

Y, si la app debe abrir la base por **nombre de contenedor** en vez de por TCP:
`sudo docker network create mailbox_net` (Mailbox usa la IP, así que normalmente
ya existe).

## 3. Primer despliegue (con `deploy`, sin root)

```bash
ssh deploy@10.188.141.17

sudo /usr/bin/bash /opt/apps/_lib/check-ports.sh mailbox   # SIEMPRE primero
sudo -E /usr/bin/bash /opt/apps/_lib/run_app.sh mailbox
sudo /usr/bin/bash /opt/apps/_lib/verify_app.sh mailbox
sudo docker start mailbox          # APP_AUTO_START=0
```

> `sudo -E` solo hace falta en esta **primera** corrida manual. El CI no lo usa:
> los secretos salen de `/etc/mailbox.env` y no hay que pasarlos por el comando
> remoto, así que no se necesita la tag `SETENV`.

## 4. Deploys siguientes (automático)

Push a `main` → `deploy-linux.yml`:

1. `desbloquear` — cancela deploys atascados >15 min (si no hay runner
   self-hosted registrado en el repo, es casi siempre eso)
2. `build` — `npm ci && npm run build` + `docker build` + push a GHCR, en
   `ubuntu-latest`
3. `deploy` — `docker pull`, `_lib/run_app.sh mailbox`, y **no lo arranca**

**Un push no cambia producción.** El contenedor queda en `created` porque
`APP_AUTO_START=0`. Alguien decide cuándo arrancarlo. Si fuera `1`, cualquier
push a `main` tocaría producción sin que nadie lo pidiera.

## 5. Verificar que quedó bien

```bash
ssh deploy@10.188.141.17
sudo /usr/bin/bash /opt/apps/_lib/verify_app.sh mailbox
sudo docker logs --tail 40 mailbox
curl -s http://localhost:8104/health
```

⚠️ **Un `/health` con 200 no prueba nada del frente.** Siempre responde 200,
incluso sin credenciales de base — por eso `run_app.sh` aborta si faltan los
`APP_REQUIRES_ENV`. Lo que sí hay que mirar:

```bash
curl -s -H "Authorization: Bearer <token>" http://localhost:8104/api/shell/state
curl -s http://localhost:8104/ | head -5          # ¿el bundle nuevo?
docker exec mailbox ls /app/assets               # ¿el hash del JS cambió?
```

Grep por texto de UI dentro de `api/main.py` **no prueba nada**: el frontend está
compilado en `dist/assets/index-<hash>.js`. Ese hash es la única prueba válida.

## 6. Rollback

Cada deploy taguea la imagen con el SHA del commit, así que volver atrás es
desplegar otro SHA:

```bash
sudo docker images ghcr.io/hector1516/eccsa-mailbox

sudo docker rm mailbox
sudo APP_IMAGE_OVERRIDE=ghcr.io/hector1516/eccsa-mailbox:<sha-anterior> \
  /usr/bin/bash /opt/apps/_lib/run_app.sh mailbox
sudo docker start mailbox
```

## 7. Cloudflare

`mailbox.ecc-sa.com.mx` apunta al host por Cloudflare. Dos cosas importan:

- **El SSL del origen.** Con el plan Full (strict), el origen necesita un
  certificado válido para ese hostname. Si el server tiene el de `*.ecc-sa.com.mx`,
  funciona; si no, hace falta un Origin Certificate de Cloudflare en el host.
- **Streaming de adjuntos.** Los adjuntos se transmiten en trozos, así que el
  time-to-first-byte es bajo y no se dispara el 524. Aun así, un archivo muy
  grande puede acercarse al límite de 100 s de Cloudflare: si se ve fallando, la
  respuesta correcta **no** es agrandar el timeout en la app, es avisar al usuario
  del tamaño antes de descargar (ya está el tamaño en el índice).

`X-Forwarded-For` lo agrega Cloudflare y `api/lugar.py` lo lee primero para
decidir 🏢/🏠. **No** leer `X-Real-IP` primero: eso haría que todo el mundo salga
"oficina".

## 8. Required en GitHub

| Secret | Para qué |
|---|---|
| `DEPLOY_SSH_KEY` | la clave privada del usuario `deploy` |
| `GITHUB_TOKEN` | ya existe; permisos `packages: write` para GHCR |

La contraseña de la base **no** está en GitHub: vive solo en
`/etc/mailbox.env`. El build de la imagen no se conecta a la base, así que no la
necesita.

## 9. Fases siguientes

- **Fase 2** (`mailbox_worker`): necesita tocar `workersadmon` — un
  `cron_sync_mailbox.py`, un `mailbox_worker.conf` en `docker/conf.d.available/`,
  un `panel/views/correo.py` para crear y asignar cuentas, y agregarlo a
  `panel/spec.py` y `panel/workers.py`. **Con un solo worker de instancia**: ver
  `AGENTS.md` de WorkersAdmon y usar `sp_getapplock`, no `GET_LOCK` (esa es de
  MySQL y Mailbox usa SQL Server).
- **Volumen `mailbox_data`**: crearlo antes del primer sync y medir el espacio
  libre del ServerVM. La cuota dura está en `HUB_Config` con la clave
  `mailbox_cuerta_datos_mb`.
- **Share `\\Fileserver\hub\Mailbox`**: hay que crearlo y dar acceso de escritura
  al usuario SMB antes de subir imágenes de firma.