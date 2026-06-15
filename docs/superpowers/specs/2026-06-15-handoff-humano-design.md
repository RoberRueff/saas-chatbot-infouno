# Diseño — Handoff a humano (modo humano por pedido del cliente)

**Fecha:** 2026-06-15
**Estado:** Aprobado
**Rama:** feat/clasificacion-departamentos-email

## Problema

El campo `Conversacion.estado_humano` existe y se filtra en
`obtener_o_crear_conversacion`, pero **ningún código lo setea a `True`**: la
feature de "pausar el bot cuando interviene un humano" está a medio implementar.
Además, el filtro actual (`estado_humano == False`) haría que un cliente en modo
humano abra una conversación nueva y el bot le vuelva a hablar — lo opuesto a
pausar.

## Objetivo

Que el cliente pueda pedir hablar con una persona; el bot lo confirma, marca la
conversación en modo humano, avisa al equipo por email y deja de responder esa
conversación. Tras 24 h de inactividad (ventana del #1), una conversación nueva
reactiva el bot.

## Decisiones (acordadas)

- **Trigger:** lo pide el cliente.
- **Detección:** la decide el modelo, con un campo nuevo `solicita_humano`.
- **Mientras pausado:** silencio total (no se llama a Gemini); los mensajes del
  cliente igual se persisten para que el asesor tenga el historial.
- **Reactivación:** vía la ventana de 24 h del #1 (sin mecanismo extra).
- **Aviso al equipo:** email de escalamiento (background, un único envío).

## Componentes

### 1. Detección (modelo) — `main.py`

- Agregar a `RespuestaChatbot`:
  ```python
  solicita_humano: bool = Field(
      default=False,
      description="True si el cliente pide explícitamente hablar con una persona / un asesor / un humano.",
  )
  ```
- Agregar una regla al `SYSTEM_PROMPT`: poner `solicita_humano=True` solo cuando
  el cliente pide explícitamente atención humana.

### 2. Búsqueda de conversación — `database.py`

- `obtener_o_crear_conversacion`: **quitar** el filtro `estado_humano == False`.
  Devuelve la última conversación reciente sea cual sea su estado; la lógica de
  callarse pasa a `_procesar_mensaje`. La expiración de 24 h sigue igual: una
  conversación humana con última actividad ≥24 h hace que se cree una nueva
  (con `estado_humano=False`) → reactivación del bot.
- Nueva función atómica:
  ```python
  def marcar_estado_humano(db, conversacion_id) -> bool:
      """UPDATE ... WHERE id=? AND estado_humano=False SET estado_humano=True.
      Devuelve True solo para el primero que la marca (gana la carrera) → un único email."""
  ```
  Mismo patrón que `reclamar_derivacion`.

### 3. Flujo — `_procesar_mensaje` en `main.py`

Orden:
1. Guardrails de entrada (igual que hoy).
2. Buscar/crear conversación.
3. **Si `conversacion.estado_humano`:** `guardar_mensaje(user)`, **no** llamar a
   Gemini, devolver silencio (respuesta `None`).
4. Si no: `_llamar_gemini` → `sanitizar_salida`.
   - **Si `resultado.solicita_humano`:**
     - `gano = marcar_estado_humano(db, conversacion.id)`.
     - `resultado.respuesta_al_cliente = MSG_ESCALAMIENTO_HUMANO`.
     - guardar mensajes (user + assistant con el texto fijo).
     - si `gano` y hay `background_tasks`: agendar el email de escalamiento.
     - **saltear** el bloque de derivación de ese turno.
     - return `(conversacion.id, resultado)`.
   - Si no: persistir + bloque de derivación (igual que hoy).

### 4. "Silencio" — firma y endpoints

- `_procesar_mensaje` devuelve `tuple[Optional[int], Optional[RespuestaChatbot]]`;
  `None` en la respuesta = callarse.
- `RespuestaChat.datos` pasa a `Optional[RespuestaChatbot] = None`; `respuesta`
  default `""`.
- `/whatsapp`: si la respuesta es `None`, devolver `<Response></Response>` (sin
  `<Message>`), así Twilio no envía nada.
- `/chat`: si es `None`, devolver `RespuestaChat(conversacion_id=id,
  respuesta="", datos=None)`.

### 5. Email de escalamiento — `notificaciones/email.py`

- `enviar_aviso_escalamiento(resultado, telefono, *, config=None, sender=enviar_smtp) -> bool`,
  reusando `construir_cuerpo` y el sender. Asunto:
  `[infouno] PIDE HUMANO: <empresa o teléfono>`.
- Ruteo: `config.destino_para(categoria)`; si no hay (categoría Desconocido o sin
  destino), **fallback a Ventas** (`Comercial/Ventas`) y, si tampoco, al primer
  destino configurado. Si no hay ninguno, no envía (log).
- Background, vía una función análoga a `_derivar_en_background` (p. ej.
  `_escalar_en_background(conversacion_id, resultado, telefono)`); como el
  `marcar_estado_humano` ya garantizó un único disparo, el bg solo envía y
  loguea. **Best-effort:** si el envío falla, se loguea y **no** se revierte el
  modo humano (la conversación sigue en manos humanas; solo se pierde el aviso).

### 6. Mensaje al cliente — `main.py`

```python
MSG_ESCALAMIENTO_HUMANO = (
    "Dale, le aviso a un asesor para que te contacte. En breve te responde una persona."
)
```
Voseo, sin emoji, consistente con los mensajes de `ia/config.py`.

## Tests

- `RespuestaChatbot` parsea `solicita_humano` (default False; True cuando viene).
- `marcar_estado_humano` atómico/idempotente (segundo llamado devuelve False).
- `_procesar_mensaje` (con `_llamar_gemini` mockeado):
  - `solicita_humano=True` en conversación nueva → `estado_humano` queda True,
    respuesta == `MSG_ESCALAMIENTO_HUMANO`, email de escalamiento agendado, sin
    derivación.
  - mensaje en conversación ya en modo humano → respuesta `None` (silencio), no
    se llama a Gemini, el mensaje del cliente queda persistido.
- `enviar_aviso_escalamiento`: ruteo por categoría y fallback a Ventas cuando la
  categoría no tiene destino.
- `/whatsapp` en modo humano → TwiML `<Response></Response>` (sin `<Message>`).

Runner stdlib del repo (también colectable por pytest); Gemini se reemplaza por
un doble (monkeypatch de `main._llamar_gemini` / `main.gemini_client`).

## Edge documentado

Si un mensaje en modo humano cae en un guardrail de entrada (p. ej. parece
injection), el bot igual devuelve su respuesta fija de bloqueo, porque los
guardrails corren antes de mirar `estado_humano`. Es raro y se acepta por
simplicidad.

## Fuera de alcance

- Endpoint de admin para pausar/reanudar manualmente (elegimos solo el trigger
  del cliente).
- Consola de agentes / responder por WhatsApp desde el sistema (el asesor
  contacta al cliente por fuera, con los datos del email).
- Reactivación "pegajosa" o marca de "resuelto" (no hay consola para setearla).
