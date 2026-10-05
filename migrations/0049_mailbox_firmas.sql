-- ═══════════════════════════════════════════════════════════════════════════
-- Migración 0049: firmas de correo
-- ═══════════════════════════════════════════════════════════════════════════
-- Fecha: 2026-10-05
--
-- Firmas = bloques de HTML que se pegan al final de lo que el usuario envía.
-- Un usuario puede tener varias ("Formal", "Comercial", "Cliente X") y cada una
-- se asigna a las cuentas que él elija. El worker de envío (Fase 5) toma la
-- predeterminada de la cuenta.
--
-- Por qué el HTML va COMPLETO y no "solo texto con colores"
-- -------------------------------------------------------
-- Porque "muy completo" (el requisito) significa: tablas para alinear el logo
-- con los datos, tipografías, colores de marca, un separador, un enlace a la
-- web. Eso es HTML. Guardar "texto con formato" obligaría a inventar un
-- lenguaje de formato propio peor que HTML.
--
-- Por qué NO base64 dentro del HTML
-- --------------------------------
-- Un logo de 300 KB inlineado (base64) pesa 400 KB y va en el cuerpo de CADA
-- correo. Cuando alguien responde, se cita y se re-cita: los hilos se multiplican
-- de tamaño y el preview del cliente se rompe. Además muchos clientes bloquean
-- imágenes inline grandes. Las imágenes van por Content-ID (cid:) y el worker
-- las adjunta al enviar. Ver AGENTS.md §Firmas.
--
-- El HTML se sanitiza en el SERVIDOR al guardar (api/main.py::_sanitizar_html).
-- Nunca en el cliente: un sanitizado en el navegador se salta por consola.
-- ═══════════════════════════════════════════════════════════════════════════

GO

-- ── Firmas ───────────────────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxFirmas')
BEGIN
    CREATE TABLE dbo.HUB_MailboxFirmas (
        Id              INT IDENTITY(1,1) PRIMARY KEY,
        IdUsuario       INT           NOT NULL,

        -- "Formal", "Comercial"… Para el usuario, no para el sistema.
        Nombre          NVARCHAR(60)   NOT NULL,

        -- El HTML sanitizado. NVARCHAR(MAX) y no VARCHAR: trae ñ, acentos y
        -- caracteres de las tablas de alineación que pega el usuario.
        Html            NVARCHAR(MAX)  NOT NULL,

        -- Una sola predeterminada por usuario. El worker la busca al construir
        -- un envío si la cuenta no tiene otra asignada.
        Predeterminada   BIT           NOT NULL DEFAULT 0,

        -- El texto plano se guarda aparte y es lo que se usa como fallback:
        -- un cliente de correo que no pinta HTML (o un celular con images
        -- apagadas) recibe esto en vez de una tabla invisible.
        TextoPlano      NVARCHAR(MAX)  NULL,

        Creado          DATETIME       NOT NULL DEFAULT GETDATE(),
        Actualizado     DATETIME       NOT NULL DEFAULT GETDATE(),

        CONSTRAINT FK_MailboxFirmas_Usuario
            FOREIGN KEY (IdUsuario) REFERENCES dbo.HUB_Users(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxFirmas creada';
END
ELSE
    PRINT 'HUB_MailboxFirmas ya existe';
GO

-- La vista de firmas siempre filtra por usuario y ordena por fecha.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxFirmas_Usuario'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxFirmas'))
BEGIN
    CREATE INDEX IX_HUB_MailboxFirmas_Usuario
        ON dbo.HUB_MailboxFirmas (IdUsuario, Creado DESC);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_HUB_MailboxFirmas_Nombre'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxFirmas'))
BEGIN
    -- Dos firmas con el mismo nombre solo confunden al usuario. 60 caracteres
    -- NVARCHAR = 120 bytes, muy por debajo del tope de 900.
    CREATE UNIQUE INDEX UX_HUB_MailboxFirmas_Nombre
        ON dbo.HUB_MailboxFirmas (IdUsuario, Nombre);
END
GO

-- ── Imágenes de la firma ─────────────────────────────────────────────────────
-- Las imágenes NO van en la base (ver cabecera): van al share SMB del FileServer
-- y acá solo queda el manifiesto. El Token es un valor aleatorio porque la
-- etiqueta <img> de una firma puede apuntar a una URL pública (para que la firma
-- también se vea en Gmail web) y eso no puede ser adivinable.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxFirmaImagenes')
BEGIN
    CREATE TABLE dbo.HUB_MailboxFirmaImagenes (
        Id              INT IDENTITY(1,1) PRIMARY KEY,
        IdFirma         INT            NOT NULL,

        Nombre          NVARCHAR(160)   NOT NULL,   -- nombre original del archivo
        ContentType     NVARCHAR(100)   NOT NULL,   -- image/png, image/jpeg…
        Bytes           INT             NOT NULL,   -- tamaño en bytes
        -- 65 bytes (32 bytes crudos en base64) para ponerlo en el atributo cid.
        Cid             NVARCHAR(80)    NULL,

        -- Token público para servir la imagen por URL. CHAR(40) = 40 bytes: entra
        -- en un índice único sin acercarse al tope de 900.
        Token           CHAR(40)        NULL,

        -- Dónde quedó guardada: RELATIVA a /data/mailbox/firmas, nunca
        -- absoluta (una ruta absoluta se rompe si el volumen se mueve).
        --
        -- OJO, el nombre de la columna dice SMB pero NO va al FileServer: se
        -- cambió a propósito. Una firma tiene ~5 imágenes de 30-80 KB, o sea
        -- ~1.6 MB para toda la empresa; eso no justifica un share de red, ni
        -- meter pysmb en la app, ni un salto por cada firma que se muestra.
        -- Y como los adjuntos ya no se guardan, el FileServer se quedó sin
        -- trabajo en Mailbox. El nombre se conserva para no rehacer la
        -- migración; la semántica real es "clave de almacenamiento".
        Clave           NVARCHAR(400)   NULL,

        Alto            INT             NULL,
        Ancho           INT             NULL,

        Creado          DATETIME        NOT NULL DEFAULT GETDATE(),

        CONSTRAINT FK_MailboxFirmaImg_Firma
            FOREIGN KEY (IdFirma) REFERENCES dbo.HUB_MailboxFirmas(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxFirmaImagenes creada';
END
ELSE
    PRINT 'HUB_MailboxFirmaImagenes ya existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxFirmaImg_Firma'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxFirmaImagenes'))
BEGIN
    CREATE INDEX IX_HUB_MailboxFirmaImg_Firma
        ON dbo.HUB_MailboxFirmaImagenes (IdFirma);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_HUB_MailboxFirmaImg_Token'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxFirmaImagenes'))
BEGIN
    CREATE UNIQUE INDEX UX_HUB_MailboxFirmaImg_Token
        ON dbo.HUB_MailboxFirmaImagenes (Token)
        WHERE Token IS NOT NULL;   -- filtrado: varias filas con Token NULL son válidas
END
GO

-- ── Asignación firma ↔ cuentas ───────────────────────────────────────────────
-- El requisito explícito: la firma "se aplicará a las cuentas de correo de cada
-- usuario seleccionadas". Esta tabla ES esa selección.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxFirmaCuentas')
BEGIN
    CREATE TABLE dbo.HUB_MailboxFirmaCuentas (
        IdFirma         INT           NOT NULL,
        IdCuenta        INT           NOT NULL,
        -- Snapshot del HTML aplicado en el momento de asignar. Si mañana el
        -- usuario edita la firma, un correo ya enviado conserva lo que se usó
        -- en su día. Ver AGENTS.md §Firmas.
        HtmlAlEnviar    NVARCHAR(MAX)  NULL,
        Creado          DATETIME      NOT NULL DEFAULT GETDATE(),

        CONSTRAINT PK_MailboxFirmaCuentas PRIMARY KEY (IdFirma, IdCuenta),
        CONSTRAINT FK_MailboxFirmaCuentas_Firma
            FOREIGN KEY (IdFirma) REFERENCES dbo.HUB_MailboxFirmas(Id) ON DELETE CASCADE,
        CONSTRAINT FK_MailboxFirmaCuentas_Cuenta
            FOREIGN KEY (IdCuenta) REFERENCES dbo.HUB_MailboxCuentas(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_MailboxFirmaCuentas creada';
END
ELSE
    PRINT 'HUB_MailboxFirmaCuentas ya existe';
GO

-- El worker resuelve "qué firma usa esta cuenta" en cada envío.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_HUB_MailboxFirmaCuentas_Cuenta'
               AND object_id = OBJECT_ID('dbo.HUB_MailboxFirmaCuentas'))
BEGIN
    CREATE INDEX IX_HUB_MailboxFirmaCuentas_Cuenta
        ON dbo.HUB_MailboxFirmaCuentas (IdCuenta);
END
GO

PRINT '0049_mailbox_firmas.sql aplicada'
GO