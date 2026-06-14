"""Rate limiting por teléfono con ventana deslizante en memoria.

Sirve para el MVP de 1 solo proceso (uvicorn). En un despliegue multi-proceso
o multi-instancia, este estado en memoria NO se comparte: habría que moverlo a
una store compartida (Redis o la propia BD).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from ia.config import RATE_LIMIT_MAX_MENSAJES, RATE_LIMIT_VENTANA_SEG

# teléfono -> deque de timestamps (monotónicos) de los mensajes recientes
_eventos: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def permitido(telefono: str, ahora: float | None = None) -> bool:
    """Devuelve True si el teléfono puede enviar otro mensaje ahora.

    Si lo permite, registra el evento. `ahora` es inyectable para tests.
    Thread-safe: los endpoints corren en el threadpool de FastAPI.
    """
    instante = time.monotonic() if ahora is None else ahora
    corte = instante - RATE_LIMIT_VENTANA_SEG
    with _lock:
        cola = _eventos[telefono]
        while cola and cola[0] < corte:
            cola.popleft()
        if len(cola) >= RATE_LIMIT_MAX_MENSAJES:
            return False
        cola.append(instante)
        return True


def reset() -> None:
    """Limpia todo el estado. Pensado para tests."""
    with _lock:
        _eventos.clear()
