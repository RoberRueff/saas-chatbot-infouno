"""Fachada de guardrails: única puerta que usa el resto de la app.

Orquesta los controles de entrada (rate limit -> validación -> anti-injection) y
el de salida (reglas de negocio). El resto del código no debería importar los
submódulos directamente, solo este.
"""

from __future__ import annotations

from dataclasses import dataclass

from ia import rate_limit
from ia.config import (
    MSG_BLOQUEO_INJECTION,
    MSG_ENTRADA_INVALIDA,
    MSG_RATE_LIMIT,
    MSG_SALIDA_SANITIZADA,
)
from ia.input_guardrails import validar_entrada
from ia.output_guardrails import revisar_salida


@dataclass
class VeredictoEntrada:
    permitido: bool
    motivo: str | None = None          # "rate_limit" | "vacio" | "muy_largo" | "injection"
    respuesta_fija: str | None = None  # texto a devolver al cliente si está bloqueado


def revisar_entrada(telefono: str, texto: str) -> VeredictoEntrada:
    """Aplica, en orden, rate limit -> validación -> anti-injection.

    Devuelve un veredicto. Si `permitido` es False, `respuesta_fija` trae el
    mensaje neutro que hay que enviarle al cliente (sin llamar al modelo).
    """
    if not rate_limit.permitido(telefono):
        return VeredictoEntrada(False, "rate_limit", MSG_RATE_LIMIT)

    resultado = validar_entrada(texto)
    if not resultado.permitido:
        if resultado.motivo == "injection":
            return VeredictoEntrada(False, "injection", MSG_BLOQUEO_INJECTION)
        return VeredictoEntrada(False, resultado.motivo, MSG_ENTRADA_INVALIDA)

    return VeredictoEntrada(True)


def sanitizar_salida(respuesta: str) -> tuple[str, str | None]:
    """Revisa la respuesta del modelo.

    Devuelve (texto_final, motivo). Si se detectó una violación, `texto_final`
    es un mensaje seguro y `motivo` indica qué se filtró ("precio").
    Si está limpia, devuelve la respuesta original y motivo None.
    """
    resultado = revisar_salida(respuesta)
    if not resultado.permitido:
        return MSG_SALIDA_SANITIZADA, resultado.motivo
    return respuesta, None
