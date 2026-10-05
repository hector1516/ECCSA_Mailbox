/* ═══════════════════════════════════════════════════════════════════════════
   0052 — Operaciones de cuenta (crear carpeta)
   ───────────────────────────────────────────────────────────────────────────
   Por qué
   -----
   `HUB_MailboxColaOperaciones` llevaba `IdMensaje NOT NULL` porque todas las
   operaciones que se inventaron eran "qué le hago A ESTE MENSAJE": marcar leído,
   destacar, borrar, mover.

   Crear una carpeta no tiene mensaje. Es una operación de la CUENTA. Se hizo
   nullable en vez de crear una tabla nueva porque la cola ya tiene justo lo que
   hace falta: el vínculo con la cuenta, el usuario que la pidió, el estado, los
   reintentos y el error. Una tabla aparte habría sido la misma tabla con otro
   nombre.

   El `CHECK` evita el peor modo de falla: una fila de operación de cuenta con
   mensaje puesto, o una de mensaje sin mensaje. Sin él, un bug del worker que
   lea `Id` de un NULL revienta con un error de NULL en vez de con un error que
   dice qué pasó.

   OJO con el orden de despliegue
   ------------------------------
   La migración va PRIMERO. Si la app empieza a encolar `crear_carpeta` antes de
   que `IdMensaje` sea nullable, el INSERT revienta y el usuario no puede crear
   carpetas. Al revés (worker antes que app) no pasa nada: el worker simplemente
   ve una operación que la app todavía no genera.
   ═══════════════════════════════════════════════════════════════════════════ */

-- IdMensaje nullable: las operaciones de cuenta no tienen mensaje.
-- La nulabilidad se lee de `sys.columns.is_nullable` y NO de `COLPROPERTY`.
-- `COLPROPERTY` es de Analysis Services (SSAS), no del motor relacional: en la
-- 2014 Express que corre ECCSA sale "'COLPROPERTY' is not a recognized
-- built-in function name" y la migración aborta. Es el mismo error que ya se
-- llevó una primera pasada por acá.
IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.HUB_MailboxColaOperaciones')
             AND name = 'IdMensaje' AND is_nullable = 0)
BEGIN
    ALTER TABLE dbo.HUB_MailboxColaOperaciones ALTER COLUMN IdMensaje BIGINT NULL;
END
GO

-- La FK se recrea porque en SQL Server hay que soltarla antes de widening.
IF EXISTS (SELECT 1 FROM sys.foreign_keys
           WHERE name = 'FK_MailboxColaOperaciones_Mensaje')
BEGIN
    ALTER TABLE dbo.HUB_MailboxColaOperaciones
        DROP CONSTRAINT FK_MailboxColaOperaciones_Mensaje;
    ALTER TABLE dbo.HUB_MailboxColaOperaciones
        ADD CONSTRAINT FK_MailboxColaOperaciones_Mensaje
        FOREIGN KEY (IdMensaje) REFERENCES dbo.HUB_MailboxMensajes(Id);
END
GO

-- CHECK: mensaje XOR operación de cuenta. Sin esto, un IdMensaje en NULL con un
-- Operacion de mensaje colaría y el worker no sabría a qué carpeta hacer SELECT.
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = 'CK_MailboxColaOperaciones_MensajeXOCuenta')
BEGIN
    ALTER TABLE dbo.HUB_MailboxColaOperaciones WITH CHECK
        ADD CONSTRAINT CK_MailboxColaOperaciones_MensajeXOCuenta
        CHECK (
            (IdMensaje IS NOT NULL AND Operacion IN ('seen', 'flag', 'delete', 'move'))
         OR (IdMensaje IS NULL     AND Operacion = 'crear_carpeta')
        );
END
GO
