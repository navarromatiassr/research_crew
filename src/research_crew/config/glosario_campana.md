# Glosario de la operación de campañas (Daniel, portabilidad Movistar)

Este texto se le da al analista para que interprete los datos con el criterio del negocio.
Lo marcado como _pendiente_ todavía no fue confirmado por el equipo.

## Tablas y qué representa una fila

| Tabla | Una fila es |
| --- | --- |
| `ops_campanas` | Una versión de una campaña. Append-only: la versión vigente es la de mayor `version_ts` por `campaign_id`. `motivo` dice por qué se escribió (carga_inicial, contactos, activada, comando, plan_editado, cx_editado, observada). |
| `ops_calls` | Una llamada cerrada de la IA telefónica, con `campaign_id`, duración, costo, motivo de fin y si hubo handoff a WhatsApp. |
| `ops_measurements` | Una métrica medida en una ventana de 15 minutos por campaña y dominio (`agent`), con umbral, desvío `z` y estado. |
| `gtr_events` | Una decisión del gobernador determinista: incidente, palanca propuesta o aplicada, severidad. |
| `alertas_recupero` | Una alerta generada por el agente de CX sobre una conversación de WhatsApp recuperable. |
| `alertas_resueltas` | La resolución humana de una alerta: quién, resultado, si servía. |

## Campaña

- `status`: draft, scheduled, active, finished, stopped.
- `dialing_state`: dialing (discando), off_window (fuera de franja), held_gtr (frenada por el gobernador), held_human (frenada por una persona), idle.
- `fuego_min` / `fuego_max`: canales simultáneos mínimos y máximos. `fuego_max` es el techo duro. `fuego_objetivo` es el valor vigente.
- `objetivo_voz_viva_dia`: llamadas con voz viva por día que se buscan. `objetivo_handoff`: handoffs buscados.
- `budget_dia_usd`: presupuesto diario.
- `franjas`: días y horarios habilitados para discar.
- `contactos_total`: contactos cargados.

## Llamadas

- `handoff = true`: la IA derivó al cliente a WhatsApp porque mostró interés real. Es el lead.
- `ended_reason`: motivo de fin de la llamada según Vapi (por ejemplo cliente cortó, asistente terminó, no contestó, contestador).
- `duration_seg`: duración. Llamadas de más de 40 segundos se consideran conversación real (_pendiente_ confirmar umbral).
- `cost_total`: costo de la llamada en USD.
- Tasa de handoff = handoffs / llamadas. Contactabilidad = llamadas con voz viva / llamadas (_pendiente_: cómo se identifica voz viva en `ended_reason`).

## Alertas de recupero

- `severidad`: hot, mid, warm, de más a menos urgente.
- `tramo`: 24, 48 o 72. _pendiente_: confirmar si son horas desde el último contacto.
- `lado`: cliente o nosotros. _pendiente_: confirmar que "nosotros" significa que la próxima acción es del closer.
- `vendible` e `interes`: puntajes de 1 a 9.
- `ventana_abierta`: la ventana de 24 h de WhatsApp sigue abierta.
- `closer`: vendedor asignado.
- `publicar = false` con `razon_descarte`: la alerta se descartó. `revisar_a_mano = true`: requiere revisión humana.
- Una alerta se considera resuelta si tiene fila en `alertas_resueltas`.

## Reglas para el analista

- Para el estado actual de una campaña usar siempre la última versión por `campaign_id`.
- Filtrar `ops_calls` y `ops_measurements` por fecha (columnas de partición `ended_at` y `ts`) para no procesar toda la historia.
- Los teléfonos, transcripciones, grabaciones y mensajes están ocultos: se pueden contar y agrupar, no leer.
- Cuando una definición esté _pendiente_, declararla como supuesto en la respuesta.
