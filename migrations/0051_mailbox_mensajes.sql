-- ═══════════════════════════════════════════════════════════════════════════════
-- Migración 0051: mensajes, adjuntos, reglas, respuestas automáticas y colas
-- ═══════════════════════════════════════════════════════════════════════════════
-- Fecha: 2026-10-05
--
-- Por qué el índice de mensajes SÍ vive en la base, y los adjuntos NO
-- ------------------------------------------------------------------
-- El índice es pequeño y es lo que hace útil la app: de 300 bytes por mensaje,
-- 100,000 mensajes son ~30 MB. Con eso la búsqueda y el listado se hacen con
-- el mismo pymssql que ya usa todo el ecosistema y sin infrastructure extra.
--
-- Los adjuntos son lo otro: un archivo de 200 MB × 100,000 mensajes no cabe ni
-- en un disco de 2 TB. Y no hacen falta guardados: se TRANSMITEN al dispositivo
-- cuando el usuario los abre. Ver AGENTS.md §5.
--
-- El CUERPO sí se guarda, comprimido con gzip, en el volumen del worker
-- (ClaveCuerpo apunta ahí). Retención en dos niveles:
--   0–90 días   → headers + cuerpo + inline  (lectura completa)
--   90 días–1 año → solo headers             (búsqueda y contexto, sin abrir)
--   >1 año        → nada
-- El campo CuerpoTruncado marca la diferencia entre "no hay cuerpo" y "ya se
-- borró el cuerpo por retención", porque la vista necesita decir exactamente
-- eso en vez de un error genérico.
--
-- Quién escribe cada tabla
-- -----------------------
--   HUB_MailboxMensajes / Adjuntos   → el WORKER (índice y manifiesto)
--   HUB_MailboxReglas / AutoRespuestas → la APP (el usuario las crea)
--   HUB_MailboxColaOperaciones       → la APP escribe · el WORKER ejecuta en IMAP
--   HUB_MailboxColaEnvio             → la APP escribe · el WORKER manda por SMTP
--
-- Es el patrón completo: la app nunca habla IMAP ni SMTP, solo encola.
-- ═══════════════════════════════════════════════════════════════════════════════

GO

-- ── 1. Índice de mensajes ─────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxMensajes')
BEGIN
    CREATE TABLE dbo.HUB_MailboxMensajes (
        -- BIGINT: 100k mensajes por cuenta × 20 cuentas = 2M filas. INT aguanta
        -- de sobra, pero BIGINT deja margen sin costo real en el índice.
        Id              BIGINT IDENTITY(1,1) PRIMARY KEY,

        IdCuenta        INT            NOT NULL,
        -- UID de IMAP. Es el identificador estable del mensaje en su carpeta:
        -- el número de secuencia se corre en cuanto alguien borra algo.
        UID             INT            NOT NULL,

        -- El header Message-ID. Sirve para re-deduplicar: IMAP a veces entrega
        -- el mismo mensaje dos veces (sobre todo tras un reconnect mal hecho).
        MessageId       NVARCHAR(500)  NULL,

        -- COLLATE ..._BIN2: el collation por defecto de SQL Server es
        -- case-INsensitive y `INBOX` y `inbox` se confundirían. MySQL necesitó
        -- la migración 0002 por lo mismo; aquí se resuelve de una vez.
        Carpeta         NVARCHAR(200) COLLATE Latin1_General_100_BIN2 NOT NULL,

        RemitenteNombre NVARCHAR(200)  NULL,
        RemitenteEmail NVARCHAR(320)  NULL,
        ParaTexto       NVARCHAR(1000) NULL,
        CcTexto         NVARCHAR(1000) NULL,
        Asunto          NVARCHAR(500)  NULL,

        -- Extracto: los primeros ~200 caracteres del texto plano, para pintar la
        -- lista sin leer el cuerpo del disco.
        Extracto        NVARCHAR(500)  NULL,

        FechaCorreo     DATETIME       NULL,
        FechaIngesta    DATETIME       NOT NULL DEFAULT GETDATE(),

        Visto           BIT            NOT NULL DEFAULT 0,
        Marcado         BIT            NOT NULL DEFAULT 0,
        Respondido      BIT            NOT NULL DEFAULT 0,

        TieneAdjuntos   BIT            NOT NULL DEFAULT 0,
        NumAdjuntos     INT            NOT NULL DEFAULT 0,

        -- ── Cuerpo ──────────────────────────────────────────────────────────
        -- Clave RELATIVA dentro del volumen del worker. Nunca absoluta: una
        -- ruta absoluta se rompe si el volumen se mueve.
        ClaveCuerpo     NVARCHAR(200)  NULL,
        BytesCuerpo     INT            NULL,
        CuerpoGuardado  BIT            NOT NULL DEFAULT 0,
        -- TRUE = el cuerpo se borró por retención pero el mensaje sigue
        -- listándose. La vista dice "ya no está disponible" en vez de fallar.
        CuerpoTruncado  BIT            NOT NULL DEFAULT 0,

        -- Marca de borrado con ventana de gracia. El usuario la pulsa y se
        -- encola; hasta que el worker la ejecuta en IMAP el mensaje sigue
        -- visible (ver HUB_MailboxColaOperaciones).
        Eliminado       BIT            NOT NULL DEFAULT 0,
        Etiqueta        NVARCHAR(60)   NULL,

        CONSTRAINT FK_MailboxMensajes_Cuenta
            FOREIGN KEY (IdCuenta) REFERENCES dbo.HUB_MailboxCuentas(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxMensajes creada';
END
ELSE
    PRINT 'HUB_MailboxMensajes ya existe';
GO

-- Idéntico por (cuenta, carpeta, UID). Son 4 + 4 + 400 = 448 bytes: dentro del
-- tope de 900, así que sí puede ser UNIQUE. Este es el índice que hace que el
-- upsert del worker sea idempotente: re-sincronizar no duplica nada.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_HUB_MailboxMensajes_Uid'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxMensajes'))
BEGIN
    CREATE UNIQUE INDEX UX_HUB_MailboxMensajes_Uid
        ON dbo.HUB_MailboxMensajes (IdCuenta, Carpeta, UID);
    PRINT 'indice unico (cuenta, carpeta, uid) creado';
END
GO

-- El listado de la app: `WHERE IdCuenta=? AND Carpeta=? ORDER BY FechaCorreo DESC`.
-- Es LA consulta más caliente de la app, y sin este índice es un sort de toda la
-- tabla en cada apertura de carpeta.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxMensajes_Lista'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxMensajes'))
BEGIN
    CREATE INDEX IX_HUB_MailboxMensajes_Lista
        ON dbo.HUB_MailboxMensajes (IdCuenta, Carpeta, FechaCorreo DESC)
        INCLUDE (Asunto, RemitenteNombre, RemitenteEmail, Visto, TieneAdjuntos, NumAdjuntos);
END
GO

-- El contador de no leídos de la home y del badge del ícono:
-- `WHERE IdCuenta IN (...) AND Visto=0 AND Carpeta='INBOX'`.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxMensajes_NoLeidos'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxMensajes'))
BEGIN
    CREATE INDEX IX_HUB_MailboxMensajes_NoLeidos
        ON dbo.HUB_MailboxMensajes (IdCuenta, Carpeta, Visto)
        INCLUDE (FechaCorreo);
END
GO

-- La purga de retención corre cada ciclo del worker:
-- `WHERE FechaCorreo < @corte AND IdCuenta=?`. Sin índice es un scan completo
-- de la tabla por cuenta, por ciclo.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxMensajes_Retencion'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxMensajes'))
BEGIN
    CREATE INDEX IX_HUB_MailboxMensajes_Retencion
        ON dbo.HUB_MailboxMensajes (IdCuenta, FechaCorreo);
END
GO

GO

-- ── 2. Manifiesto de adjuntos ────────────────────────────────────────────────
-- Solo la metadata. Los bytes NO están aquí: se piden por IMAP al abrir el
-- mensaje, y el worker los transmite (ver AGENTS.md §5).
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxAdjuntos')
BEGIN
    CREATE TABLE dbo.HUB_MailboxAdjuntos (
        Id              BIGINT IDENTITY(1,1) PRIMARY KEY,
        IdMensaje       BIGINT        NOT NULL,

        -- ── LA COLUMNA CLAVE ──────────────────────────────────────────────
        -- El "part number" de IMAP: la ruta de la parte MIME dentro del
        -- mensaje. '2.1' es la segunda parte de nivel superior, primer adjunto.
        --
        -- Es lo que permitepedir EXACTAMENTE un adjunto sin bajar el mensaje
        -- entero: `UID FETCH <uid> (BODY.PEEK[2.1])`. Es lo que hace viable el
        -- modelo de streaming: abrir un PDF de 40 MB no baja los otros 39.
        Parte           NVARCHAR(20)   NOT NULL,

        Nombre          NVARCHAR(255)  NOT NULL,
        ContentType     NVARCHAR(100)  NULL,
        -- Content-ID del header, para el <img src="cid:..."> del cuerpo.
        Cid             NVARCHAR(80)   NULL,
        Size            INT            NOT NULL DEFAULT 0,

        -- Inline = el navegador lo pinta dentro del texto (logos del remitente).
        -- Los inline SÍ se guardan en disco, porque sin ellos el mensaje se ve
        -- roto y hacen falta N peticiones IMAP por cada lectura.
        EsInline        BIT            NOT NULL DEFAULT 0,
        InlineGuardado  BIT            NOT NULL DEFAULT 0,

        -- Escape hatch: si el usuario marca el adjunto como "guardar para
        -- offline", aquí aparece la ruta en el share. Nunca es automático.
        ClaveSMB        NVARCHAR(400)  NULL,
        GuardadoOffline BIT            NOT NULL DEFAULT 0,

        CONSTRAINT FK_MailboxAdjuntos_Mensaje
            FOREIGN KEY (IdMensaje) REFERENCES dbo.HUB_MailboxMensajes(Id) ON DELETE CASCADE,
        -- (mensaje, parte) es la identidad lógica de un adjunto. 8 + 40 bytes.
        CONSTRAINT UX_MailboxAdjuntos_Parte UNIQUE (IdMensaje, Parte)
    );
    PRINT 'HUB_MailboxAdjuntos creada';
END
ELSE
    PRINT 'HUB_MailboxAdjuntos ya existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxAdjuntos_Cid'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxAdjuntos'))
BEGIN
    -- Al renderizar el cuerpo se resuelve cada src="cid:x" con esta fila.
    CREATE INDEX IX_HUB_MailboxAdjuntos_Cid
        ON dbo.HUB_MailboxAdjuntos (IdMensaje, Cid);
END
GO

GO

-- ── 3. Cola de operaciones sobre el buzón ────────────────────────────────────
-- El patrón completo de la app: escribe una fila, el worker la ejecuta en IMAP.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxColaOperaciones')
BEGIN
    CREATE TABLE dbo.HUB_MailboxColaOperaciones (
        Id          BIGINT IDENTITY(1,1) PRIMARY KEY,
        IdCuenta    INT           NOT NULL,
        IdUsuario   INT           NOT NULL,
        IdMensaje   BIGINT        NOT NULL,

        -- seen | flag | delete | move
        Operacion   VARCHAR(20)    NOT NULL,
        -- El valor depende de la operación: "1"/"0" para seen, "" para delete,
        -- la carpeta destino para move. Se guarda como texto y no como BIT para
        -- que una operación nueva no exija ALTER TABLE.
        Valor       NVARCHAR(200) NULL,

        -- PENDIENTE | APLICADA | ERROR
        Estado      VARCHAR(20)    NOT NULL DEFAULT 'PENDIENTE',
        Intentos    INT            NOT NULL DEFAULT 0,
        Error       NVARCHAR(500)  NULL,
        Creado      DATETIME       NOT NULL DEFAULT GETDATE(),
        Aplicado    DATETIME       NULL,

        CONSTRAINT FK_MailboxColaOps_Mensaje
            FOREIGN KEY (IdMensaje) REFERENCES dbo.HUB_MailboxMensajes(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxColaOperaciones creada';
END
ELSE
    PRINT 'HUB_MailboxColaOperaciones ya existe';
GO

-- La pregunta que hace el worker en cada ciclo: "qué hay pendiente, más viejo
-- primero". Un índice compuesto sobre las dos columnas es exactamente eso.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_MailboxColaOps_Pendientes'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxColaOperaciones'))
BEGIN
    CREATE INDEX IX_MailboxColaOps_Pendientes
        ON dbo.HUB_MailboxColaOperaciones (Estado, Creado);
END
GO

GO

-- ── 4. Cola de envío ─────────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxColaEnvio')
BEGIN
    CREATE TABLE dbo.HUB_MailboxColaEnvio (
        Id              BIGINT IDENTITY(1,1) PRIMARY KEY,
        IdCuenta        INT           NOT NULL,
        IdUsuario       INT           NOT NULL,
        IdFirma         INT           NULL,   -- qué firma se aplicó

        Para            NVARCHAR(2000) NOT NULL,
        Cc              NVARCHAR(2000) NULL,
        Bcc             NVARCHAR(2000) NULL,
        Asunto          NVARCHAR(500)  NULL,

        -- ── SNAPSHOT, no referencia ─────────────────────────────────────────
        -- El HTML tal como se envió, con los cid ya resueltos. Si no fuera
        -- snapshot, editar la firma mañana reescribiría la historia de todos
        -- los correos enviados. Ver AGENTS.md §6.
        HtmlSnapshot    NVARCHAR(MAX) NULL,
        -- Fallback en texto plano para clientes que no pintan HTML.
        TextoSnapshot   NVARCHAR(MAX) NULL,
        -- Manifiesto JSON de los adjuntos que se mandan: nombre, cid, clave.
        AdjuntosJson    NVARCHAR(MAX) NULL,

        InResponderA    NVARCHAR(500)  NULL,   -- Message-ID, para el hilo
        MessageIdEnviado NVARCHAR(500) NULL,   -- el que asignó el servidor

        -- PENDIENTE | ENVIANDO | ENVIADO | ERROR
        Estado          VARCHAR(20)    NOT NULL DEFAULT 'PENDIENTE',
        Intentos        INT            NOT NULL DEFAULT 0,
        Error           NVARCHAR(1000) NULL,
        Creado          DATETIME       NOT NULL DEFAULT GETDATE(),
        Enviado         DATETIME       NULL,

        CONSTRAINT FK_MailboxColaEnvio_Cuenta
            FOREIGN KEY (IdCuenta) REFERENCES dbo.HUB_MailboxCuentas(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxColaEnvio creada';
END
ELSE
    PRINT 'HUB_MailboxColaEnvio ya existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_MailboxColaEnvio_Pendientes'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxColaEnvio'))
BEGIN
    CREATE INDEX IX_MailboxColaEnvio_Pendientes
        ON dbo.HUB_MailboxColaEnvio (Estado, Creado);
END
GO

GO

-- ── 5. Reglas de filtrado ────────────────────────────────────────────────────
-- Condiciones Y (no hay O ni negación) y en ese orden. La primera que matchea gana.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxReglas')
BEGIN
    CREATE TABLE dbo.HUB_MailboxReglas (
        Id          INT IDENTITY(1,1) PRIMARY KEY,
        IdUsuario   INT           NOT NULL,

        -- Menor número = se evalúa antes.
        Prioridad   INT           NOT NULL DEFAULT 100,

        -- FROM | TO | SUBJECT | BODY | DOMINIO
        Campo       VARCHAR(20)    NOT NULL,
        -- CONTIENE | IGUAL | EMPIEZA | TERMINA | REGEX
        Operador    VARCHAR(20)    NOT NULL DEFAULT 'CONTIENE',
        Valor       NVARCHAR(500)  NOT NULL,

        -- MARCAR_LEIDO | ARCHIVAR | ELIMINAR | ETIQUETAR | NO_HACER
        -- NO_HACER existe para dejar la regla documentada sin aplicarla.
        Accion      VARCHAR(20)    NOT NULL,
        Etiqueta    NVARCHAR(60)   NULL,

        Activa      BIT            NOT NULL DEFAULT 1,
        Creado      DATETIME       NOT NULL DEFAULT GETDATE(),
        UltimaEjecucion DATETIME   NULL,
        VecesEjecutada INT          NOT NULL DEFAULT 0,

        CONSTRAINT FK_MailboxReglas_Usuario
            FOREIGN KEY (IdUsuario) REFERENCES dbo.HUB_Users(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxReglas creada';
END
ELSE
    PRINT 'HUB_MailboxReglas ya existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_MailboxReglas_Usuario'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxReglas'))
BEGIN
    CREATE INDEX IX_MailboxReglas_Usuario
        ON dbo.HUB_MailboxReglas (IdUsuario, Activa, Prioridad);
END
GO

GO

-- ── 6. Respuestas automáticas ────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxRespuestasAuto')
BEGIN
    CREATE TABLE dbo.HUB_MailboxRespuestasAuto (
        Id              INT IDENTITY(1,1) PRIMARY KEY,
        IdUsuario       INT           NOT NULL,
        IdCuenta        INT           NULL,   -- NULL = aplica a todas sus cuentas

        Mensaje         NVARCHAR(MAX) NOT NULL,
        EsDefault       BIT           NOT NULL DEFAULT 0,

        -- Solo fuera de horario: en horario de oficina se ignora y la persona
        -- contesta. Si no, el sistema parece automatizado y molesta.
        SoloFueraHorario BIT          NOT NULL DEFAULT 0,

        -- Dominios exentos: el jefe nunca recibe un "no estoy". Coma.
        ExcepcionesDominio NVARCHAR(500) NULL,

        Activa          BIT           NOT NULL DEFAULT 1,
        Creado          DATETIME      NOT NULL DEFAULT GETDATE(),
        UltimoUso       DATETIME      NULL,

        CONSTRAINT FK_MailboxAutoResp_Usuario
            FOREIGN KEY (IdUsuario) REFERENCES dbo.HUB_Users(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxRespuestasAuto creada';
END
ELSE
    PRINT 'HUB_MailboxRespuestasAuto ya existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_MailboxAutoResp_Usuario'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxRespuestasAuto'))
BEGIN
    CREATE INDEX IX_MailboxAutoResp_Usuario
        ON dbo.HUB_MailboxRespuestasAuto (IdUsuario, Activa);
END
GO

PRINT '0051_mailbox_mensajes.sql aplicada'
GO