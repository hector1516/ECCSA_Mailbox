-- ─────────────────────────────────────────────────────────────────────────────
-- Migración 0057 — Bloqueos globales de correo
-- Fecha: 2026-10-24
--
-- POR QUÉ
-- Las reglas de `HUB_MailboxReglas` son POR USUARIO y solo se aplican a las
-- cuentas que ese usuario tiene asignadas. Eso está bien para "archivar los
-- correos de tal cliente", pero no para un bloqueo: si alguien marca un
-- remitente como spam, tiene que dejar de llegar en LAS 13 cuentas, no solo en
-- la suya.
--
-- Esta tabla es global: el worker la evalúa para todos los buzones, antes de
-- las reglas personales. Es una lista negra de remitente o de dominio, con
-- origen para saber de dónde salió cada entrada.
--
-- Aditiva e idempotente.
-- ─────────────────────────────────────────────────────────────────────────────

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxBloqueos')
BEGIN
    CREATE TABLE dbo.HUB_MailboxBloqueos (
        Id          INT IDENTITY(1,1) PRIMARY KEY,
        -- email | dominio
        Tipo        VARCHAR(8)    NOT NULL,
        Valor       NVARCHAR(320) NOT NULL,
        Motivo      NVARCHAR(200) NULL,
        -- manual (botón del panel) | auto (regla) | importada (lista pegada)
        Origen      VARCHAR(12)   NOT NULL CONSTRAINT DF_HMB_Origen DEFAULT 'manual',
        Activo      BIT           NOT NULL CONSTRAINT DF_HMB_Activo DEFAULT 1,
        Creado      DATETIME      NOT NULL CONSTRAINT DF_HMB_Creado DEFAULT GETDATE(),
        CreadoPor   NVARCHAR(200) NULL
    );

    -- Un mismo valor no puede estar dos veces: el panel importa listas enteras
    -- y un duplicado no debe dar error ni crear filas gemelas.
    CREATE UNIQUE INDEX UX_MailboxBloqueos ON dbo.HUB_MailboxBloqueos (Tipo, Valor);
END
GO
