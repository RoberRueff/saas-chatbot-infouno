import json
import logging
import os
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Form, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import (
    engine,
    get_db,
    guardar_mensaje,
    init_db,
    liberar_derivacion,
    obtener_o_crear_conversacion,
    reclamar_derivacion,
)
from ia import guardrails
from notificaciones.email import enviar_aviso_derivacion
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


app = FastAPI(title="Chatbot Infouno", version="1.0.0", lifespan=lifespan)

gemini_client: genai.Client | None = None

SYSTEM_PROMPT = """
Sos el asistente virtual de infouno, una agencia argentina que ofrece automatización de procesos con IA y desarrollo web para pymes.
Atendés por WhatsApp a clientes reales y tu tarea es derivar cada consulta al DEPARTAMENTO correcto.

## DEPARTAMENTOS (categoría)
- "Comercial/Ventas": prospecto nuevo que quiere cotizar o contratar un servicio (automatización con IA o desarrollo web). Es el caso más común.
- "Administración": facturación, pagos, comprobantes, datos fiscales o temas de contrato.
- "Servicio Técnico": cliente existente con un problema o pedido de soporte sobre algo YA entregado (su web caída, su automatización fallando).
- "Desconocido": mensaje ambiguo o ajeno a infouno. Pedí aclaración, no derives.

## REGLAS ESTRICTAS DEL NEGOCIO
1. NUNCA des precios, cotizaciones ni valores estimados. Si preguntan, decí que un asesor los va a contactar con una propuesta a medida.
2. Hablá siempre de vos (voseo argentino), en tono profesional y cálido. Sin tuteo ni ustedeo formal.
3. Tu única función es capturar la información necesaria para derivar el caso. No resuelvas vos el pedido.
4. Si el cliente menciona una localidad o provincia, registrala; si no, preguntala.
5. Relevá el nombre de la empresa y el rubro de la pyme.
6. Para casos comerciales, identificá la línea de servicio (campo linea_servicio): "Automatización con IA" o "Desarrollo Web".
7. Una vez que tenés la información mínima para derivar, no seguís preguntando: confirmá la recepción y avisá que un asesor los va a contactar.

## INFORMACIÓN MÍNIMA PARA DERIVAR (recién ahí notificar_recepcion=True)
- Comercial/Ventas: necesidad (qué servicio) + rubro + ubicación
- Administración: nombre de la empresa + necesidad (qué trámite)
- Servicio Técnico: nombre de la empresa + necesidad (qué problema, sobre qué proyecto)

## IDIOMA
Solo español rioplatense. Ninguna respuesta en otro idioma.
""".strip()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class Categoria(str, Enum):
    comercial = "Comercial/Ventas"
    administracion = "Administración"
    servicio_tecnico = "Servicio Técnico"
    desconocido = "Desconocido"


class RespuestaChatbot(BaseModel):
    categoria: Categoria = Field(description="Clasificación del tipo de consulta")
    ubicacion: Optional[str] = Field(
        None, description="Ciudad o provincia argentina mencionada por el cliente"
    )
    nombre_empresa: Optional[str] = Field(
        None, description="Nombre de la empresa o pyme del cliente, si fue mencionado"
    )
    rubro: Optional[str] = Field(
        None, description="Rubro o sector de la pyme (ej: gastronomía, retail, salud, logística)"
    )
    necesidad: Optional[str] = Field(
        None,
        description="Qué proceso quiere automatizar o qué tipo de web necesita (institucional, e-commerce, landing)",
    )
    linea_servicio: Optional[str] = Field(
        None,
        description="Línea de servicio cuando aplica: 'Automatización con IA' o 'Desarrollo Web'. None si no corresponde.",
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


def verificar_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Auth simple para /chat: exige el header X-API-Key == APP_SECRET_KEY.

    Si APP_SECRET_KEY no está configurada, el endpoint queda cerrado (rechaza
    todo) en vez de abierto: fail-closed.
    """
    esperado = os.getenv("APP_SECRET_KEY", "")
    if not esperado or x_api_key != esperado:
        raise HTTPException(status_code=401, detail="API key inválida o ausente")


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


def _derivar_en_background(conversacion_id: int, resultado: RespuestaChatbot, telefono: str) -> None:
    """Envía el email de derivación FUERA del request (no bloquea la respuesta).

    Usa una sesión nueva (la del request ya se cerró). Reclama la derivación de
    forma atómica: solo el primero que gana la carrera envía; si el envío falla,
    libera la marca para reintentar en el próximo mensaje del cliente.
    """
    with Session(engine) as db:
        if not reclamar_derivacion(db, conversacion_id):
            return  # otro request ya está derivando este caso
        if not enviar_aviso_derivacion(resultado, telefono):
            liberar_derivacion(db, conversacion_id)


def _procesar_mensaje(
    db: Session,
    telefono: str,
    texto: str,
    background_tasks: BackgroundTasks | None = None,
) -> tuple[Optional[int], RespuestaChatbot]:
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

    # --- Derivación: si el caso quedó listo y todavía no fue notificado, AGENDAR
    # el envío del email en BACKGROUND (no bloquea la respuesta al cliente, así el
    # webhook de Twilio no se cuelga si el SMTP está lento). El reclamo atómico
    # dentro de la tarea garantiza un único envío por caso.
    if (background_tasks is not None
            and resultado.notificar_recepcion
            and not conversacion.derivada
            and resultado.categoria != Categoria.desconocido):
        background_tasks.add_task(_derivar_en_background, conversacion.id, resultado, telefono)

    return conversacion.id, resultado


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "servicio": "Chatbot Infouno", "ia": "gemini-2.5-flash"}


@app.post("/chat", response_model=RespuestaChat, dependencies=[Depends(verificar_api_key)])
def chat(entrada: MensajeEntrada, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not _ia_configurada():
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY no configurada")
    try:
        conv_id, resultado = _procesar_mensaje(db, entrada.telefono_cliente, entrada.mensaje, background_tasks)
    except Exception as e:
        logger.exception("Error procesando /chat para %s", entrada.telefono_cliente)
        raise HTTPException(status_code=502, detail="Error procesando la solicitud") from e
    return RespuestaChat(
        conversacion_id=conv_id,
        respuesta=resultado.respuesta_al_cliente,
        datos=resultado,
    )


@app.post("/whatsapp", dependencies=[Depends(verificar_twilio)])
def whatsapp_webhook(
    background_tasks: BackgroundTasks,
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
        _, resultado = _procesar_mensaje(db, telefono, Body, background_tasks)
        respuesta_texto = resultado.respuesta_al_cliente
    except Exception:
        logger.exception("Error procesando /whatsapp para %s", telefono)
        respuesta_texto = "Hubo un problema procesando tu mensaje. Por favor intentá de nuevo en unos minutos."

    twiml = f"<Response><Message>{xml_escape(respuesta_texto)}</Message></Response>"
    return Response(content=twiml, media_type="application/xml")
