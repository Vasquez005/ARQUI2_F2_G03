# Analisis final de pendientes - PORTUS Fase 2

Fecha: 2026-09-24  
Repositorio oficial: `ARQUI2_F2_G03`  
Objetivo: dejar claro que falta para cerrar la entrega de forma completa y defendible.

---

## 1) Estado general actual

El proyecto ya tiene base funcional integrada:

- Firmware en 3 controladores (UNO entrada, UNO salida, Mega grua).
- Bridge serial <-> MQTT funcionando.
- Backend con reglas de negocio y API extensa.
- Web con login por rol y vistas operativas.
- Bot con vinculacion y envio de notificaciones pendientes.

Sin embargo, todavia hay pendientes importantes para afirmar "100% completo" contra enunciado.

---

## 2) Pendiente critico (prioridad maxima)

## 2.1 Falta cerrar el ciclo fisico automatico en backend

Hoy el backend guarda eventos del bridge (`portus/evt/#`), pero no convierte de forma completa esos eventos en avance automatico de turno de punta a punta.

Impacto:

- Turnos pueden requerir llamadas manuales a endpoints para avanzar.
- La demostracion puede verse "semi-automatica".

Accion requerida:

- Implementar un orquestador de eventos en backend que procese eventos de:
  - garita,
  - pesaje,
  - transferencia/grua,
  - salida,
  y ejecute las transiciones de turno correspondientes.

---

## 2.2 Asociacion vehiculo/RFID <-> contenedor/manifiesto

Actualmente este enlace no esta cerrado de forma robusta para todos los casos reales.

Impacto:

- Sin esta relacion, no se puede automatizar completamente ingreso por garita.

Accion requerida:

- Definir y persistir mapeo de identidad de vehiculo/RFID con carga esperada
  (contenedor/manifiesto/cita).

---

## 3) Firmware y control fisico pendientes

## 3.1 AL02 (paro de emergencia)

Pendiente confirmado: no esta implementado porque falta confirmar senal/pin legible en microcontrolador.

Impacto:

- No se puede generar la alarma AL02 obligatoria si el paro no se detecta por software.

Accion requerida:

- Confirmar si existe senal de lectura del paro.
- Si existe: leerla y emitir evento/alarma AL02.

---

## 3.2 Buffer local de eventos en desconexion

Modo degradado existe, pero no hay buffer local de eventos para reconciliar despues de reconexion.

Impacto:

- Riesgo de perder trazabilidad fina durante caida de enlace.

Accion requerida:

- Implementar buffer circular local (RAM/EEPROM, segun viabilidad) y reenvio/reconciliacion.

---

## 3.3 Comandos de aguja en Mega

Estado actual: `AgujaRecta`, `AgujaParqueo`, `AgujaLiberar` responden `REJ causa=pesaje_externo` en la variante actual.

Impacto:

- Si el flujo final exige que Mega gobierne aguja en operacion integrada, esto queda incompleto.

Decision requerida:

- Mantener arquitectura "pesaje/aguja externo" (y documentarlo), o
- Reintegrar control de aguja en Mega con reglas de seguridad.

---

## 3.4 Calibracion fisica final

Pendientes de banco:

- Ajuste fino de angulos/tiempos de actuadores.
- Verificacion de sensores en condiciones reales de maqueta.

Impacto:

- Sin calibracion, pueden aparecer fallos intermitentes en demo.

---

## 4) Web (C) - estado y faltantes

Ya se avanzo en vistas funcionales para:

- Terminal
- Naviera
- Agente
- Autoridad

Faltantes para "calidad final de entrega":

- Endurecer validaciones de formularios y mensajes de error por caso.
- Mejorar UX (filtros, confirmaciones, acciones por fila, feedback claro).
- Consolidar reportes de acuerdo con metricas exigidas por enunciado (no solo resumen operativo).
- Validar coherencia completa de permisos por rol en todos los flujos UI.

---

## 5) Bot (D) - faltante principal

La base esta funcional, pero falta validacion completa de escenarios reales de notificacion:

- levante otorgado/retenido,
- retencion creada/resuelta,
- cierre/anulacion de turno,
- reconexion con cola de pendientes.

---

## 6) Pruebas faltantes para cierre formal

## 6.1 Matriz de escenarios de evaluacion

Ejecutar y evidenciar escenarios del enunciado (happy paths + excepciones).

## 6.2 Evidencia minima de entrega

Guardar evidencia de:

- estado de servicios (`status_all.sh`),
- pruebas por rol web,
- deposito y retiro completos,
- retenciones RT01-RT06 (segun aplique),
- alarmas criticas relevantes (AL01 y, si se implementa, AL02),
- comportamiento en degradado/reconexion.

---

## 7) Riesgos actuales si se entrega hoy

- Riesgo de observacion por automatizacion incompleta evento->turno.
- Riesgo por AL02 no implementada (si la piden estricta).
- Riesgo por falta de reconciliacion de eventos offline.
- Riesgo de inconsistencias menores de UX/reporteria en web.

---

## 8) Plan corto recomendado (orden de cierre)

1. Cerrar orquestacion backend de eventos fisicos a turnos.  
2. Cerrar mapeo RFID/vehiculo a contenedor/manifiesto/cita.  
3. Definir e implementar AL02 (si hay senal).  
4. Implementar buffer/reconciliacion offline minimo viable.  
5. Pulir validaciones/reportes web y correr bateria de pruebas final.  
6. Generar paquete de evidencias para defensa/demo.

---

## 9) Conclusion ejecutiva

El proyecto esta funcional y bien encaminado, pero para afirmar cumplimiento total todavia faltan piezas de automatizacion integral, seguridad operacional (AL02) y robustez de reconexion.  
Si se cierran los puntos de seccion 8, la entrega queda mucho mas solida tecnica y academicamente.

