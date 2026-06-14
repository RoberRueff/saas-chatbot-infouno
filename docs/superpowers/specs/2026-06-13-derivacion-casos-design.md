# Diseño — Derivación de casos y panel de consulta

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

`estado_humano` se mantiene en el modelo por compatibilidad pero deja de usarse
como filtro; el filtro de conversación activa pasa a `derivada == False`.

`obtener_o_crear_conversacion` cambia su filtro de `estado_humano == False` a
`derivada == False`. Así, tras derivar, el próximo mensaje del cliente no
encuentra conversación activa y crea una nueva (caso nuevo).

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

### 4. Manejo de errores

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

## Fuera de alcance (siguiente iteración)

- Autenticación del panel con `APP_SECRET_KEY` / `X-API-Key`.
- Notificaciones push (email / webhook a Slack o CRM).
- Vista HTML del panel.
- Validación de firma de Twilio (`X-Twilio-Signature`) — tarea aparte acordada
  para después de esta feature.
