# Diseño — Fallback grácil cuando Gemini no devuelve texto

**Fecha:** 2026-06-15
**Estado:** Aprobado
**Rama:** feat/clasificacion-departamentos-email

## Problema

En `_llamar_gemini` ([main.py:150-174](../../../main.py#L150)), la respuesta se parsea con
`json.loads(response.text)`. Cuando el modelo **no produce texto** —filtro de
seguridad, `MAX_TOKENS`, recitation— `response.text` es `None` (verificado en
google-genai 2.8.0: la property devuelve `None`, no lanza). Entonces
`json.loads(None)` lanza `TypeError`, que burbujea:

- `/chat` → `HTTPException 502` + `logger.exception` (ruido de crash).
- `/whatsapp` → mensaje genérico "Hubo un problema procesando tu mensaje…".

Es un caso esperable del modelo, no un crash de la app; merece degradar con
gracia, no romper.

## Objetivo

Cuando Gemini no devuelva texto, responder al cliente con un mensaje amable que
lo invite a reformular, sin excepción, sin derivación, y registrándolo como
`warning` (no `exception`).

## Cambio

Acotado a `_llamar_gemini` en `main.py`:

1. Tras `generate_content`, chequear `if not response.text:` (cubre `None` y `""`).
2. Si está vacío:
   - `logger.warning(...)` incluyendo el `finish_reason` del primer candidato si
     está disponible, para diagnóstico (acceso defensivo: si no se puede leer, se
     omite).
   - Devolver una `RespuestaChatbot` de fallback: `categoria=Desconocido`,
     `notificar_recepcion=False`, `respuesta_al_cliente=MSG_IA_SIN_RESPUESTA`.
3. Si hay texto, parsear como hoy.

El flujo posterior queda intacto: se sanitiza la salida, se persiste el turno y
se responde 200. No se dispara derivación (`categoria=Desconocido` y
`notificar_recepcion=False`).

### Rename del helper

`_respuesta_bloqueada(texto)` ([main.py:184-190](../../../main.py#L184)) produce
exactamente la forma necesaria (categoría desconocido + texto fijo + no
notificar). Como ahora cubre dos casos (bloqueo de guardrail **y** IA sin
respuesta), se renombra a un nombre genérico:

- `_respuesta_bloqueada` → `_respuesta_sintetica`

Se actualizan todos los usos (hoy solo uno, en `_procesar_mensaje`).

### Mensaje nuevo

Constante en `main.py` (es una condición de la capa IA, no un guardrail, así que
no va en `ia/config.py`):

```python
MSG_IA_SIN_RESPUESTA = (
    "Perdoná, no pude procesar bien tu mensaje. ¿Lo podés escribir de otra forma?"
)
```

En voseo, consistente con los mensajes de `ia/config.py`.

## Fuera de alcance

- **Errores de red / SDK** en `generate_content`: siguen propagando → 502. Es
  correcto: son transitorios y reintentables.
- **JSON malformado pese al `response_schema`**: muy improbable; ya lo cubre el
  `try/except` de los endpoints.

## Tests

`_llamar_gemini` usa el cliente global `gemini_client`, así que el test usa un
doble (fake) del cliente. Patrón: monkeypatch del módulo `main`.

1. **Gemini devuelve texto JSON válido** → `_llamar_gemini` devuelve la
   `RespuestaChatbot` parseada (categoría/campos del JSON).
2. **`response.text` es `None`** → devuelve el fallback: `categoria=Desconocido`,
   `notificar_recepcion is False`, `respuesta_al_cliente == MSG_IA_SIN_RESPUESTA`.
3. **`response.text` es `""`** → mismo fallback (cubre el borde de string vacío).

Runner stdlib del repo (sin pytest), consistente con los tests existentes.
