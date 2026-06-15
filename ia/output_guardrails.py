"""Guardrail de salida: red de seguridad sobre las reglas de negocio.

Verifica que la respuesta del bot no incluya precios/cotizaciones (regla #1).
Es una segunda barrera por si el modelo se desvía del system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from ia.config import PATRONES_PROHIBIDOS_SALIDA


@dataclass
class ResultadoSalida:
    permitido: bool
    motivo: str | None = None  # "precio" | None


def revisar_salida(respuesta: str) -> ResultadoSalida:
    """Revisa la respuesta generada. Si viola una regla, devuelve el motivo."""
    bajo = (respuesta or "").lower()
    for motivo, patron in PATRONES_PROHIBIDOS_SALIDA:
        if patron.search(bajo):
            return ResultadoSalida(False, motivo)
    return ResultadoSalida(True)
