"""Guardrails de entrada: validación del mensaje y detección de prompt injection."""

from __future__ import annotations

from dataclasses import dataclass

from ia.config import MAX_LONGITUD_MENSAJE, PATRONES_INJECTION


@dataclass
class ResultadoEntrada:
    permitido: bool
    motivo: str | None = None  # "vacio" | "muy_largo" | "injection" | None


def validar_entrada(texto: str) -> ResultadoEntrada:
    """Valida un mensaje del cliente antes de mandarlo al modelo."""
    limpio = (texto or "").strip()
    if not limpio:
        return ResultadoEntrada(False, "vacio")
    if len(limpio) > MAX_LONGITUD_MENSAJE:
        return ResultadoEntrada(False, "muy_largo")
    if _es_injection(limpio):
        return ResultadoEntrada(False, "injection")
    return ResultadoEntrada(True)


def _es_injection(texto: str) -> bool:
    bajo = texto.lower()
    return any(patron.search(bajo) for patron in PATRONES_INJECTION)
