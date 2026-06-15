"""Tests de la ventana de inactividad de conversaciones (SQLite en memoria)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import (
    Base,
    guardar_mensaje,
    obtener_o_crear_conversacion,
    reclamar_derivacion,
)

TEL = "+5491150000099"


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_reutiliza_dentro_de_ventana():
    # Conversación recién creada (sin mensajes): un mensaje 1 h después la reutiliza.
    with _db() as db:
        conv1 = obtener_o_crear_conversacion(db, TEL)
        ahora = datetime.now(timezone.utc) + timedelta(hours=1)
        conv2 = obtener_o_crear_conversacion(db, TEL, ahora=ahora)
        assert conv2.id == conv1.id


def test_crea_nueva_pasada_la_ventana():
    # Conversación vacía y vieja (>24 h): se crea una nueva con derivada=False.
    with _db() as db:
        conv1 = obtener_o_crear_conversacion(db, TEL)
        ahora = datetime.now(timezone.utc) + timedelta(hours=25)
        conv2 = obtener_o_crear_conversacion(db, TEL, ahora=ahora)
        assert conv2.id != conv1.id
        assert conv2.derivada is False


def test_reutiliza_segun_ultimo_mensaje():
    # La ventana se mide desde el ÚLTIMO mensaje, no desde la creación.
    with _db() as db:
        conv1 = obtener_o_crear_conversacion(db, TEL)
        guardar_mensaje(db, conv1.id, "user", "hola")
        ahora = datetime.now(timezone.utc) + timedelta(hours=23)
        conv2 = obtener_o_crear_conversacion(db, TEL, ahora=ahora)
        assert conv2.id == conv1.id


def test_cliente_derivado_que_vuelve_se_puede_rederivar():
    # Bug original: cliente derivado que vuelve pasada la ventana arranca
    # conversación nueva con derivada=False (vuelve a poder derivarse).
    with _db() as db:
        conv1 = obtener_o_crear_conversacion(db, TEL)
        assert reclamar_derivacion(db, conv1.id) is True
        ahora = datetime.now(timezone.utc) + timedelta(hours=25)
        conv2 = obtener_o_crear_conversacion(db, TEL, ahora=ahora)
        assert conv2.id != conv1.id
        assert conv2.derivada is False


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
