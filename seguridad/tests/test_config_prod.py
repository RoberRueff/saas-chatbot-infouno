"""Test de la guarda de configuración de producción (fail-fast)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import main

_VARS = ("APP_ENV", "APP_SECRET_KEY", "TWILIO_AUTH_TOKEN", "GEMINI_API_KEY")


def _con_entorno(**valores):
    """Devuelve (aplicar, restaurar): aplicar setea `valores` y borra el resto de
    _VARS; restaurar deja os.environ como estaba."""
    previo = {k: os.environ.get(k) for k in _VARS}

    def aplicar():
        for k in _VARS:
            os.environ.pop(k, None)
        for k, v in valores.items():
            os.environ[k] = v

    def restaurar():
        for k, v in previo.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return aplicar, restaurar


def test_dev_no_lanza_aunque_falten_secretos():
    aplicar, restaurar = _con_entorno(APP_ENV="development")
    try:
        aplicar()
        main._validar_config_produccion()  # no debe lanzar
    finally:
        restaurar()


def test_prod_lanza_si_falta_un_secreto():
    # Falta TWILIO_AUTH_TOKEN.
    aplicar, restaurar = _con_entorno(
        APP_ENV="production", APP_SECRET_KEY="x", GEMINI_API_KEY="y"
    )
    try:
        aplicar()
        lanzo = False
        try:
            main._validar_config_produccion()
        except RuntimeError as e:
            lanzo = True
            assert "TWILIO_AUTH_TOKEN" in str(e), str(e)
        assert lanzo, "esperaba RuntimeError por secreto faltante"
    finally:
        restaurar()


def test_prod_no_lanza_si_estan_todos():
    aplicar, restaurar = _con_entorno(
        APP_ENV="production",
        APP_SECRET_KEY="x",
        TWILIO_AUTH_TOKEN="y",
        GEMINI_API_KEY="z",
    )
    try:
        aplicar()
        main._validar_config_produccion()  # no debe lanzar
    finally:
        restaurar()


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
