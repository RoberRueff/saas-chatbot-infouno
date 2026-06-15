# Diseño — Derivación de casos, panel y traspaso a humano

**Fecha:** 2026-06-13
**Proyecto:** saas-chatbot-balanzas
**Estado:** Aprobado — pendiente de implementación

## Problema

El chatbot clasifica consultas y, cuando reúne la información mínima, marca
`notificar_recepcion = True`. Pero ese flag no dispara ninguna acción: el caso
nunca sale del bot, ningún humano lo toma y `estado_humano` está definido en el
modelo pero nunca se usa. El flujo de negocio no cierra de punta a punta.

## Objetivo

Cuando el bot tiene la info mínima para derivar, registrar el caso de forma
persistente y exponerlo en un listado consultable por un humano (ventas /
servicio técnico / calibración). Sin servicios externos.

Además, permitir que un humano **tome** un caso desde ese listado: a partir de ahí
la conversación pasa a `estado_humano` y el bot deja de responder
automáticamente, para que la persona atienda sin que el bot la pise.

## Decisiones de producto (acordadas)

1. **Mecanismo:** marcar la conversación como derivada en la BD + exponerla en
   un endpoint de listado. Nada de email/webhook por ahora.
2. **Post-derivación:** un caso derivado se considera cerrado. Si el mismo
   cliente vuelve a escribir, se abre una **conversación/caso nuevo** desde cero.
3. **Acceso al panel:** `GET /casos` abierto (sin autenticación) en esta etapa.
4. **Formato:** JSON.

## Diseño

### 1. Modelo de datos (`database.py`)

Se agregan campos a `Conversacion` para registrar la derivación:

| Campo | Tipo | Default | Uso |
|---|---|---|---|
| `derivada` | `bool` | `False` | Marca que el caso salió del bot. Reemplaza a `estado_humano` como filtro de conversación activa. |
| `categoria` | `str \| None` | `None` | Categoría final (Venta / Servicio Técnico / Calibración/ISO). Indexado. |
| `derivada_en` | `datetime \| None` | `None` | Momento de la derivación (UTC). |
| `resumen_json` | `Text \| None` | `None` | Snapshot de los datos estructurados al derivar (ubicación, tipo_equipo, marca_modelo, síntoma, info_faltante). |

`estado_humano` **deja de ser un campo muerto y pasa a tener un propósito real**:
marca que un humano está atendiendo la conversación (ver sección 4). Es un eje
distinto de `derivada`: `derivada` = el bot juntó la info y encoló el caso;
`estado_humano` = un humano tomó la conversación y el bot debe callarse. Una
conversación puede estar derivada y todavía sin humano (`derivada=True`,
`estado_humano=False`), o tomada por un humano (`estado_humano=True`).

`obtener_o_crear_conversacion` cambia su filtro de `estado_humano == False` a
**"continuar la conversación salvo que esté derivada y sin humano atendiéndola"**,
es decir el filtro pasa a `derivada == False OR estado_humano == True`. Así:

- **Derivado y sin tomar** (`derivada=True, estado_humano=False`) → el próximo
  mensaje del cliente no lo encuentra y crea un caso nuevo (comportamiento del
  punto 2 de Decisiones).
- **Tomado por un humano** (`estado_humano=True`) → el próximo mensaje del cliente
  **continúa en la misma conversación** (no abre caso nuevo), para que el humano
  no pierda el hilo.

### 2. Lógica de derivación (`_procesar_mensaje` en `main.py`)

Tras guardar los mensajes (user + assistant), si `resultado.notificar_recepcion`:

- `conversacion.derivada = True`
- `conversacion.categoria = resultado.categoria.value`
- `conversacion.derivada_en = datetime.now(timezone.utc)`
- `conversacion.resumen_json = ` JSON con los campos relevantes del resultado
  (excluye `respuesta_al_cliente` y `notificar_recepcion`).
- `db.commit()`

Esto se encapsula en una función auxiliar `marcar_derivada(db, conversacion, resultado)`
en `database.py` para mantener la capa de persistencia separada.

### 3. Endpoint de panel (`GET /casos`)

- Lista conversaciones con `derivada == True`, ordenadas por `derivada_en` desc.
- Query param opcional `categoria` para filtrar por área
  (ej: `GET /casos?categoria=Servicio Técnico`).
- Respuesta JSON: lista de objetos con `conversacion_id`, `telefono_cliente`,
  `categoria`, `derivada_en`, y los campos del `resumen_json` desplegados
  (`ubicacion`, `tipo_equipo`, `marca_modelo`, `sintoma_falla`, `info_faltante`).
- Sin autenticación en esta etapa.

Schema de respuesta: nuevo modelo Pydantic `CasoDerivado`.

### 4. Traspaso a humano (`estado_humano`)

Un caso derivado queda en la cola, pero hasta ahora ningún humano puede "tomarlo"
ni el bot sabe cuándo callarse para no pisar a una persona. `estado_humano` cubre
eso: cuando vale `True`, **un humano está atendiendo la conversación y el bot no
responde**.

**Disparadores**

1. **Humano toma el caso desde el panel (principal).** Nuevo endpoint
   `POST /casos/{id}/tomar` → setea `estado_humano = True` en la conversación. Es
   la "elección de derivar a un humano": el asesor ve el caso en `/casos` y lo
   agarra. Idempotente (tomar dos veces no rompe nada; si el id no existe, 404).
2. **El cliente pide hablar con una persona (secundario, opcional).** Se agrega un
   campo `pide_humano: bool` al schema `RespuestaChatbot` (`main.py`); el bot lo
   marca cuando detecta la intención ("quiero hablar con alguien"). Esto **no**
   silencia al bot automáticamente: solo prioriza/señala el caso en el panel para
   que un humano lo tome. El silenciado ocurre recién con `tomar`.

**Guard en `_procesar_mensaje` (`main.py`)**

Al inicio de `_procesar_mensaje`, antes de llamar a Gemini: si la conversación
existe y `estado_humano == True`, **guardar el mensaje entrante del cliente** (para
que el humano lo vea en el historial) pero **no** llamar a Gemini ni generar
auto-respuesta. El endpoint responde sin mensaje al canal (en `/whatsapp`, TwiML
sin `<Message>`), de modo que el humano responde por fuera sin que el bot escriba
encima.

**Interacción con el filtro de conversación activa**

Ver sección 1: el filtro `derivada == False OR estado_humano == True` garantiza
que, una vez tomada por un humano, la conversación sigue siendo la activa para ese
teléfono (el cliente no abre un caso nuevo mientras el humano la atiende).

### 5. Manejo de errores

- Si `categoria` recibido en el query param no coincide con ninguna categoría
  conocida, devolver lista vacía (no error).
- La derivación es idempotente: si una conversación ya está derivada, no debería
  reabrirse para nuevos mensajes (el filtro `derivada == False` lo garantiza).

## Testing

Tests con SQLite en memoria (`sqlite:///:memory:`) y el cliente Gemini mockeado:

1. **Deriva correctamente:** un resultado con `notificar_recepcion=True` marca la
   conversación (`derivada=True`, `categoria`, `derivada_en`, `resumen_json`) y
   aparece en `GET /casos`.
2. **No deriva:** un resultado con `notificar_recepcion=False` no marca nada y la
   conversación no aparece en `/casos`.
3. **Caso nuevo tras derivar:** un mensaje posterior del mismo teléfono crea una
   conversación nueva (id distinto), no reusa la derivada.
4. **Filtro por categoría:** `GET /casos?categoria=...` devuelve solo los casos de
   esa categoría.
5. **Snapshot correcto:** el `resumen_json` guardado refleja los campos del
   resultado al momento de derivar.
6. **Traspaso silencia al bot:** con `estado_humano=True`, un mensaje del cliente
   se guarda pero NO dispara llamada a Gemini ni auto-respuesta (el endpoint
   responde sin mensaje).
7. **Tomar caso desde el panel:** `POST /casos/{id}/tomar` setea
   `estado_humano=True`, es idempotente, y devuelve 404 si el id no existe.
8. **Conversación tomada no abre caso nuevo:** con `estado_humano=True`, un mensaje
   posterior del mismo teléfono continúa en la misma conversación (mismo id), a
   diferencia del caso derivado-y-sin-tomar.
9. **`pide_humano` no silencia solo:** un resultado con `pide_humano=True` sin
   `tomar` deja al bot respondiendo normalmente; recién `tomar` lo silencia.

## Fuera de alcance (siguiente iteración)

- Devolver el control al bot / cerrar el caso tras la atención humana (des-marcar
  `estado_humano`). Por ahora, una vez tomada, la conversación queda con el humano.
- Autenticación del panel y del endpoint `tomar` con `APP_SECRET_KEY` / `X-API-Key`.
- Notificaciones push (email / webhook a Slack o CRM).
- Vista HTML del panel.
- Validación de firma de Twilio (`X-Twilio-Signature`) — tarea aparte acordada
  para después de esta feature.
