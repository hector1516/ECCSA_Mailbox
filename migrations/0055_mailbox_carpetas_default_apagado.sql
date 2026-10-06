/* ═══════════════════════════════════════════════════════════════════════════
   0055 — Corregir el default de sincronización
   ───────────────────────────────────────────────────────────────────────────
   Qué salió mal
   --------------
   La 0054 dejó `Sincronizar = 1` por default, y el primer listado de carpetas
   activó 75 carpetas en la cuenta de Héctor y 25 en la de robot. La de robot
   tiene "INBOX/IT" con 3 800 mensajes, "INBOX/Onedrive" con 4 203 e
   "INBOX/ECC-SA" con 1 850.

   Por qué eso no termina nunca: la sincronización solo mira 90 días y trae un
   lote de 200 por carpeta por ciclo. Una carpeta con 3 800 correos no se acaba en
   un ciclo, y como el trabajo se reparte con un presupuesto para no tapar al
   worker, el ciclo siguiente empieza de nuevo por el principio de esa carpeta. La
   carpeta grande se reprocesa eternamente sin avanzar y consume el presupuesto
   que necesitaban las demás.

   Además, sincronizar 646 carpetas de la cuenta 4 llenaría la base de mensajes
   que nadie pidió ver. El presupuesto por ciclo existe para que el worker no se
   atrase, no para vaciar un buzón entero a la fuerza.

   La corrección
   -------------
   Todas las carpetas discovered quedan APAGADAS. Aparecen como pestañas con
   cuántos correos tienen (eso viene del `STATUS`, que es gratis) y el usuario
   enciende las que usa desde el botón ⚙️ de la cuenta.
   ═══════════════════════════════════════════════════════════════════════════ */

UPDATE dbo.HUB_MailboxCarpetas SET Sincronizar = 0;
GO

/* La raíz se queda encendida: es la carpeta del día y la única que el sistema
   asume que existe. `CarpetaRaiz` sale del panel por cuenta (para Gmail es
   INBOX; para un Exchange sería la carpeta del buzón). */
UPDATE c
SET Sincronizar = 1
FROM dbo.HUB_MailboxCarpetas c
INNER JOIN dbo.HUB_MailboxCuentas a ON a.Id = c.IdCuenta
WHERE c.Nombre = ISNULL(NULLIF(a.CarpetaRaiz, ''), 'INBOX');
GO
