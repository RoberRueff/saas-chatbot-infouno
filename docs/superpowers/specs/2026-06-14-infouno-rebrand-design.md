# Adaptación del chatbot: de Balanzas a Infouno

**Fecha:** 2026-06-14
**Estado:** Aprobado para implementación

## Contexto

Este proyecto es un clon del chatbot de "saas chatbot balanzas" (WhatsApp + Gemini
2.5 Flash + FastAPI + SQLite, con guardrails de entrada/salida). El objetivo es
adaptarlo para **infouno**, agencia argentina que ofrece **automatizaciones de
procesos con IA** y **desarrollo web** para pymes (infouno.com.ar).

El bot conserva su propósito: captar la consulta del cliente por WhatsApp,
clasificarla, relevar los datos mínimos del lead y **derivar el caso al área
correcta** — sin vender ni cotizar directamente.

## Enfoque: re-skin de dominio

La arquitectura no cambia. FastAPI, el cliente Gemini, la base SQLite, los
endpoints (`/`, `/chat`, `/whatsapp`), el verificador de Twilio y la mecánica de
guardrails (rate limit → validación → anti-injection → filtro de salida) se
mantienen idénticos. Solo se reemplaza la **capa de dominio**: system prompt,
categorías, campos capturados, mensajes fijos de guardrails y textos/docs.

Se descartó cualquier cambio de comportamiento (informar sobre servicios, dar
rangos de precio) por decisión explícita del usuario: el bot sigue siendo
**captar y derivar**, y **nunca da precios**.

## Cambios por componente

### 1. Identidad — `SYSTEM_PROMPT` (main.py)

Reescribir el system prompt para infouno:

- Rol: asistente virtual de **infouno**, agencia argentina de automatizaciones de
  procesos con IA y desarrollo web para pymes.
- Función única: captar la información necesaria para derivar el caso al área
  correcta (Automatización IA o Desarrollo Web).
- Reglas que se mantienen:
  - **Nunca** dar precios, cotizaciones ni valores estimados → un asesor contacta.
  - Voseo argentino, tono profesional y cálido, solo español rioplatense.
  - Si el cliente menciona localidad/provincia, registrarla; si no, preguntarla.
  - Una vez que hay info mínima para derivar, no seguir preguntando: confirmar
    recepción y avisar que un asesor lo va a contactar.
  - Si el mensaje es ambiguo o ajeno a los servicios, clasificar como
    "Desconocido" y pedir aclaración.
- Regla **eliminada**: "no hacer diagnósticos técnicos" (era específica de la
  reparación de balanzas).

### 2. Categorías — `enum Categoria` (main.py)

| Antes (balanzas)    | Ahora (infouno)        | Valor del enum            |
|---------------------|------------------------|---------------------------|
| Venta de Equipos    | Automatización con IA  | `"Automatización con IA"` |
| Servicio Técnico    | Desarrollo Web         | `"Desarrollo Web"`        |
| Calibración/ISO     | *(eliminada)*          | —                         |
| Desconocido         | Desconocido            | `"Desconocido"`           |

Se mantienen 2 categorías de servicio + Desconocido. No se subdivide más por ahora.

### 3. Datos capturados — `RespuestaChatbot` (main.py)

Se reemplazan los campos de equipos por campos de agencia/pyme:

| Campo                | Cambio        | Descripción                                          |
|----------------------|---------------|------------------------------------------------------|
| `categoria`          | se mantiene   | Clasificación (ver tabla arriba)                     |
| `ubicacion`          | se mantiene   | Ciudad o provincia argentina                         |
| `nombre_empresa`     | **nuevo**     | Nombre de la empresa/pyme del cliente                |
| `rubro`              | **nuevo**     | Rubro o sector de la pyme                            |
| `necesidad`          | **nuevo**     | Proceso a automatizar o tipo de web que necesita     |
| `tipo_equipo`        | **eliminado** | —                                                    |
| `marca_modelo`       | **eliminado** | —                                                    |
| `sintoma_falla`      | **eliminado** | —                                                    |
| `info_faltante`      | se mantiene   | Datos críticos que faltan para derivar               |
| `respuesta_al_cliente` | se mantiene | Respuesta en voseo, sin precios                      |
| `notificar_recepcion`| se mantiene   | True si ya hay info mínima para derivar              |

**Info mínima para derivar:**
- Automatización con IA → `rubro` + `necesidad` + `ubicacion`
- Desarrollo Web → tipo de proyecto (institucional / e-commerce / landing, dentro
  de `necesidad`) + `rubro` + `ubicacion`

`nombre_empresa` es deseable pero no bloquea la derivación (no es obligatorio en
`info_faltante`).

### 4. Guardrails — `ia/config.py`

- `PATRONES_PROHIBIDOS_SALIDA`: se conservan los patrones de **precio**; se
  **eliminan** los patrones de **diagnóstico** (no aplican a una agencia).
- `MSG_BLOQUEO_INJECTION`: reescribir mencionando los servicios de infouno
  (automatización con IA y desarrollo web) en lugar de balanzas/pesaje.
- `MSG_SALIDA_SANITIZADA`: reemplazar la sugerencia "(ubicación, tipo de equipo)"
  por "(rubro, tipo de proyecto)".
- Resto (longitud máx., rate limit, patrones de injection) sin cambios.

### 5. Textos y metadatos

- `main.py`: `FastAPI(title="Chatbot Infouno", ...)` y respuesta del endpoint `/`
  (`"servicio": "Chatbot Infouno"`).
- `README.md`, `docs/COMO-FUNCIONA-EL-CHATBOT.md`: actualizar dominio y ejemplos
  (incluida la ruta del script en la guía, que apunta a "saas chatbot balanzas").
- `iniciar-chatbot.sh`, `subir-cambios-mac.sh`, `subir-cambios-windows.ps1`:
  reemplazar nombres "balanzas" por "infouno".
- `ia/tests/test_guardrails.py`: actualizar las aserciones que validan el texto de
  `MSG_BLOQUEO_INJECTION` y cualquier dato de dominio de balanzas.
- `docs/superpowers/specs/2026-06-13-derivacion-casos-design.md`: doc heredado de
  balanzas; se deja como referencia histórica (no se versiona como propio) salvo
  que el usuario pida limpiarlo.

## Out of scope

- Cambios de arquitectura, base de datos o flujo de conversación.
- Dar precios o rangos.
- Capa de información de servicios (el bot no explica servicios en profundidad).
- Servicios de impresión 3D y diseño industrial (excluidos del alcance del bot).

## Criterios de éxito

1. Ninguna referencia a "balanza/pesaje/calibración" en código, prompts, mensajes
   de guardrails ni docs (verificable con `grep -ri balanza`).
2. El bot clasifica consultas en Automatización con IA / Desarrollo Web /
   Desconocido y captura `ubicacion`, `nombre_empresa`, `rubro`, `necesidad`.
3. Ante consultas de precio, deriva a asesor (no cotiza); el guardrail de salida de
   precios sigue activo.
4. Los tests (`ia/tests/`, `seguridad/tests/`) pasan con los textos actualizados.
