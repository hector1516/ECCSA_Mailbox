-- ─────────────────────────────────────────────────────────────────────────────
-- Migración 0056 — Triaje de correo
-- Fecha: 2026-10-24
--
-- POR QUÉ
-- El worker ya indexa cada mensaje, pero no guarda las cabeceras que distinguen
-- un correo de persona de uno de publicidad (Auto-Submitted, Precedence,
-- List-Unsubscribe, List-Id) ni el veredicto de autenticación. Sin ellas, la
-- única forma de clasificar sería mandar cada mensaje a la IA, que es justo lo
-- que se quiere evitar.
--
-- Estas columnas se llenan en la ingesta (mailbox_worker/imap_client.py y
-- sync.py) y son la base de las reglas deterministas de triaje.py.
--
-- Todo es aditivo e idempotente: se puede correr dos veces.
-- ─────────────────────────────────────────────────────────────────────────────

IF COL_LENGTH('dbo.HUB_MailboxMensajes', 'EsBulk') IS NULL
    ALTER TABLE dbo.HUB_MailboxMensajes
        ADD EsBulk BIT NOT NULL CONSTRAINT DF_HMM_EsBulk DEFAULT 0;
GO

IF COL_LENGTH('dbo.HUB_MailboxMensajes', 'AutoSubmitted') IS NULL
    ALTER TABLE dbo.HUB_MailboxMensajes
        ADD AutoSubmitted BIT NOT NULL CONSTRAINT DF_HMM_AutoSubmitted DEFAULT 0;
GO

IF COL_LENGTH('dbo.HUB_MailboxMensajes', 'TieneLista') IS NULL
    ALTER TABLE dbo.HUB_MailboxMensajes
        ADD TieneLista BIT NOT NULL CONSTRAINT DF_HMM_TieneLista DEFAULT 0;
GO

IF COL_LENGTH('dbo.HUB_MailboxMensajes', 'AuthResultado') IS NULL
    ALTER TABLE dbo.HUB_MailboxMensajes
        ADD AuthResultado VARCHAR(20) NULL;
GO
-- 20 caracteres: 'pass', 'fail', 'softfail', 'none' o NULL si el servidor no
-- manda Authentication-Results. No se guarda la cabecera entera: solo el
-- veredicto de dmarc/spf/dkim, que es lo que usa el clasificador.


IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxClasificacion')
BEGIN
    CREATE TABLE dbo.HUB_MailboxClasificacion (
        Id              BIGINT IDENTITY(1,1) PRIMARY KEY,
        IdMensaje       BIGINT        NOT NULL,
        IdCuenta        INT           NOT NULL,

        RemitenteEmail  NVARCHAR(320) NULL,
        -- El destinatario que resultó huérfano (puede venir en Cc: "copiaron a
        -- alguien por error"). NULL cuando la categoría no es 'huerfano'.
        Destinatario    NVARCHAR(320) NULL,

        -- bulk | rebote | interno | respuesta | activo | huerfano | normal
        Categoria       VARCHAR(20)   NOT NULL,
        Confianza       DECIMAL(3,2)  NULL,
        -- regla | ia | manual
        Metodo          VARCHAR(8)    NOT NULL,
        Motivo          NVARCHAR(400) NULL,

        DestinoSugerido NVARCHAR(320) NULL,
        BorradorAsunto  NVARCHAR(500) NULL,
        BorradorTexto   NVARCHAR(MAX) NULL,

        -- NUEVA | APROBADA | RECHAZADA | ENVIADA | IGNORADA
        Estado          VARCHAR(12)   NOT NULL CONSTRAINT DF_HMC_Estado DEFAULT 'NUEVA',

        Modelo          VARCHAR(60)   NULL,
        TokensIn        INT           NULL,
        TokensOut       INT           NULL,

        Creado          DATETIME      NOT NULL CONSTRAINT DF_HMC_Creado DEFAULT GETDATE(),
        Revisado        DATETIME      NULL,
        RevisadoPor     NVARCHAR(200) NULL
    );

    -- Un mensaje se clasifica UNA vez. Es la garantía de no volver a gastar
    -- tokens en el mismo correo en cada ciclo.
    CREATE UNIQUE INDEX UX_MailboxClasificacion_Mensaje
        ON dbo.HUB_MailboxClasificacion (IdMensaje);

    CREATE INDEX IX_MailboxClasificacion_Estado
        ON dbo.HUB_MailboxClasificacion (Estado, Creado DESC);
END
GO


IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxDirecciones')
BEGIN
    CREATE TABLE dbo.HUB_MailboxDirecciones (
        Email        NVARCHAR(320) NOT NULL PRIMARY KEY,
        -- auto | activa | exempleado
        -- 'auto' = resolver contra HUB_Users en cada clasificación.
        -- Los otros dos son un override manual del operador (una dirección que
        -- no está en HUB_Users pero sí es de alguien, o al revés).
        Estado       VARCHAR(16)   NOT NULL CONSTRAINT DF_HMD_Estado DEFAULT 'auto',
        IdUsuario    INT           NULL,
        -- A dónde mandar a quien se equivocó. NULL = usar el destino por
        -- defecto de HUB_Config (triaje_destino_defecto).
        Destino      NVARCHAR(320) NULL,
        Nota         NVARCHAR(300) NULL,
        Actualizado  DATETIME      NOT NULL CONSTRAINT DF_HMD_Act DEFAULT GETDATE()
    );
END
GO
