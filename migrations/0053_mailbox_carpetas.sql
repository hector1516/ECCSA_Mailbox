/* ═══════════════════════════════════════════════════════════════════════════
   0053 — Carpetas conocidas por cuenta
   ───────────────────────────────────────────────────────────────────────────
   Por qué
   -----
   Las pestañas de la app se armaban con `GROUP BY Carpeta` sobre los MENSAJES.
   Eso funciona para Entrada y Enviados y se rompe en cuanto existe una carpeta
   vacía: una carpeta recién creada no tiene mensajes, así que no aparece en el
   `GROUP BY` y el usuario acaba de crearla sin verla.

   Peor todavía: para que una carpeta con un solo correo apareciera, el usuario
   tendría que tener que mover un correo a ciegas hacia un nombre que no puede
   ver. La carpeta que no se ve es la carpeta que no se puede usar.

   Así que las carpetas se registran como entidades propias. El conteo de
   mensajes vive en la consulta, no en la tabla: duplicarlo haría que quedara
   viejo en cuanto el worker sincronizara.
   ═══════════════════════════════════════════════════════════════════════════ */

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_MailboxCarpetas')
BEGIN
    CREATE TABLE dbo.HUB_MailboxCarpetas (
        Id          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        IdCuenta    INT           NOT NULL,
        -- `COLLATE ..._BIN2` como el resto del módulo: las carpetas conservan
        -- mayúsculas y acentos, y una comparación CI colapsaría "Facturación"
        -- con "facturación", que son carpetas distintas.
        Nombre      NVARCHAR(200) COLLATE Latin1_General_100_BIN2 NOT NULL,
        -- 1 si la carpeta viene del propio servidor (INBOX, Sent, Spam...) y no
        -- la creó un usuario. Se guardan igual para poder mostrarlas aunque
        -- estén vacías.
        DelSistema  BIT           NOT NULL DEFAULT 0,
        Creado      DATETIME2(3)  NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT UQ_MailboxCarpetas_CuentaNombre UNIQUE (IdCuenta, Nombre),
        CONSTRAINT FK_MailboxCarpetas_Cuenta
            FOREIGN KEY (IdCuenta) REFERENCES dbo.HUB_MailboxCuentas(Id) ON DELETE CASCADE
    );

    CREATE INDEX IX_MailboxCarpetas_Cuenta ON dbo.HUB_MailboxCarpetas(IdCuenta, Nombre);
END
GO

/* Las carpetas que ya están en el índice se registran ahora, para que las
   pestañas aparezcan populated desde el primer arranque y no haya que esperar
   a que el worker vuelva a recorrer cada cuenta. */
INSERT INTO dbo.HUB_MailboxCarpetas (IdCuenta, Nombre, DelSistema, Creado)
SELECT DISTINCT m.IdCuenta, m.Carpeta,
       CASE WHEN m.Carpeta IN ('INBOX', 'Sent') THEN 1 ELSE 0 END,
       SYSDATETIME()
FROM dbo.HUB_MailboxMensajes m
WHERE m.Carpeta IS NOT NULL AND LTRIM(RTRIM(m.Carpeta)) <> ''
  AND NOT EXISTS (SELECT 1 FROM dbo.HUB_MailboxCarpetas c
                  WHERE c.IdCuenta = m.IdCuenta AND c.Nombre = m.Carpeta)
GO
