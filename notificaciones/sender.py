"""Adapter SMTP: capa fina sobre smtplib. El resto del módulo no toca la red.

Usa SMTP_SSL (puerto 465) contra el servidor propio de infouno. Lanza si el
envío falla; quien llama (`enviar_aviso_derivacion`) captura el error.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from notificaciones.config import NotifConfig


def enviar_smtp(config: NotifConfig, destino: str, asunto: str, cuerpo: str) -> None:
    msg = EmailMessage()
    msg["From"] = config.email_from
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.set_content(cuerpo)

    with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15) as smtp:
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(msg)
