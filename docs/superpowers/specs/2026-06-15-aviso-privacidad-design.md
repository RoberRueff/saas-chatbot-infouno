# Diseño — Aviso de privacidad (deber de informar al recabar, art. 6)

**Fecha:** 2026-06-15
**Estado:** Aprobado
**Rama:** feat/clasificacion-departamentos-email

## Problema

La Ley 25.326 art. 6 obliga a informar al titular **al recabar** sus datos:
finalidad, identidad del responsable y derechos (acceso/rectificación/supresión).
El chatbot hoy no muestra ningún aviso. Es el pendiente de código del hallazgo
#7 (el registro ante la AAIP es trámite administrativo, no código).

## Decisión

Mostrar un aviso corto en la **primera respuesta de cada conversación nueva**
(cumple "informar al recabar" sin repetir en cada mensaje; como las
conversaciones expiran a las 24 h, reaparece periódicamente).

## Componentes

### 1. Constante `MSG_AVISO_PRIVACIDAD` (`main.py`)

```python
MSG_AVISO_PRIVACIDAD = (
    "Aviso de privacidad: tus datos (teléfono y mensajes) los trata infouno solo "
    "para atender y derivar tu consulta. Podés pedir acceder a ellos o borrarlos "
    "cuando quieras."
)
```

Cubre los tres elementos del art. 6: **responsable** (infouno), **finalidad**
(atender y derivar la consulta) y **derechos** (acceso / borrado). Voseo, sin
emoji, consistente con los demás mensajes fijos.

### 2. Lógica en `_procesar_mensaje`

- Después de `obtener_o_crear_conversacion`, capturar
  `es_primer_turno = not conversacion.mensajes` (una conversación recién creada
  no tiene mensajes).
- Helper `_con_aviso_si_primero(texto, es_primer_turno) -> str`: devuelve
  `f"{texto}\n\n{MSG_AVISO_PRIVACIDAD}"` si es el primer turno, o `texto` si no.
- Aplicarlo a `resultado.respuesta_al_cliente` en las dos ramas que responden al
  cliente: la **normal** (tras sanitizar la salida) y la de **escalamiento a
  humano** (tras fijar `MSG_ESCALAMIENTO_HUMANO`).

### 3. Dónde NO aparece

- Bloqueos de guardrail de entrada: retornan antes de crear conversación.
- Mensajes siguientes de la misma conversación (`es_primer_turno` es False).
- Modo humano (silencio): una conversación nueva nunca está en modo humano, así
  que el primer turno nunca cae en el path silencioso.

### 4. Persistencia

El mensaje del bot se guarda **con** el aviso incluido (registro fiel de lo que
recibió el cliente). El riesgo de que el modelo "imite" el aviso en turnos
siguientes es despreciable (texto corto, `temperature=0.3`) y, si ocurriera, es
inocuo (no viola ningún guardrail de salida).

## Tests

Con `main._llamar_gemini` reemplazado por un doble (patrón de `test_handoff.py`),
SQLite en memoria:

1. Primer mensaje de una conversación nueva → `MSG_AVISO_PRIVACIDAD` está en la
   respuesta devuelta.
2. Segundo mensaje de la misma conversación → la respuesta NO incluye el aviso.
3. Escalamiento a humano en el primer turno → la respuesta incluye
   `MSG_ESCALAMIENTO_HUMANO` **y** el aviso.

Runner stdlib del repo (colectable por pytest).

## Fuera de alcance

- **Registro de la base ante la AAIP** (arts. 21/24): trámite administrativo, no
  código.
