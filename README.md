# Mailbox ECCSA

Buzón corporativo de ECCSA como **PWA**: en el iPhone, en Android y en
escritorio, en `https://mailbox.ecc-sa.com.mx`.

Una tarjeta por cuenta de correo en la home, firmas que se aplican a las cuentas
que elijas, y los adjuntos que se descargan **al dispositivo** cuando los abres
— no se quedan guardados en el servidor.

---

## Qué es y qué no es

> **El buzón tiene un solo dueño, y no es esta app.**

| | Esta app | `mailbox_worker` (workersadmon) |
|---|---|---|
| Habla IMAP / SMTP | **nunca** | ✅ dueño único |
| Ve la contraseña del buzón | **nunca** | ✅ cifrada en reposo |
| Baja los adjuntos | hace de proxy | ✅ hace el fetch |
| Firmas, reglas, cola de envío | ✅ escribe | ✅ ejecuta |

La app escribe filas de cola y el worker las ejecuta contra el buzón. Por eso un
ciclo de sincronización lento **no** puede dejar la app colgada, y por eso la
contraseña de un buzón nunca existe en el navegador.

El detalle completo está en [`AGENTS.md`](AGENTS.md).

---

## Arrancar en local

```bash
npm install
npm run build          # genera dist/  (dist/ NO se versiona)

# la API en otra terminal, apuntando a la base de PRUEBAS
HUB_DB_DATABASE=ECCSA_Admon_Pruebas python3 -m uvicorn api.main:app --port 8000
```

La app necesita que la API esté en el mismo origen. Lo mássimple es `npm run build`
y servir con FastAPI (que expone `dist/` en `/`).

### Migraciones

Este repo trae **su propio** runner. No se usa el de WorkersAdmon: las
migraciones de Mailbox viven acá, y el runner de WorkersAdmon solo mira su
propio `migrations/`.

Los dos escriben en la Misma tabla `schema_migrations`, que es compartida con
HUB/Admon, y por eso los números no chocan: Mailbox arranca en `0048`, justo
después del `0047` que ya existía.

```bash
# contra la base de pruebas, SIEMPRE primero
HUB_DB_DATABASE=ECCSA_Admon_Pruebas python3 apply_migrations.py --dry-run
HUB_DB_DATABASE=ECCSA_Admon_Pruebas python3 apply_migrations.py

# producción, a propósito (pide confirmación escrita)
HUB_DB_DATABASE=ECCSA_Admon HUB_MIGRATE_PRODUCTION=1 python3 apply_migrations.py
```

`0048` permiso `AccesoMailbox` + cuentas + sesiones · `0049` firmas ·
`0050` suscripciones push · `0051` mensajes, adjuntos, colas, reglas y
auto-respuestas.

El runner **aborta** si el destino no es una base de pruebas salvo que se pida
producción explícitamente, y cada archivo corre en su propia transacción. Correrlo
dos veces no cambia nada.

### El logo

```bash
npm run iconos                                  # usa ../Mail/IMG_0417.PNG
npm run iconos -- /ruta/a/logo_grande.png       # o uno mejor
```

Parte el globo y la palabra "Mail" automáticamente y genera `mailbox_logo.png`
(splash), `mailbox_marca.png` (chip del header) y los 9 iconos del PWA.

---

## Herramientas

| | Qué hace |
|---|---|
| `tools/generar_iconos.py` | Logo → `public/` + los 9 iconos del PWA |
| `tools/test_sanitizador.py` | 35 casos del sanitizador de firmas, sin BD |
| `tools/prueba_visual/` | Renderiza la home con el CSS compilado, a 430/900/1440 px |

```bash
python3 tools/test_sanitizador.py
bash tools/prueba_visual/capturar.sh 1440     # → captura-1440px.png
```

La prueba visual existe porque `.module-card` y `.module-badge` los define el
shell y **no se editan en la app**: ver el look real requiere renderizarlo, y
así no hay que reinstalar la PWA en un iPhone para comprobar un contador.

---

## Deploy

`https://mailbox.ecc-sa.com.mx` → Cloudflare → **WebbApps (Debian) 10.188.141.17:8104**.

El CI compila en `ubuntu-latest` y sube a GHCR; el servidor solo hace
`docker pull` (tiene 1 vCPU y 1.9 GB, compilar ahí no entra) y recrea el
contenedor con la lógica compartida de `/opt/apps/_lib/`.

Detalle en [`deploy/DEPLOY.md`](deploy/DEPLOY.md) y en [`AGENTS.md`](AGENTS.md) §12.

---

## Estado

Fases 0 y 1 hechas (esqueleto, shell, login/passkey, home, esquema de base,
firmas con sanitizado, notificaciones con soporte iOS). **Falta el
`mailbox_worker`**, que es lo que baja los correos: sin él la bandeja se ve
vacía a propósito.

| Fase | |
|---|---|
| 0 · esqueleto, shell, login, home | ✅ |
| 1 · migraciones y cuentas | ✅ las 4 aplicadas y verificadas; el panel que las crea vive en WorkersAdmon |
| 2 · `mailbox_worker` (sync) | ✅ código y tests; falta desplegar y aplicar en producción |
| 3 · lectura, búsqueda, streaming | ✅ visor, búsqueda y adjuntos transmitidos en rangos |
| 4 · firmas completas | ✅ editor rico, imágenes con `cid:` y previsualización |
| 5 · envío | ✅ compositor, cola y SMTP con la firma resuelta |
| 6 · reglas y auto-respuestas | ⬄ reglas completas; falta la UI de alta de auto-respuestas |

---

## Stack

**Vite + Svelte 5 + Tailwind v3** (variante `t3` del ECCSA-Shell) ·
**FastAPI + pymssql** contra SQL Server · **Web Push** con VAPID ·
**passkeys** con `rpId` raíz `ecc-sa.com.mx`.

El diseño —tokens, colores, banner, barra de acciones, grilla de módulos— **no
está en este repo**: viene del [ECCSA-Shell](https://github.com/hector1516/ECCSA-Shell),
igual que en Field, Admon y el panel de workersadmon. Si hay que cambiar un color
o una tarjeta, se cambia allá y se propaga; acá no se edita a mano y el CI lo
verifica.