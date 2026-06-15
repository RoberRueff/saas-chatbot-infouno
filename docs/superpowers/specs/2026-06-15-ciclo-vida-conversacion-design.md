# Diseño — Ciclo de vida de la conversación (expiración por inactividad)

**Fecha:** 2026-06-15
**Estado:** Aprobado
**Rama:** feat/clasificacion-departamentos-email

## Problema

`obtener_o_crear_conversacion` ([database.py:67-82](../../../database.py#L67))
devuelve siempre la última conversación del teléfono con `estado_humano == False`,
**sin importar `derivada` ni cuánto tiempo pasó**. Consecuencia:

- Una vez que un cliente fue derivado (`derivada=True`), todos sus mensajes
  futuros reutilizan esa misma conversación.
- La derivación exige `not conversacion.derivada`
  ([main.py:245-249](../../../main.py#L245)), así que **una consulta nueva del
  mismo teléfono —días después, otro tema— nunca genera un segundo email de
  derivación**. El caso queda invisible para el equipo.

## Objetivo

Que el próximo mensaje de un cliente arranque una **conversación nueva** cuando
la anterior está inactiva, de modo que un cliente que vuelve pueda volver a
derivarse.

## Decisión de diseño

- **Disparador:** inactividad por tiempo (una sola regla; cubre tanto al cliente
  derivado que vuelve como a la charla abandonada).
- **Ventana:** 24 horas (coincide con la ventana de sesión de WhatsApp/Twilio).
- **Medición (Opción A):** sin cambio de schema. Se calcula la última actividad
  a partir de la fecha del último mensaje de la conversación; si pasaron ≥24 h,
  se crea una nueva. Cero migración, encaja con el volumen del MVP.

## Cambio

Único y acotado, en `obtener_o_crear_conversacion` ([database.py:67-82](../../../database.py#L67)):

1. Busca la última conversación con `estado_humano == False` (igual que hoy).
2. Si existe, calcula su última actividad =
   fecha del último mensaje, o `fecha_creacion` si todavía no tiene mensajes.
3. Si esa última actividad es **< 24 h**, la reutiliza (comportamiento actual).
4. Si es **≥ 24 h** (o no hay conversación previa), crea una nueva.

La conversación nueva nace con `derivada=False`, así que el cliente que vuelve
**vuelve a poder derivarse** → arregla el bug.

### Detalles

- **Constante:** `VENTANA_CONVERSACION_HORAS = 24` en `database.py`, en un solo
  punto.
- **Inyección de tiempo para tests:** `obtener_o_crear_conversacion` recibe un
  parámetro opcional `ahora: datetime | None = None` (mismo patrón que
  `rate_limit.permitido`), para testear sin esperar 24 h reales. Default:
  `datetime.now(timezone.utc)`.
- **Comparación de fechas:** los timestamps se guardan timezone-aware en UTC
  ([database.py:34-36, 51-53](../../../database.py#L34)); la comparación usa el
  mismo `tz`.
- **Cálculo de la última actividad:** consultar la fecha del último mensaje de la
  conversación candidata (ordenado por `id`/`fecha` desc, `first()`), con
  fallback a `fecha_creacion` si no hay mensajes. No se carga toda la relación
  `mensajes`.
- **Sin cambios en `main.py`:** el flujo de `_procesar_mensaje` queda igual; solo
  cambia a qué conversación apunta.

## Tests

En `notificaciones/tests/test_db_derivacion.py` (o un módulo nuevo):

1. Mensaje dentro de la ventana → reutiliza la misma conversación (mismo `id`).
2. Mensaje pasada la ventana → crea conversación nueva (`id` distinto,
   `derivada=False`).
3. Cliente derivado que vuelve después de 24 h → puede generar una derivación
   nueva (la conversación nueva tiene `derivada=False`).
4. Conversación creada hace >24 h pero **sin mensajes** → crea nueva (cubre el
   edge de un fallo de Gemini que dejó la conversación vacía).

## Fuera de alcance (mejoras futuras)

- **Re-derivar al cambiar de categoría dentro de la misma conversación.** Con el
  modelo de solo-inactividad, si dentro de las 24 h el cliente ya derivado cambia
  de tema (p. ej. de comercial a servicio técnico), sigue siendo la misma
  conversación con `derivada=True` y no se dispara un segundo email. Limitación
  conocida y aceptada para este MVP.
- **Handoff a humano:** el campo `estado_humano` sigue existiendo y filtrándose,
  pero ningún código lo setea a `True`. Queda como feature separada.
- **Columna `ultima_actividad` indexada** (Opción B): optimización para cuando el
  volumen lo justifique.
