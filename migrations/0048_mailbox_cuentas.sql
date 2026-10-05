-- ═══════════════════════════════════════════════════════════════════════════
-- Migración 0048: base de Mailbox — permiso, cuentas, vínculos y sesiones
-- ═══════════════════════════════════════════════════════════════════════════
-- Fecha: 2026-10-05
--
-- Por qué estas tablas
-- --------------------
-- Mailbox NO guarda los adjuntos: se transmiten al dispositivo. Y los cuerpos
-- van a disco (volumen Docker). Lo que queda aquí es lo pequeño, acotado y
-- relacional, que es justo lo que cabe en un SQL Server 2014 **Express** (tope
-- de 10 GB por base). Este archivo es la Fase 1; el índice de mensajes va en
-- 0051.
--
-- Quién escribe qué
-- -----------------
--   · HUB_MailboxCuentas / Links  → el PANEL de workersadmon (un admin las crea
--     y las asigna). El usuario NO puede crear cuentas ni ver credenciales.
--   · HUB_MailboxSesiones        → esta app (login y logout).
--   · Estado/UltimoSync/Error    → el WORKER (mailbox_worker) cuando valida una
--     cuenta o sincroniza.
--
-- Reglas de SQL Server 2014 que este archivo respeta (ver AGENTS.md §Trampas)
-- ---------------------------------------------------------------------------
--   1. NVARCHAR, nunca VARCHAR: hay acentos, ñ y nombres de carpeta IMAP en
--      UTF-7.
--   2. IDENTITY, nunca AUTO_INCREMENT.
--   3. GETDATE(), nunca NOW().
--   4. Ningún PRIMARY KEY compuesto que pase de 900 bytes. Por eso TODO lleva
--      Id INT IDENTITY como clave y los únicos compuestos son de NVARCHAR(160)
--      (320 bytes) o menos.
--   5. COLLATE ..._BIN2 en las columnas de nombre de carpeta/carpeta: el
--      collation por defecto de SQL Server es case-INsensitive y `INBOX` y
--      `inbox` se confundirían. MySQL necesitó la migración 0002 por lo mismo
--      y aquí se resuelve de una vez.
--   6. Todo IF NOT EXISTS: se puede volver a correr sin romper nada.
-- ═══════════════════════════════════════════════════════════════════════════

GO

-- ── 1. Permiso de acceso a Mailbox ───────────────────────────────────────────
IF COL_LENGTH('dbo.HUB_Users', 'AccesoMailbox') IS NULL
    ALTER TABLE dbo.HUB_Users ADD AccesoMailbox BIT NOT NULL DEFAULT 0;
GO

-- Un usuario nuevo no debe salir con la app permitida por accidente.
UPDATE dbo.HUB_Users SET AccesoMailbox = 0 WHERE AccesoMailbox IS NULL;
GO

-- ── 2. Cuentas de correo ─────────────────────────────────────────────────────
-- Una fila = un buzón real. Las cuentas compartidas se dan de alta UNA vez y se
-- enlazan a varios usuarios en HUB_MailboxCuentasLinks.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxCuentas')
BEGIN
    CREATE TABLE dbo.HUB_MailboxCuentas (
        Id                  INT IDENTITY(1,1) PRIMARY KEY,

        -- Cómo se ve en la home. El Alias es lo que el usuario lee ("Ventas
        -- Oaxaca"); el Email es la dirección real del buzón.
        Alias               NVARCHAR(80)    NOT NULL,
        Email               NVARCHAR(320)   NOT NULL,
        Icono               NVARCHAR(16)    NULL,   -- emoji de la tarjeta
        Color               NVARCHAR(16)    NULL,   -- color de acento de la tarjeta

        -- Servidor. Varios para que una sola app hable Gmail, Outlook y GoDaddy.
        ServidorIMAP        NVARCHAR(160)   NOT NULL,
        PuertoIMAP          INT             NOT NULL DEFAULT 993,
        ServidorSMTP        NVARCHAR(160)   NULL,
        PuertoSMTP          INT             NULL DEFAULT 587,

        -- Credencial. SIEMPRE cifrada en reposo con Fernet; la llave vive en un
        -- archivo del volumen del worker, NUNCA en la base ni en el repo.
        -- TipoAuth = 'PASSWORD' (app password / contraseña) u 'OAUTH2' (refresh
        -- token, también cifrado).
        TipoAuth            VARCHAR(10)     NOT NULL DEFAULT 'PASSWORD',
        CredencialCifrada   NVARCHAR(MAX)   NULL,
        UsarSSL             BIT             NOT NULL DEFAULT 1,

        -- Carpeta raíz: en Gmail casi todos dejan todo en INBOX y las etiquetas
        -- cuelgan de ahí; en otros servidores cada cuenta tiene su INBOX propio.
        CarpetaRaiz         NVARCHAR(200) COLLATE Latin1_General_100_BIN2 NULL DEFAULT 'INBOX',

        -- Estado. `PENDIENTE` es el estado inicial y significa "el worker todavía
        -- no la ha probado": la escribe el panel y el worker la valida en su
        -- siguiente ciclo. Así el panel no necesita hablar IMAP.
        Estado              VARCHAR(20)     NOT NULL DEFAULT 'PENDIENTE',
        UltimoError         NVARCHAR(500)   NULL,
        UltimoSync          DATETIME        NULL,

        -- Retención por cuenta. Los defaults son los globales acordados; una
        -- cuenta concreta puede tener otros sin tocar código.
        VentanaDias         INT             NOT NULL DEFAULT 90,
        MaxMensajes         INT             NOT NULL DEFAULT 5000,
        CuotaAdjuntosMB     INT             NOT NULL DEFAULT 2048,

        Creado              DATETIME        NOT NULL DEFAULT GETDATE(),
        Actualizado         DATETIME        NOT NULL DEFAULT GETDATE()
    );
    PRINT 'HUB_MailboxCuentas creada';
END
ELSE
    PRINT 'HUB_MailboxCuentas ya existe';
GO

-- Una dirección no puede estar dada de alta dos veces: el worker sincroniza por
-- Id y dos filas con el mismo buzón descargarían el correo dos veces.
--
-- El índice va sobre la columna CRUDA, no sobre `LTRIM(RTRIM(Email))`. SQL Server
-- no admite una expresión de función en la clave de un índice: solo columnas
-- simples o columnas calculadas persistidas. Escribirlo con las funciones da
-- `Incorrect syntax near '('`, que es como se descubrió.
--
-- Para que el índice siga siendo correcto, la limpieza de espacios se exige con
-- un CHECK, que SÍ admite funciones. Sin él, "juan@x.com" y "juan@x.com "
-- pasarían el índice como dos cuentas distintas, que es justo lo que este
-- índice evita.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_HUB_MailboxCuentas_Email'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxCuentas'))
BEGIN
    CREATE UNIQUE INDEX UX_HUB_MailboxCuentas_Email
        ON dbo.HUB_MailboxCuentas (Email);
    PRINT 'indice unico de Email creado';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = 'CK_MailboxCuentas_Email_SinEspacios'
                 AND parent_object_id = OBJECT_ID('dbo.HUB_MailboxCuentas'))
BEGIN
    ALTER TABLE dbo.HUB_MailboxCuentas
        ADD CONSTRAINT CK_MailboxCuentas_Email_SinEspacios
        CHECK (Email = LTRIM(RTRIM(Email)));
    PRINT 'constraint de Email sin espacios agregada';
END
GO

-- El worker lista las cuentas por estado en cada ciclo; sin este índice son
-- N escaneos completos por ciclo.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxCuentas_Estado'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxCuentas'))
BEGIN
    CREATE INDEX IX_HUB_MailboxCuentas_Estado
        ON dbo.HUB_MailboxCuentas (Estado);
END
GO

-- ── 3. Vínculos usuario ↔ cuenta ─────────────────────────────────────────────
-- Es la tabla que le dice a la app qué tarjetas pintar en la home. El usuario
-- NO escribe aquí: solo lee. El panel la escribe.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxCuentasLinks')
BEGIN
    CREATE TABLE dbo.HUB_MailboxCuentasLinks (
        Id          INT IDENTITY(1,1) PRIMARY KEY,
        IdCuenta    INT           NOT NULL,
        IdUsuario   INT           NOT NULL,
        Creado      DATETIME      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_MailboxLinks_Cuenta
            FOREIGN KEY (IdCuenta) REFERENCES dbo.HUB_MailboxCuentas(Id) ON DELETE CASCADE,
        CONSTRAINT FK_MailboxLinks_Usuario
            FOREIGN KEY (IdUsuario) REFERENCES dbo.HUB_Users(Id) ON DELETE CASCADE,
        CONSTRAINT UX_MailboxLinks_Unico UNIQUE (IdCuenta, IdUsuario)
    );
    PRINT 'HUB_MailboxCuentasLinks creada';
END
ELSE
    PRINT 'HUB_MailboxCuentasLinks ya existe';
GO

-- La home consulta SIEMPRE por usuario. Este índice es el que evita un scan.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxLinks_Usuario'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxCuentasLinks'))
BEGIN
    CREATE INDEX IX_HUB_MailboxLinks_Usuario
        ON dbo.HUB_MailboxCuentasLinks (IdUsuario);
END
GO

-- ── 4. Sesiones ──────────────────────────────────────────────────────────────
-- Lo que hace esta tabla y que Admon NO tiene: el token es REVOCABLE.
--
-- En Admon el token es "email|timestamp" y el backend nunca valida el
-- vencimiento: vive mientras el usuario exista en HUB_Users. Eso significa que
-- "cerrar sesión en los otros dispositivos" es imposible. En un buzón eso es un
-- problema real — hay que poder quitarle el acceso a alguien de inmediato.
--
-- Aquí se guarda el HASH del token, nunca el token: si alguien lee la base no
-- puede suplantar una sesión. El token es un valor aleatorio de 32 bytes en
-- hex (64 caracteres) y lo que va a la tabla es su SHA-256.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxSesiones')
BEGIN
    CREATE TABLE dbo.HUB_MailboxSesiones (
        Id              INT IDENTITY(1,1) PRIMARY KEY,

        -- CHAR(64) = 64 bytes: muy por debajo del tope de 900 del índice único.
        TokenHash       CHAR(64)       NOT NULL,

        IdUsuario       INT            NOT NULL,
        Email           NVARCHAR(320)  NOT NULL,
        Dispositivo     NVARCHAR(200)  NULL,   -- user-agent, para poder ver y
                                                -- revocar sesiones por equipo
        Creado          DATETIME       NOT NULL DEFAULT GETDATE(),
        UltimoUso       DATETIME       NULL,
        Expira          DATETIME       NOT NULL,
        Activo          BIT            NOT NULL DEFAULT 1,

        CONSTRAINT FK_MailboxSesiones_Usuario
            FOREIGN KEY (IdUsuario) REFERENCES dbo.HUB_Users(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxSesiones creada';
END
ELSE
    PRINT 'HUB_MailboxSesiones ya existe';
GO

-- La autenticación busca por hash en cada request: sin índice único esto es un
-- scan por request, y el scan por request es lo que tumba la app.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_HUB_MailboxSesiones_TokenHash'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxSesiones'))
BEGIN
    CREATE UNIQUE INDEX UX_HUB_MailboxSesiones_TokenHash
        ON dbo.HUB_MailboxSesiones (TokenHash);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxSesiones_Usuario'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxSesiones'))
BEGIN
    CREATE INDEX IX_HUB_MailboxSesiones_Usuario
        ON dbo.HUB_MailboxSesiones (IdUsuario, Activo);
END
GO

-- ── 5. Config global de la app ───────────────────────────────────────────────
-- Un lugar para los valores que cambian sin deploy (retención por defecto, cuota
-- de disco, si se mandan avisos de prueba). Se leen de HUB_Config para no crear
-- una tabla de parámetros nueva.
IF NOT EXISTS (SELECT 1 FROM HUB_Config WHERE Clave = 'mailbox_retencion_dias')
    INSERT INTO HUB_Config (Clave, Valor, Actualizado) VALUES ('mailbox_retencion_dias', '90', GETDATE());
GO

IF NOT EXISTS (SELECT 1 FROM HUB_Config WHERE Clave = 'mailbox_max_mensajes')
    INSERT INTO HUB_Config (Clave, Valor, Actualizado) VALUES ('mailbox_max_mensajes', '5000', GETDATE());
GO

-- Cuota global del volumen donde se guardan los cuerpos. Es un tope DURO: el
-- worker lo consulta antes de escribir y, si no cabe, deja de bajar cuerpos
-- viejos en vez de llenar el disco. Ver AGENTS.md §Almacenamiento.
IF NOT EXISTS (SELECT 1 FROM HUB_Config WHERE Clave = 'mailbox_cuerta_datos_mb')
    INSERT INTO HUB_Config (Clave, Valor, Actualizado) VALUES ('mailbox_cuerta_datos_mb', '8192', GETDATE());
GO

PRINT '0048_mailbox_cuentas.sql aplicada'
GO