"""Tests del aviso de privacidad (art. 6) en el primer turno de cada conversación."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import main
from ia import rate_limit
from database import Base

TEL = "+5491150000055"


def _resultado(**kw):
    base = dict(
        categoria=main.Categoria.comercial,
        respuesta_al_cliente="Hola, contame en qué te ayudo.",
        notificar_recepcion=False,
        solicita_humano=False,
    )
    base.update(kw)
    return main.RespuestaChatbot(**base)


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_primer_mensaje_incluye_aviso():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda h, t: _resultado()
        with _db() as db:
            _, res = main._procesar_mensaje(db, TEL, "hola", None)
            assert res is not None
            assert main.MSG_AVISO_PRIVACIDAD in res.respuesta_al_cliente
    finally:
        main._llamar_gemini = original


def test_segundo_mensaje_no_incluye_aviso():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda h, t: _resultado()
        with _db() as db:
            main._procesar_mensaje(db, TEL, "hola", None)            # primer turno
            _, res2 = main._procesar_mensaje(db, TEL, "otra cosa", None)  # segundo turno
            assert res2 is not None
            assert main.MSG_AVISO_PRIVACIDAD not in res2.respuesta_al_cliente
    finally:
        main._llamar_gemini = original


def test_escalamiento_primer_turno_incluye_aviso():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda h, t: _resultado(solicita_humano=True)
        with _db() as db:
            _, res = main._procesar_mensaje(db, TEL, "quiero hablar con alguien", None)
            assert res is not None
            assert main.MSG_ESCALAMIENTO_HUMANO in res.respuesta_al_cliente
            assert main.MSG_AVISO_PRIVACIDAD in res.respuesta_al_cliente
    finally:
        main._llamar_gemini = original


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
