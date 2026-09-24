# Observaciones de revisión — Bot del transportista (Persona D)

**Fecha de revisión:** 2026-09-24
**Archivos revisados/modificados:**
- `bot_d/app/main.py` (reescrito sobre la base de B)
- `backend/models.py` (tabla nueva `notificaciones`), `backend/servicios.py`, `backend/app.py` (avisos reales)

**Contra qué se comparó:** tareas de Persona D en `docs originales/PORTUS_Fase2_Plan.md` (sección 3) y `docs originales/Fase_2_PORTUS.md` (secciones 6 y 9).

**Verificación realizada:** el bot se corrió en modo CLI (sin token) contra una base temporal compartida con el backend de B, con 2 transportistas vinculados a chats distintos. Se probó vinculación, los 7 comandos, texto libre, aislamiento entre transportistas y los avisos de levante, retención (RT01, RT03, RT04), resolución (Corregir, Aclarar, Rechazar), cierre, anulación y recordatorio. El modo Telegram se probó solo hasta construir la aplicación (sin token real no se puede conectar).

---

## Checklist contra las tareas de Persona D

| # | Tarea (según el plan / enunciado) | Estado |
|---|---|---|
| 1 | Bot conectado a la base de datos de B | ✅ **Integrado** — antes usaba su propia base con datos inventados |
| 2 | Vinculación con código de 6 caracteres, un uso, expira a los 60 min | ✅ Cumplido (código generado por la terminal en la web) |
| 3 | Los 7 comandos | ✅ Cumplido, con los contenidos de la tabla 6.2 |
| 4 | Citas: franjas de 15 min, máximo 2, solo con levante, sin duplicar | ✅ Cumplido, en la tabla `citas` de B (la que usa la garita para RT04) |
| 5 | Ventana: inicio de la franja hasta 5 min después del fin, si no RT04 | ✅ Lo decide B en la garita; ahora también marca la cita cumplida/vencida |
| 6 | Avisos automáticos (tabla 6.3) | ⚠️ 8 de 9. Falta "cita cancelada o reprogramada" (no existe esa función en la terminal) |
| 7 | Aislamiento entre transportistas | ✅ Verificado con 2 transportistas |
| 8 | Nunca quedar sin responder | ✅ **Corregido** — antes el texto libre no recibía respuesta |

---

## 1. Lo que se encontró y se corrigió

1. **Base propia con datos falsos.** El bot tenía sus propias tablas `contenedores`, `turnos` y `citas` con `CONT-001..003` sembrados. Nada de eso lo veía B, así que una cita pedida por el bot nunca llegaba a la garita. Ahora usa `backend/models.py` y `backend/portus_core.db` directamente (misma Pi, SQLite en modo WAL).
2. **El texto libre no recibía respuesta.** Solo había `CommandHandler` para los 7 comandos; un "hola" o un `/foo` quedaban sin contestar, y la regla 6.2 dice que el servicio nunca puede quedar callado. Ahora un solo `MessageHandler(filters.TEXT)` atiende todo.
3. **`/cita` no dejaba elegir franja.** Asignaba automáticamente la primera. El enunciado pide ofrecer las próximas franjas y que el transportista elija. Ahora: `/cita` → lista de contenedores, `/cita C1` → 4 franjas numeradas, `/cita C1 2` → confirma.
4. **Horas en UTC.** Las citas se mostraban como `2026-09-24 21:00:00 UTC`. Ahora se muestran en hora de Guatemala (la base sigue guardando UTC).
5. **`/inicio` no cumplía 6.2.** No tenía el nombre de la terminal ni una descripción por comando. Corregido.
6. **Usuario no vinculado.** Recibía respuestas distintas según el comando. La regla 6.1.5 pide siempre la misma respuesta; ahora es un único mensaje fijo (salvo para `/vincular`).
7. **Fuga posible entre transportistas.** Si un mismo chat se vinculaba primero a un transportista y luego a otro, quedaba asociado a los dos. Ahora se desvincula del anterior.
8. **`/misturnos` mostraba todos los turnos**, incluso cerrados. Ahora solo los activos.
9. **Las notificaciones no existían** (salvo el recordatorio). B solo escribía "[pendiente bot D]" en la línea de tiempo.

## 2. Cómo funcionan ahora los avisos

B escribe el aviso ya redactado en la tabla `notificaciones` (con el `transportista_id` dueño de la carga) y el bot, cada 3 segundos, envía los pendientes a su chat y marca `sent_at`. Si el bot está apagado o el transportista todavía no se vincula, el aviso espera en la cola y sale después.

| Aviso (tabla 6.3) | Quién lo genera | Estado |
|---|---|---|
| Levante otorgado (con canal; si es rojo, aviso de verificación) | B, `POST /manifiestos/{id}/levante` | ✅ |
| Levante retenido con motivo | B, mismo endpoint | ✅ |
| Cita asignada | Bot, en la respuesta de confirmación | ✅ |
| Recordatorio 1 hora antes | Bot | ✅ Solo si la cita se pidió con más de 1 h de anticipación, y una sola vez |
| Vehículo retenido (con pesos si es RT01/RT02) | B, `crear_retencion` | ✅ |
| Retención resuelta (peso nuevo si Corregir, motivo si Rechazar) | B, `resolver_retencion` | ✅ |
| Cita cancelada o reprogramada | — | ❌ No existe todavía la pestaña Citas de la terminal |
| Turno cerrado (con tiempo total) | B, `cerrar_turno` | ✅ |
| Turno anulado (con causa) | B, `anular_turno` (endpoint nuevo) | ✅ |

## 3. Pendiente para D

- **Cancelar / reprogramar / bloquear franja (sec. 4.7).** Lo hace la terminal desde la web, pero la lógica de franjas es de D. Falta: una columna o tabla de franjas bloqueadas que `proximas_franjas()` respete, y los endpoints en B (con su aviso al transportista).
- **Permanencia en `/estado`.** Se calcula desde el cierre del turno de depósito, porque el patio no guarda la fecha de ingreso de cada contenedor. Si B agrega esa fecha, conviene usarla.
- **Probar con Telegram real** desde un teléfono (lo pide la evaluación): `PORTUS_BOT_TOKEN=... python3 app/main.py` desde `bot_d/`.

## 4. Cómo probarlo sin Telegram

```bash
cd bot_d
python3 app/main.py          # sin PORTUS_BOT_TOKEN entra en modo CLI
> transportistas             # ids y si estan vinculados
> gen-code 1                 # lo mismo que el boton de la terminal
> chat 111 /vincular ABC123
> chat 111 /cita
> notifs                     # envia (imprime) los avisos pendientes
```

`bot_d/portus_persona_d.db` ya no se usa y se puede borrar.
