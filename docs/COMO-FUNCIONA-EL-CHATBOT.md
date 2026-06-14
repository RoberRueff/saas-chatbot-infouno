# 🤖 Cómo funciona el Chatbot de Balanzas

> Guía visual para entender, de un vistazo, cómo trabaja el chatbot — sin necesidad de saber programar.

## En una frase
Un cliente escribe por **WhatsApp**, la **IA (Gemini)** entiende su consulta, la **clasifica** (venta / servicio técnico / calibración), le responde en tono argentino, y guarda todo para **derivar el caso al área correcta** — sin dar precios ni diagnósticos.

---

## 🗺️ Diagrama de flujo general

```
┌─────────────┐
│   CLIENTE   │  Escribe un mensaje
│  (WhatsApp) │  "Necesito calibrar una balanza en Córdoba"
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│      TWILIO         │  Recibe el WhatsApp y lo reenvía
│   (puente WhatsApp) │  como webhook a nuestro servidor
└──────┬──────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│        SERVIDOR (FastAPI / main.py)      │
│            endpoint  POST /whatsapp      │
└──────┬───────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  1) Busca/crea la CONVERSACIÓN del       │
│     cliente por su número de teléfono    │  ◄──┐
│     (database.py + SQLite)               │     │
└──────┬───────────────────────────────────┘     │
       │                                          │
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
└──────┬───────────────────────────────────┘      │
       │                                          │
       ▼                                          │
┌─────────────────────────────────────────┐      │
│  4) La IA decide y devuelve:             │      │
│     • categoría (venta/servicio/...)     │      │
│     • ubicación, equipo, marca, falla    │      │
│     • respuesta_al_cliente               │      │
│     • ¿ya tengo info para derivar? (T/F) │      │
└──────┬───────────────────────────────────┘      │
       │                                          │
       ▼                                          │
┌─────────────────────────────────────────┐      │
│  5) GUARDA el mensaje del cliente y la   │──────┘
│     respuesta + datos en la base         │
└──────┬───────────────────────────────────┘
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
| Clasificar la consulta | Dar precios o cotizaciones |
| Pedir los datos que faltan | Hacer diagnósticos técnicos |
| Responder en voseo argentino | Responder en otro idioma |
| Decidir cuándo ya hay info para derivar | Seguir preguntando de más |

Y devuelve siempre una **respuesta estructurada (JSON)** con campos fijos, no texto suelto:

```
categoría · ubicación · tipo_equipo · marca_modelo ·
síntoma_falla · info_faltante · respuesta_al_cliente · notificar_recepción
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
   provincia estás?")        va a contactar"
          │                          │
          └──────► vuelve ◄──────────┘
                  al inicio        (caso queda listo
                                    para derivar)
```

---

## 🧩 Piezas del sistema

| Componente | Para qué sirve | Archivo |
|---|---|---|
| **FastAPI** | El servidor web que recibe mensajes | `main.py` |
| **Gemini 2.5 Flash** | El "cerebro" que entiende y clasifica | `main.py` |
| **SQLite + SQLAlchemy** | Memoria: guarda conversaciones y mensajes | `database.py` |
| **Twilio** | El puente con WhatsApp | endpoint `/whatsapp` |
| **Endpoint `/chat`** | Versión API para probar sin WhatsApp | `main.py` |

---

**Resumen ultra-corto:** WhatsApp → Twilio → FastAPI → busca historial → Gemini clasifica y responde → guarda en SQLite → responde al cliente. Todo orientado a **capturar el caso y derivarlo**, nunca a vender ni reparar directamente.

---

## 📋 Para el futuro (lo único que tenés que recordar)

**Prender el bot:** abrir la Terminal y correr un solo comando:

```bash
"/Users/Rober/Desktop/Proyectos/saas chatbot balanzas/iniciar-chatbot.sh"
```

Eso levanta el servidor + el túnel (con la URL fija) juntos.

- **Apagar:** apretá `Ctrl+C` en esa misma terminal.
- **Twilio:** ya está configurado, **no se toca más** (la URL de ngrok es fija).

---
