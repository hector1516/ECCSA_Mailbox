-- ─────────────────────────────────────────────────────────────────────────────
-- Migración 0058 — Afinamiento del triaje sin IA
-- Fecha: 2026-10-24
--
-- POR QUÉ
-- El triaje ya no usa IA (decisión del usuario: sin cuota que pagar). Para no
-- perder precisión se añaden dos señales deterministas:
--   1. "Primer contacto": un dominio que nunca nos ha escrito es más sospechoso.
--   2. "Lenguaje promocional": sujetos/cuerpos con vocabulario de venta en frío.
-- Además, cuando el operador RECHAZA un candidato, se cuenta el rechazo por
-- dominio y, tras N rechazos, el dominio se bloquea solo (auto-aprendizaje).
-- Y cuando APRUEBA, el dominio queda marcado como "conocido" y deja de ser
-- sospechoso en futuros correos.
--
-- También se persiste InReplyTo: hasta ahora se capturaba pero se tiraba, y es
-- la señal más barata para saber si un correo es respuesta a un hilo real o un
-- "Re:" inventado de venta en frío.
--
-- Aditiva e idempotente.
-- ─────────────────────────────────────────────────────────────────────────────

-- 1) Columna InReplyTo en HUB_MailboxMensajes
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.HUB_MailboxMensajes')
                 AND name = 'InReplyTo')
BEGIN
    ALTER TABLE dbo.HUB_MailboxMensajes ADD InReplyTo NVARCHAR(500) NULL;
END
GO

-- 2) Reputación por dominio del remitente
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxRemitentes')
BEGIN
    CREATE TABLE dbo.HUB_MailboxRemitentes (
        Dominio       NVARCHAR(255) NOT NULL PRIMARY KEY,
        PrimeraVez    DATETIME      NOT NULL CONSTRAINT DF_HMR_Primera DEFAULT GETDATE(),
        UltimaVez     DATETIME      NOT NULL CONSTRAINT DF_HMR_Ultima  DEFAULT GETDATE(),
        Veces         INT           NOT NULL CONSTRAINT DF_HMR_Veces   DEFAULT 1,
        Rechazos      INT           NOT NULL CONSTRAINT DF_HMR_Rech    DEFAULT 0,
        EsConocido    BIT           NOT NULL CONSTRAINT DF_HMR_Conoc   DEFAULT 0,
        BloqueadoAuto BIT           NOT NULL CONSTRAINT DF_HMR_Bloq    DEFAULT 0
    );
END
GO
