"""Config de las notificaciones por email.

Lee todo de variables de entorno (cargadas por `load_dotenv()` en main.py) y no
depende de FastAPI/Gemini, así que el módulo se puede testear con la stdlib.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class NotifConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    destinos: dict[str, str]  # categoria.value -> email del departamento

    def destino_para(self, categoria: str) -> str | None:
        """Email del departamento para una categoría, o None si no hay ruteo."""
        return self.destinos.get(categoria) or None

    @property
    def activo(self) -> bool:
        """La notificación está activa solo si hay contraseña SMTP configurada."""
        return bool(self.smtp_password)


def cargar_config() -> NotifConfig:
    """Construye la config desde el entorno (con defaults razonables)."""
    user = os.getenv("SMTP_USER", "")
    return NotifConfig(
        smtp_host=os.getenv("SMTP_HOST", "mail.infouno.com.ar"),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
        smtp_user=user,
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_from=os.getenv("NOTIF_EMAIL_FROM", user),
        destinos={
            "Comercial/Ventas": os.getenv("NOTIF_EMAIL_VENTAS", ""),
            "Administración": os.getenv("NOTIF_EMAIL_ADMIN", ""),
            "Servicio Técnico": os.getenv("NOTIF_EMAIL_SOPORTE", ""),
        },
    )
