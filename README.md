# Chatbot Infouno

Chatbot de WhatsApp para infouno, agencia argentina de automatización de procesos con IA y desarrollo web para pymes.  
Captura consultas de clientes (Automatización con IA, Desarrollo Web) y las clasifica con IA para derivarlas al área correspondiente.

## Stack

- **Backend:** FastAPI + Python 3.11
- **IA:** Google Gemini 2.0 Flash (Structured Outputs)
- **Base de datos:** SQLite (SQLAlchemy 2.x)
- **Canal:** WhatsApp vía Twilio Sandbox
- **Despliegue local:** Uvicorn + Ngrok

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv venv
venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
copy .env.example .env
# Editá .env y poné tu GEMINI_API_KEY

# 4. Iniciar servidor
uvicorn main:app --reload --port 8000
```

## Variables de entorno

Copiá `.env.example` como `.env` y completá:

| Variable | Descripción |
|---|---|
| `GEMINI_API_KEY` | Clave de Google AI Studio ([obtener aquí](https://aistudio.google.com/app/apikey)) |
| `APP_SECRET_KEY` | Clave secreta de la app (cambiala en producción) |

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/chat` | API REST para pruebas |
| `POST` | `/whatsapp` | Webhook de Twilio (WhatsApp) |

## Tests

Instalá las dependencias de desarrollo y corré toda la suite con pytest:

```bash
pip install -r requirements-dev.txt
pytest
```

Cada archivo de test también trae un runner propio para correrlo aislado sin pytest:

```bash
python3 ia/tests/test_guardrails.py
```

## Seguridad y guardrails (`ia/`)

Toda la lógica de seguridad de la IA vive aislada en la carpeta `ia/`. Se aplica
automáticamente dentro de `_procesar_mensaje`, antes y después de llamar a Gemini.

| Archivo | Responsabilidad |
|---|---|
| `ia/config.py` | Parámetros ajustables: umbrales, patrones (regex) y mensajes fijos al cliente. Es el único lugar que hay que tocar para afinar el comportamiento. |
| `ia/rate_limit.py` | Límite de mensajes por teléfono (ventana deslizante en memoria). |
| `ia/input_guardrails.py` | Validación de entrada + detección de prompt injection / jailbreak. |
| `ia/output_guardrails.py` | Filtro de la respuesta del bot (regla de negocio: sin precios). |
| `ia/guardrails.py` | Fachada: única puerta que usa `main.py`. |

**Controles activos:**

1. **Rate limit por teléfono** — máx. `15` mensajes cada `60s` (configurable en `ia/config.py`).
2. **Validación de entrada** — rechaza mensajes vacíos o de más de `2000` caracteres.
3. **Anti prompt-injection** — detecta intentos de manipular al bot ("ignorá las instrucciones", "actuá como…", "system prompt", etc.). Heurística por patrones: primera barrera, no infalible.
4. **Filtro de salida** — si la respuesta generada incluye un precio (viola la regla del negocio), se reemplaza por un texto seguro.

Cuando un guardrail de **entrada** bloquea, el bot responde con un mensaje fijo,
registra el evento (`logging`) y **no llama a Gemini ni guarda el mensaje** (así
un intento de injection no contamina el historial de la conversación).

> **Nota:** el rate limit usa memoria del proceso. Sirve para 1 instancia de
> uvicorn; en un despliegue multi-proceso/multi-instancia habría que moverlo a
> una store compartida (Redis o la BD).

### Tests de guardrails

Los módulos de `ia/` solo dependen de la stdlib (no de FastAPI ni de Gemini),
así que los tests corren sin instalar las dependencias del proyecto:

```bash
python3 ia/tests/test_guardrails.py    # runner propio
# o, si tenés pytest instalado:
pytest ia/tests/
```

## Prueba rápida (local + WhatsApp)

```powershell
# Terminal 1 — servidor
uvicorn main:app --reload --port 8000

# Terminal 2 — túnel público
& "ruta\a\ngrok.exe" http 8000
```

Configurá la URL HTTPS de Ngrok en el **Sandbox de Twilio** como webhook del `/whatsapp`.

## Validación de firma de Twilio (`seguridad/`)

El endpoint `/whatsapp` es público: sin protección, cualquiera que descubra la URL
podría enviarle mensajes falsos y hacer que el bot llame a Gemini (gasto de cuota)
y guarde conversaciones truchas. Para evitarlo, `seguridad/twilio.py` valida la
firma `X-Twilio-Signature` que Twilio incluye en cada webhook (HMAC-SHA1 sobre la
URL + parámetros + tu `TWILIO_AUTH_TOKEN`). Si la firma no coincide, el request se
rechaza con **403** antes de tocar Gemini o la base.

Se aplica como dependencia de FastAPI en `/whatsapp`. Comportamiento:

- **Con `TWILIO_AUTH_TOKEN` configurado:** valida toda petición; las falsas se rechazan.
- **Sin token (desarrollo):** la validación se **desactiva** (con un warning en el log),
  para no friccionar las pruebas locales.

**Detalle ngrok:** Twilio firma con la URL *pública* (`https://...ngrok.../whatsapp`),
pero el request interno llega como `localhost`. El módulo reconstruye la URL pública
desde los headers de proxy (`X-Forwarded-Proto` / `Host`). Si tu setup no los reenvía
bien, podés forzar la URL exacta con la variable `TWILIO_WEBHOOK_URL`.

Tests (requieren `fastapi` y `twilio` instalados):

```bash
pytest seguridad/tests/
```

## Subir cambios a GitHub

```powershell
# Windows
.\subir-cambios-windows.ps1 "descripcion de los cambios"
```

```bash
# Mac / Linux
./subir-cambios-mac.sh "descripcion de los cambios"
```
