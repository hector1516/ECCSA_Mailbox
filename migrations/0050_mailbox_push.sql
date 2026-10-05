-- ═══════════════════════════════════════════════════════════════════════════
-- Migración 0050: suscripciones push de Mailbox
-- ═══════════════════════════════════════════════════════════════════════════
-- Fecha: 2026-10-05
--
-- POR QUÉ UNA TABLA PROPIA Y NO HUB_PushSubscriptions
-- ----------------------------------------------------
-- Ya existe HUB_PushSubscriptions (la usan Field, Admon y el panel de
-- workersadmon) y tiene UN problema para Mailbox: está indexada por
-- `UserEmail` y NO tiene columna de app. Consecuencia: si Mailbox guarda aquí,
-- una suscripción creada desde mailbox.ecc-sa.com.mx queda indistinguible de
-- una creada desde field.ecc-sa.com.mx para el MISMO usuario. Cuando el worker
-- mandara un aviso de correo nuevo, la librería elegiría TODAS las
-- suscripciones de ese usuario y el usuario recibiría también las alertas de
-- kilómetros en el móvil. Notificaciones cruzadas entre apps: exactamente el
-- tipo de cosa que hace que la gente desactive los permisos.
--
-- La alternativa era agregar `App VARCHAR(20)` a HUB_PushSubscriptions, pero eso
-- obliga a tocar el código de Field y del panel y a migrar filas. Romper dos
-- apps que funcionan para no duplicar una tabla de 5 columnas no vale.
--
-- Decisión: tabla propia, CLAVES VAPID COMPARTIDAS. La clave pública/privada se
-- lee de HUB_Config (vapid_private_key / vapid_public_key), la misma que usan
-- las otras apps. Beneficios: una sola llave que rotar, y si algún día se
-- quiere unificar, es un MERGE.
--
-- iOS (que es la mayoría del caso)
-- -------------------------------
-- En iPhone la suscripción push SOLO se crea si la PWA está instalada y el
-- permiso se pidió desde un gesto. El cliente lo verifica antes de pedirla
-- (src/lib/push.js). Acá solo se guarda lo que llegó.
-- ═══════════════════════════════════════════════════════════════════════════

GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxSuscripciones')
BEGIN
    CREATE TABLE dbo.HUB_MailboxSuscripciones (
        Id              INT IDENTITY(1,1) PRIMARY KEY,

        IdUsuario       INT            NOT NULL,

        -- La URL del push service (Apple, Google, Mozilla). Es larga: los
        -- endpoints de Apple son ~180 caracteres. NVARCHAR(2048) son 4096 BYTES,
        -- muy por encima del tope de 900 bytes de un índice de SQL Server, así
        -- que NO se puede indexar directamente (ver EndpointHash abajo).
        Endpoint        NVARCHAR(2048)  NOT NULL,

        -- Hash persistido del endpoint para poder tener un índice ÚNICO sobre
        -- él. Es la salida estándar cuando la columna a indexar excede el tope
        -- de bytes. HASHBYTES con SHA2_256 necesita SQL 2012+, y esto corre en
        -- 2014, así que está disponible.
        --
        -- Por qué importa: sin esto no se puede evitar duplicados y un mismo
        -- dispositivo suscripto dos veces recibe cada correo dos veces.
        EndpointHash    AS (CONVERT(BINARY(32), HASHBYTES('SHA2_256', Endpoint))) PERSISTED,

        P256dhKey       NVARCHAR(512)   NOT NULL,
        AuthKey         NVARCHAR(512)   NOT NULL,

        -- "iOS", "Android", "Chrome de escritorio"… Solo informativo: sirve para
        -- que el panel diga "3 iPhone, 1 PC" en vez de un número pelado.
        Plataforma      NVARCHAR(20)   NULL,

        Creado          DATETIME       NOT NULL DEFAULT GETDATE(),
        UltimoUso       DATETIME       NULL,
        Activo          BIT            NOT NULL DEFAULT 1,

        CONSTRAINT FK_MailboxSuscripciones_Usuario
            FOREIGN KEY (IdUsuario) REFERENCES dbo.HUB_Users(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxSuscripciones creada';
END
ELSE
    PRINT 'HUB_MailboxSuscripciones ya existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_HUB_MailboxSuscripciones_EndpointHash'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxSuscripciones'))
BEGIN
    CREATE UNIQUE INDEX UX_HUB_MailboxSuscripciones_EndpointHash
        ON dbo.HUB_MailboxSuscripciones (EndpointHash);
    PRINT 'indice unico sobre el hash del endpoint creado';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxSuscripciones_Usuario'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxSuscripciones'))
BEGIN
    -- El worker pregunta siempre "las suscripciones activas del usuario X" antes
    -- de mandar un aviso.
    CREATE INDEX IX_HUB_MailboxSuscripciones_Usuario
        ON dbo.HUB_MailboxSuscripciones (IdUsuario, Activo);
END
GO

PRINT '0050_mailbox_push.sql aplicada'
GO