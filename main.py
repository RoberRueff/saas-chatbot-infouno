import json
import logging
import os
import traceback
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, guardar_mensaje, init_db, obtener_o_crear_conversacion
from ia import guardrails
from seguridad.twilio import verificar_twilio

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global gemini_client
    init_db()
    if _ia_configurada():
        gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    yield


app = FastAPI(title="Chatbot Balanzas", version="1.0.0", lifespan=lifespan)

gemini_client: genai.Client | None = None

SYSTEM_PROMPT = """
Sos el asistente virtual de una fábrica argentina de balanzas e instrumentos de pesaje industrial.
Atendés consultas comerciales y técnicas de clientes reales: industrias, comercios, transportistas y laboratorios.

## REGLAS ESTRICTAS DEL NEGOCIO

1. NUNCA des precios, cotizaciones ni valores estimados. Si el cliente pregunta, decile que un asesor lo va a contactar.
2. NUNCA hacés diagnósticos técnicos definitivos. Podés preguntar síntomas, pero no afirmar qué tiene o cuánto cuesta reparar.
3. Siempre hablá de vos (voseo argentino), en tono profesional y cálido. Sin tuteo ni ustedeo formal.
4. Tu única función es capturar la información necesaria para derivar el caso al área correcta (ventas, servicio técnico o calibración/ISO).
5. Si el cliente menciona una localidad o provincia, registrala. Si no lo hace, preguntale.
6. Identificá el tipo de equipo: báscula de camiones, balanza comercial, balanza de laboratorio, pesómetro, balanza de cinta, etc.
7. Para servicio técnico, relevá: marca, modelo, síntoma de falla y urgencia.
8. Para calibración/ISO: empresa, equipo, tipo de certificación requerida, plazo.
9. Una vez que tenés la información mínima para derivar, no seguís preguntando: confirmá la recepción y avisá que alguien los va a contactar.
10. Si el mensaje es ambiguo o no tiene que ver con pesaje industrial, clasificalo como "Desconocido" y pedí aclaración.

## INFORMACIÓN MÍNIMA PARA DERIVAR
- Venta: tipo de equipo + ubicación
- Servicio técnico: marca/modelo + síntoma + ubicación
- Calibración/ISO: empresa + tipo de equipo + tipo de certificado + ubicación

## IDIOMA
Solo español rioplatense. Ninguna respuesta en otro idioma.
""".strip()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class Categoria(str, Enum):
    venta = "Venta de Equipos"
    servicio = "Servicio Técnico"
    calibracion = "Calibración/ISO"
    desconocido = "Desconocido"


class RespuestaChatbot(BaseModel):
    categoria: Categoria = Field(description="Clasificación del tipo de consulta")
    ubicacion: Optional[str] = Field(
        None, description="Ciudad o provincia argentina mencionada por el cliente"
    )
    tipo_equipo: Optional[str] = Field(
        None,
        description="Tipo de equipo de pesaje (ej: báscula de camiones, balanza comercial, etc.)",
    )
    marca_modelo: Optional[str] = Field(
        None, description="Marca y/o modelo del equipo, si fue mencionado"
    )
    sintoma_falla: Optional[str] = Field(
        None,
        description="Descripción del problema o falla reportada, solo aplica a servicio técnico",
    )
    info_faltante: list[str] = Field(
        default_factory=list,
        description="Lista de datos críticos que faltan para poder derivar el caso",
    )
    respuesta_al_cliente: str = Field(
        description="Respuesta breve para enviar al cliente, en voseo argentino, profesional, SIN precios ni diagnósticos"
    )
    notificar_recepcion: bool = Field(
        description="True si ya tenemos la información mínima para derivar el caso. False si todavía falta preguntar algo."
    )


class MensajeEntrada(BaseModel):
    telefono_cliente: str = Field(description="Número de teléfono del cliente (identificador único)")
    mensaje: str = Field(description="Mensaje enviado por el cliente")


class RespuestaChat(BaseModel):
    conversacion_id: Optional[int] = None  # None si un guardrail bloqueó antes de crear conversación
    respuesta: str
    datos: RespuestaChatbot


# ---------------------------------------------------------------------------
# IA — Google Gemini
# ---------------------------------------------------------------------------

def _ia_configurada() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def _llamar_gemini(historial: list[dict], texto: str) -> RespuestaChatbot:
    contents = []
    for msg in historial:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(genai_types.Content(
            role=role,
            parts=[genai_types.Part.from_text(text=msg["content"])],
        ))
    contents.append(genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=texto)],
    ))

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RespuestaChatbot,
            temperature=0.3,
        ),
    )
    data = json.loads(response.text)
    return RespuestaChatbot(**data)


# ---------------------------------------------------------------------------
# Lógica compartida
# ---------------------------------------------------------------------------

MAX_HISTORIAL_MENSAJES = 30  # ventana de contexto para acotar tokens/latencia


def _respuesta_bloqueada(texto_fijo: str) -> RespuestaChatbot:
    """Respuesta sintética para cuando un guardrail de entrada bloquea el mensaje."""
    return RespuestaChatbot(
        categoria=Categoria.desconocido,
        respuesta_al_cliente=texto_fijo,
        notificar_recepcion=False,
    )


def _procesar_mensaje(db: Session, telefono: str, texto: str) -> tuple[Optional[int], RespuestaChatbot]:
    # --- Guardrails de entrada (rate limit -> validación -> anti-injection) ---
    # Si bloquea, NO llamamos a Gemini y NO persistimos el mensaje (evita que un
    # intento de injection quede en el historial y contamine las próximas llamadas).
    veredicto = guardrails.revisar_entrada(telefono, texto)
    if not veredicto.permitido:
        logger.warning("Guardrail de entrada bloqueó mensaje de %s — motivo: %s", telefono, veredicto.motivo)
        return None, _respuesta_bloqueada(veredicto.respuesta_fija)

    conversacion = obtener_o_crear_conversacion(db, telefono)
    mensajes = conversacion.mensajes[-MAX_HISTORIAL_MENSAJES:]
    # Gemini exige que el historial arranque con un turno de usuario.
    while mensajes and mensajes[0].rol != "user":
        mensajes = mensajes[1:]
    historial = [{"role": msg.rol, "content": msg.contenido} for msg in mensajes]
    # Llamamos a Gemini ANTES de persistir: si falla, no dejamos un turno "user"
    # huérfano que ensucie el historial (dos turnos de usuario seguidos) en el próximo mensaje.
    resultado = _llamar_gemini(historial, texto)

    # --- Guardrail de salida (reglas de negocio: sin precios ni diagnósticos) ---
    texto_seguro, motivo_salida = guardrails.sanitizar_salida(resultado.respuesta_al_cliente)
    if motivo_salida is not None:
        logger.warning("Guardrail de salida sanitizó respuesta para %s — motivo: %s", telefono, motivo_salida)
        resultado.respuesta_al_cliente = texto_seguro

    nota_json = resultado.model_dump_json(exclude={"respuesta_al_cliente"}, exclude_none=False)
    guardar_mensaje(db, conversacion.id, "user", texto)
    guardar_mensaje(db, conversacion.id, "assistant", resultado.respuesta_al_cliente, nota_json)
    return conversacion.id, resultado


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "servicio": "Chatbot Balanzas", "ia": "gemini-2.5-flash"}


@app.post("/chat", response_model=RespuestaChat)
def chat(entrada: MensajeEntrada, db: Session = Depends(get_db)):
    if not _ia_configurada():
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY no configurada")
    try:
        conv_id, resultado = _procesar_mensaje(db, entrada.telefono_cliente, entrada.mensaje)
    except Exception as e:
        print("\n" + "="*60)
        print("ERROR EN /chat — GEMINI")
        print("="*60)
        traceback.print_exc()
        print("="*60 + "\n")
        raise HTTPException(status_code=502, detail=f"Error Gemini: {str(e)}")
    return RespuestaChat(
        conversacion_id=conv_id,
        respuesta=resultado.respuesta_al_cliente,
        datos=resultado,
    )


@app.post("/whatsapp", dependencies=[Depends(verificar_twilio)])
def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    db: Session = Depends(get_db),
):
    if not _ia_configurada():
        return Response(
            content="<Response><Message>Servicio temporalmente no disponible.</Message></Response>",
            media_type="application/xml",
        )

    telefono = From.replace("whatsapp:", "").strip()

    try:
        _, resultado = _procesar_mensaje(db, telefono, Body)
        respuesta_texto = resultado.respuesta_al_cliente
    except Exception as e:
        print("\n" + "="*60)
        print("ERROR EN /whatsapp — GEMINI")
        print(f"Teléfono: {telefono}")
        print(f"Mensaje recibido: {Body}")
        print("Detalle del error:")
        traceback.print_exc()
        print("="*60 + "\n")
        respuesta_texto = "Hubo un problema procesando tu mensaje. Por favor intentá de nuevo en unos minutos."

    twiml = f"<Response><Message>{xml_escape(respuesta_texto)}</Message></Response>"
    return Response(content=twiml, media_type="application/xml")
