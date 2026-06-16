# 🤖 Cómo funciona el Chatbot de Infouno

> Guía visual para entender, de un vistazo, cómo trabaja el chatbot — sin necesidad de saber programar.

## En una frase
Un cliente escribe por **WhatsApp**, la **IA (Gemini)** entiende su consulta, la **clasifica** y la deriva al **departamento correcto** (Comercial, Administración o Servicio Técnico), le responde en tono argentino y **avisa por email al área** — sin dar precios. Si el cliente lo pide, lo **pasa a una persona**; y cuida los **datos** de cada cliente.

---

## 🗺️ Diagrama de flujo general

```
┌─────────────┐
│   CLIENTE   │  Escribe un mensaje
│  (WhatsApp) │  "Quiero automatizar la atención de mi local en Córdoba"
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│      TWILIO         │  Recibe el WhatsApp y lo reenvía
│   (puente WhatsApp) │  como webhook a nuestro servidor
└──────┬──────────────┘
       │   🔒 Se valida la FIRMA de Twilio (que el mensaje venga de verdad de Twilio)
       ▼
┌─────────────────────────────────────────┐
│        SERVIDOR (FastAPI / main.py)      │
│            endpoint  POST /whatsapp      │
└──────┬───────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  0) FILTROS DE SEGURIDAD (guardrails)    │
│     • Frena spam (muchos mensajes juntos)│
│     • Rechaza mensajes vacíos o enormes  │
│     • Bloquea intentos de "engañar" a la │
│       IA (prompt injection)              │
└──────┬───────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  1) Busca/crea la CONVERSACIÓN del       │
│     cliente por su número de teléfono    │  ◄──┐
│     (si pasaron +24 h sin hablar, abre   │     │
│      una conversación NUEVA)             │     │
└──────┬───────────────────────────────────┘     │
       │                                          │
       │   ¿La conversación está "en manos de     │
       │    una persona"? → el bot se queda       │
       │    callado (no responde).                │
       ▼                                          │
┌─────────────────────────────────────────┐      │
│  2) Arma el HISTORIAL (últimos 30 msjs)  │      │  Memoria de la
│     para que la IA tenga contexto        │      │  conversación
└──────┬───────────────────────────────────┘      │  (chatbot.db)
       │                                          │
       ▼                                          │
┌─────────────────────────────────────────┐      │
│  3) Llama a GEMINI 2.5 Flash             │      │
│     • System Prompt = reglas del negocio │      │
│     • Devuelve JSON estructurado         │      │
│     • Si la IA no contesta, responde un  │      │
│       mensaje amable (no se rompe)       │      │
└──────┬───────────────────────────────────┘      │
       │                                          │
       ▼                                          │
┌─────────────────────────────────────────┐      │
│  4) La IA decide y devuelve:             │      │
│     • categoría (departamento)           │      │
│     • ubicación, empresa, rubro, necesidad│     │
│     • respuesta_al_cliente               │      │
│     • ¿ya tengo info para derivar? (T/F) │      │
│     • ¿pide hablar con una persona? (T/F)│      │
└──────┬───────────────────────────────────┘      │
       │                                          │
       ▼                                          │
┌─────────────────────────────────────────┐      │
│  5) FILTRO DE SALIDA: si por error la    │      │
│     respuesta trae un precio, lo cambia  │      │
│     por un texto seguro                  │      │
└──────┬───────────────────────────────────┘      │
       │                                          │
       ▼                                          │
┌─────────────────────────────────────────┐      │
│  6) GUARDA el mensaje y la respuesta     │──────┘
│     en la base                           │
└──────┬───────────────────────────────────┘
       │
       ├───────► Si el caso quedó listo → 📧 EMAIL al departamento (en segundo plano)
       │
       ├───────► Si pidió una persona  → 📧 EMAIL "PIDE HUMANO" + el bot se calla
       │
       ▼
┌─────────────────────┐
│   RESPONDE al        │  El cliente recibe la respuesta
│   cliente (WhatsApp) │  en voseo, profesional, sin precios
└─────────────────────┘
```

---

## 🧠 La parte clave: qué hace la IA

La IA no responde "libre". Está **encerrada en reglas de negocio** (el `SYSTEM_PROMPT` en `main.py`):

| ✅ Sí hace | ❌ Nunca hace |
|---|---|
| Clasificar la consulta y derivarla al área | Dar precios o cotizaciones |
| Pedir los datos que faltan | Responder en otro idioma |
| Responder en voseo argentino | Seguir preguntando de más |
| Decidir cuándo ya hay info para derivar | Cotizar o cerrar la venta directo |
| Detectar cuándo el cliente **pide una persona** | Romperse si no logra responder (degrada con un mensaje amable) |

Y devuelve siempre una **respuesta estructurada (JSON)** con campos fijos, no texto suelto:

```
categoría · ubicación · nombre_empresa · rubro · necesidad ·
info_faltante · respuesta_al_cliente · notificar_recepción · solicita_humano
```

---

## 🔁 El ciclo de una conversación

```
Cliente pregunta  →  ¿Falta info?
                       │
          ┌────────────┴────────────┐
          │ SÍ                       │ NO
          ▼                          ▼
   La IA repregunta          La IA confirma recepción
   (ej: "¿en qué            "Listo, un asesor te
   provincia estás?")        va a contactar"  →  📧 email al área
          │                          │
          └──────► vuelve ◄──────────┘
                  al inicio        (caso queda listo
                                    para derivar)

Casos especiales:
• "Quiero hablar con una persona"  → el bot avisa al equipo y se queda callado.
• Pasan +24 h sin hablar           → el próximo mensaje abre una conversación NUEVA
                                      (y el bot vuelve a atender desde cero).
```

---

## 🆕 Mejoras y novedades (lo que se sumó)

| Mejora | Qué cambió, en criollo |
|---|---|
| **Conversación con vencimiento** | Si un cliente vuelve después de 24 h, se abre un caso nuevo. Antes, un cliente ya derivado "quedaba pegado" y nunca volvía a generar aviso al área. |
| **Pasar a una persona** | Si el cliente pide un humano, el bot **avisa al equipo por email** y deja de responder esa charla (para no pisar al asesor). Vuelve a atender solo después de 24 h de silencio. |
| **Email al derivar** | Cuando el caso está listo, llega un mail al departamento (Comercial / Administración / Servicio Técnico) con todos los datos. Se manda en segundo plano (no demora la respuesta) y nunca duplicado. |
| **A prueba de fallas de la IA** | Si Gemini no logra contestar (por su filtro de seguridad o por largo), el cliente recibe un mensaje amable pidiéndole reformular, en vez de un error. |
| **Más sólido bajo carga** | La base de datos se configuró para aguantar mejor varios mensajes a la vez (menos errores de "base ocupada"). |
| **Arranque seguro en producción** | Si falta una clave crítica (Twilio, claves de la API), el servidor **no arranca** y avisa, en lugar de quedar mal configurado en silencio. |
| **Cuidado de datos (privacidad)** | Borrado automático de conversaciones viejas, borrado a pedido de un cliente, y un aviso de privacidad en el primer mensaje. (Detalle abajo.) |

---

## 🔒 Seguridad y privacidad

**Seguridad (que nadie abuse del bot ni gaste la cuenta):**

- **Firma de Twilio:** el `/whatsapp` solo acepta mensajes que vengan realmente de Twilio. En producción es obligatorio; si falta la clave, el servidor no arranca.
- **Clave para el endpoint de prueba (`/chat`):** protegido con una API key.
- **Guardrails:** límite de mensajes por teléfono (anti-spam), rechazo de mensajes vacíos/enormes, y bloqueo de intentos de "engañar" a la IA. Además, un filtro de salida evita que se escape un precio.

**Privacidad (Ley 25.326 de Datos Personales):**

- **Borrado automático:** las conversaciones inactivas por más de **6 meses** se eliminan solas (teléfono + mensajes). La app las purga al arrancar y una vez por día.
- **Borrado a pedido:** si un cliente pide que borren sus datos, el operador puede eliminarlos con un endpoint protegido (`POST /admin/borrar-datos`).
- **Aviso de privacidad:** en el **primer mensaje** de cada conversación, el bot informa para qué usa los datos y que se pueden consultar o borrar.
- **Pendiente (no es código):** registrar la base de datos ante la **AAIP** (trámite administrativo).

---

## 🧩 Piezas del sistema

| Componente | Para qué sirve | Archivo |
|---|---|---|
| **FastAPI** | El servidor web que recibe mensajes | `main.py` |
| **Gemini 2.5 Flash** | El "cerebro" que entiende y clasifica | `main.py` |
| **SQLite + SQLAlchemy** | Memoria: guarda conversaciones y mensajes | `database.py` |
| **Twilio** | El puente con WhatsApp (+ validación de firma) | `seguridad/twilio.py` |
| **Guardrails** | Filtros de seguridad de entrada/salida de la IA | `ia/` |
| **Notificaciones** | Emails al área (derivación y "pide humano") | `notificaciones/` |
| **Endpoint `/chat`** | Versión API para probar sin WhatsApp | `main.py` |
| **Endpoint `/admin/borrar-datos`** | Borrado de datos de un cliente a pedido | `main.py` |

---

**Resumen ultra-corto:** WhatsApp → Twilio (firma) → FastAPI → guardrails → historial → Gemini clasifica y responde → guarda en SQLite → avisa al área por email → responde al cliente. Todo orientado a **capturar el caso y derivarlo**, nunca a cotizar ni cerrar la venta directamente — y cuidando la seguridad y los datos del cliente.

---

## 📋 Para el futuro (lo único que tenés que recordar)

**Prender el bot:** abrir la Terminal y correr un solo comando:

```bash
"/Users/Rober/Desktop/Proyectos/saas chatbot infouno/iniciar-chatbot.sh"
```

Eso levanta el servidor + el túnel (con la URL fija) juntos.

- **Apagar:** apretá `Ctrl+C` en esa misma terminal.
- **Twilio:** ya está configurado, **no se toca más** (la URL de ngrok es fija).
- **Si un cliente pide que borren sus datos:** se hace con el endpoint `/admin/borrar-datos` (pedíselo a quien maneja el servidor).

---
