"""Validación de la firma de los webhooks de Twilio.

Twilio firma cada webhook con HMAC-SHA1 usando tu `TWILIO_AUTH_TOKEN`, la URL
exacta del request y los parámetros del form, y la envía en el header
`X-Twilio-Signature`. Acá recalculamos esa firma y la comparamos: si no coincide,
el request no vino de Twilio y se rechaza con 403 (antes de gastar Gemini o
escribir en la BD). Es el control que evita que un tercero abuse del webhook
público y te infle los costos.
"""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Request
from twilio.request_validator import RequestValidator

logger = logging.getLogger("chatbot.twilio")


def _url_publica(request: Request) -> str:
    """Devuelve la URL que Twilio usó para firmar el request.

    Detrás de ngrok / un proxy, el request interno llega como
    ``http://localhost:8000/...`` pero Twilio firmó con la URL pública
    ``https://<sub>.ngrok.../whatsapp``. Por eso:

    1. Si ``TWILIO_WEBHOOK_URL`` está seteada, se usa tal cual (override exacto).
    2. Si no, se reconstruye respetando los headers de proxy
       (``X-Forwarded-Proto`` y ``Host``), que ngrok completa.
    """
    override = os.getenv("TWILIO_WEBHOOK_URL")
    if override:
        return override

    proto = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    host = request.headers.get("Host") or request.url.netloc
    url = f"{proto}://{host}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


async def verificar_twilio(request: Request) -> None:
    """Dependencia de FastAPI que valida la firma del webhook de Twilio.

    - Sin ``TWILIO_AUTH_TOKEN`` configurado: NO valida (modo desarrollo), solo
      registra un aviso. Permite probar en local sin fricción.
    - Con token: si la firma falta o no coincide, corta con 403 y no llega al handler.
    """
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not token:
        logger.warning(
            "TWILIO_AUTH_TOKEN no configurado — validación de firma DESACTIVADA (modo dev)"
        )
        return

    firma = request.headers.get("X-Twilio-Signature", "")
    url = _url_publica(request)
    form = await request.form()
    params = {clave: valor for clave, valor in form.items()}

    validator = RequestValidator(token)
    if not validator.validate(url, params, firma):
        logger.warning("Firma de Twilio INVÁLIDA — request rechazado (url=%s)", url)
        raise HTTPException(status_code=403, detail="Firma de Twilio inválida")
