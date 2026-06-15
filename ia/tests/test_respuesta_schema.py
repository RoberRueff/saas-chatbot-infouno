"""Tests del schema RespuestaChatbot: el campo solicita_humano."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import main


def test_solicita_humano_default_false():
    r = main.RespuestaChatbot(
        categoria=main.Categoria.comercial,
        respuesta_al_cliente="hola",
        notificar_recepcion=False,
    )
    assert r.solicita_humano is False


def test_solicita_humano_se_parsea_true():
    r = main.RespuestaChatbot(
        categoria=main.Categoria.desconocido,
        respuesta_al_cliente="ok",
        notificar_recepcion=False,
        solicita_humano=True,
    )
    assert r.solicita_humano is True


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
