"""Tests de la marca de modo humano y de la búsqueda sin filtro de estado."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import (
    Base,
    marcar_estado_humano,
    obtener_o_crear_conversacion,
)

TEL = "+5491150000077"


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_marcar_estado_humano_es_atomico_e_idempotente():
    with _db() as db:
        conv = obtener_o_crear_conversacion(db, TEL)
        assert marcar_estado_humano(db, conv.id) is True   # gana el primero
        assert marcar_estado_humano(db, conv.id) is False  # ya estaba marcada
        refrescada = obtener_o_crear_conversacion(db, TEL)
        assert refrescada.estado_humano is True


def test_obtener_devuelve_conversacion_aunque_este_en_modo_humano():
    # La búsqueda ya NO filtra por estado_humano: dentro de la ventana, devuelve
    # la misma conversación (para que el caller pueda callar al bot).
    with _db() as db:
        conv = obtener_o_crear_conversacion(db, TEL)
        marcar_estado_humano(db, conv.id)
        misma = obtener_o_crear_conversacion(db, TEL)
        assert misma.id == conv.id
        assert misma.estado_humano is True


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fallos = 0
    for fn in funcs:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"  FAIL {fn.__name__}: {type(e).__name__}: {e}")
    total = len(funcs)
    print(f"\n{total - fallos}/{total} tests pasaron")
    sys.exit(1 if fallos else 0)
