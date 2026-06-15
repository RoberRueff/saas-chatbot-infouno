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


def construir_cuerpo(resultado, telefono: str, *,
                     intro: str = "Nuevo caso derivado desde el chatbot de WhatsApp.") -> str:
    g = lambda campo: getattr(resultado, campo, None) or "-"
    return "\n".join([
        intro,
        "",
        f"Departamento: {_categoria_str(resultado)}",
        f"Empresa: {g('nombre_empresa')}",
        f"Rubro: {g('rubro')}",
        f"Línea de servicio: {g('linea_servicio')}",
        f"Necesidad: {g('necesidad')}",
        f"Ubicación: {g('ubicacion')}",
        f"Teléfono del cliente: {telefono}",
    ])


def enviar_aviso_derivacion(resultado, telefono: str, *,
                            config: NotifConfig | None = None,
                            sender=enviar_smtp) -> bool:
    """Envía el aviso de derivación al departamento que corresponde.

    Devuelve True solo si el mail se envió OK. Nunca lanza: ante cualquier
    problema (desactivado, sin destino, error de envío) loguea y devuelve False.
    """
    config = config or cargar_config()
    if not config.activo:
        logger.warning("Notificación por email DESACTIVADA (SMTP_PASSWORD vacío) — no se envía")
        return False

    destino = config.destino_para(_categoria_str(resultado))
    if not destino:
        logger.info("Sin destino para la categoría '%s' — no se envía", _categoria_str(resultado))
        return False

    try:
        sender(config, destino, construir_asunto(resultado, telefono),
               construir_cuerpo(resultado, telefono))
        logger.info("Aviso de derivación enviado a %s", destino)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Falló el envío del aviso de derivación a %s", destino)
        return False


def construir_asunto_escalamiento(resultado, telefono: str) -> str:
    quien = getattr(resultado, "nombre_empresa", None) or telefono
    return f"[infouno] PIDE HUMANO: {quien}"


def _destino_escalamiento(config: NotifConfig, categoria: str) -> str | None:
    """Ruteo por categoría; si no hay, fallback a Ventas y luego al primer destino."""
    return (
        config.destino_para(categoria)
        or config.destinos.get("Comercial/Ventas")
        or next((d for d in config.destinos.values() if d), None)
    )


def enviar_aviso_escalamiento(resultado, telefono: str, *,
                              config: NotifConfig | None = None,
                              sender=enviar_smtp) -> bool:
    """Avisa al equipo que el cliente pidió hablar con una persona.

    Devuelve True solo si el mail se envió OK. Nunca lanza: ante cualquier
    problema loguea y devuelve False (best-effort; el modo humano ya quedó marcado).
    """
    config = config or cargar_config()
    if not config.activo:
        logger.warning("Notificación por email DESACTIVADA (SMTP_PASSWORD vacío) — no se envía escalamiento")
        return False

    destino = _destino_escalamiento(config, _categoria_str(resultado))
    if not destino:
        logger.info("Sin destino para escalamiento — no se envía")
        return False

    try:
        sender(config, destino, construir_asunto_escalamiento(resultado, telefono),
               construir_cuerpo(resultado, telefono,
                                intro="El cliente pidió hablar con una persona (chatbot de WhatsApp)."))
        logger.info("Aviso de escalamiento enviado a %s", destino)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Falló el envío del aviso de escalamiento a %s", destino)
        return False
