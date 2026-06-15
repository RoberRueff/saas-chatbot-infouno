"""Tests de _llamar_gemini: fallback grácil cuando el modelo no devuelve texto."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import main


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.candidates = []


class _FakeModels:
    def __init__(self, resp):
        self._resp = resp

    def generate_content(self, **kwargs):
        return self._resp


class _FakeClient:
    def __init__(self, resp):
        self.models = _FakeModels(resp)


def _con_cliente(text):
    return _FakeClient(_FakeResp(text))


def test_devuelve_respuesta_parseada_si_hay_texto():
    original = main.gemini_client
    try:
        payload = json.dumps({
            "categoria": "Comercial/Ventas",
            "respuesta_al_cliente": "Hola, contame en qué te puedo ayudar.",
            "notificar_recepcion": False,
        })
        main.gemini_client = _con_cliente(payload)
        r = main._llamar_gemini([], "quiero automatizar mi local")
        assert r.categoria == main.Categoria.comercial
        assert r.respuesta_al_cliente == "Hola, contame en qué te puedo ayudar."
        assert r.notificar_recepcion is False
    finally:
        main.gemini_client = original


def test_fallback_si_text_es_none():
    original = main.gemini_client
    try:
        main.gemini_client = _con_cliente(None)
        r = main._llamar_gemini([], "hola")
        assert r.categoria == main.Categoria.desconocido
        assert r.notificar_recepcion is False
        assert r.respuesta_al_cliente == main.MSG_IA_SIN_RESPUESTA
    finally:
        main.gemini_client = original


def test_fallback_si_text_es_vacio():
    original = main.gemini_client
    try:
        main.gemini_client = _con_cliente("")
        r = main._llamar_gemini([], "hola")
        assert r.categoria == main.Categoria.desconocido
        assert r.respuesta_al_cliente == main.MSG_IA_SIN_RESPUESTA
    finally:
        main.gemini_client = original


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
