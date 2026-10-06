/* ═══════════════════════════════════════════════════════════════════════════
   0054 — Las carpetas que el worker sincroniza
   ───────────────────────────────────────────────────────────────────────────
   Por qué
   -----
   Las carpetas se crean en el CLIENTE DE CORREO del usuario (Gmail, Hostinger),
   no aquí. Antes el worker solo sincronizaba la carpeta raíz, así que cualquier
   carpeta de trabajo —"Newsletters", "Clientes", "Facturación 2026"— era
   invisible en la app: ni aparecía como pestaña ni se podía leer.

   Estas columnas hacen que el catálogo sea de dos cosas a la vez:

     · Lo que HAY en el buzón  → `TotalEnBuzon`, `NoLeidosEnBuzon`
       Salen de un IMAP `STATUS`, que NO descarga el contenido: solo pregunta
       cuántos mensajes y cuántos sin leer hay. Por eso se puede tener la
       pestaña con su contador real antes de sincronizar una sola línea de
       correo. Es lo que permite que "Newsletters" aparezca al instante con
       "37 sin leer" y no en tres días.

     · Lo que NOSOTROS sincronizamos → `Sincronizar`
       Descargar el contenido de "Todos los mensajes" de Gmail son años de
       historial: son millones de filas en nuestra base y horas de IMAP. Por eso
       la sincronización es una decisión, no un default.

   Por qué el default es el contrario para las carpetas del sistema
   ------------------------------------------------------------------
   `Sincronizar` arranca en 1 para las carpetas que crea el usuario y en 0
   para papelera, spam y borradores. Esos tres existen en todos los buzones y
   ninguno se lee desde aquí: sincronizarlos es trabajo que no le sirve a nadie
   y que además infla la base con basura que la retención tiene que barrer
   después.
   ═══════════════════════════════════════════════════════════════════════════ */

IF COL_LENGTH('dbo.HUB_MailboxCarpetas', 'Sincronizar') IS NULL
    ALTER TABLE dbo.HUB_MailboxCarpetas ADD Sincronizar BIT NOT NULL DEFAULT 1;
GO

IF COL_LENGTH('dbo.HUB_MailboxCarpetas', 'TotalEnBuzon') IS NULL
    ALTER TABLE dbo.HUB_MailboxCarpetas ADD TotalEnBuzon INT NULL;
GO

IF COL_LENGTH('dbo.HUB_MailboxCarpetas', 'NoLeidosEnBuzon') IS NULL
    ALTER TABLE dbo.HUB_MailboxCarpetas ADD NoLeidosEnBuzon INT NULL;
GO

IF COL_LENGTH('dbo.HUB_MailboxCarpetas', 'UltimaListado') IS NULL
    ALTER TABLE dbo.HUB_MailboxCarpetas ADD UltimaListado DATETIME2(3) NULL;
GO

/* Las carpetas que ya estaban (INBOX, por la migración 0053) se sincronizan:
   es lo que ya venía pasando. Las del sistema empiezan apagadas. */
UPDATE dbo.HUB_MailboxCarpetas
SET Sincronizar = CASE WHEN DelSistema = 1 AND Nombre <> 'INBOX' THEN 0 ELSE 1 END
WHERE Sincronizar IS NULL OR TotalEnBuzon IS NULL;
GO

/* El índice del ciclo: por cuenta, solo las que se sincronizan. El ciclo lo
   corre 5 de cada 6 minutos y esta consulta se ejecuta una vez por cuenta;
   sin índice es un barrido de la tabla entera en cada vuelta. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_MailboxCarpetas_Sync')
BEGIN
    CREATE INDEX IX_MailboxCarpetas_Sync
        ON dbo.HUB_MailboxCarpetas(IdCuenta, Sincronizar, Nombre);
END
GO
