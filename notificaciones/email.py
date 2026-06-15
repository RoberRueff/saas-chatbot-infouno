"""Notificación por email al derivar un caso. Fachada que usa main.py.

`enviar_aviso_derivacion` arma el mail, resuelve el departamento destino y delega
el envío en un `sender` inyectable. Nunca propaga excepciones: si algo falla,
loguea y devuelve False (el cliente igual recibe su respuesta por WhatsApp).
"""
from __future__ import annotations

import logging

from notificaciones.config import NotifConfig, cargar_config
from notificaciones.sender import enviar_smtp

logger = logging.getLogger("chatbot.notificaciones")


def _categoria_str(resultado) -> str:
    """Acepta un enum (str, Enum) o un string y devuelve siempre el string."""
    cat = getattr(resultado, "categoria", None)
    return getattr(cat, "value", cat)


def construir_asunto(resultado, telefono: str) -> str:
    quien = getattr(resultado, "nombre_empresa", None) or telefono
    return f"[infouno] {_categoria_str(resultado)}: {quien}"


def construir_cuerpo(resultado, telefono: str) -> str:
    g = lambda campo: getattr(resultado, campo, None) or "-"
    return "\n".join([
        "Nuevo caso derivado desde el chatbot de WhatsApp.",
        "",
        f"Departamento: {_categoria_str(resultado)}",
        f"Empresa: {g('nombre_empresa')}",
        f"Rubro: {g('rubro')}",
        f"Línea de servicio: {g('linea_servicio')}",
        f"Necesidad: {g('necesidad')}",
        f"Ubicación: {g('ubicacion')}",
        f"Teléfono del cliente: {telefono}",
    ])
