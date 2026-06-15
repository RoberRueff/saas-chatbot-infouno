"""Test del comportamiento fail-closed de la validación Twilio en production."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import HTTPException

from seguridad.twilio import verificar_twilio


def test_production_sin_token_rechaza():
    os.environ["APP_ENV"] = "production"
    os.environ.pop("TWILIO_AUTH_TOKEN", None)
    try:
        asyncio.run(verificar_twilio(None))  # type: ignore[arg-type]
        raise AssertionError("debería haber rechazado con 503")
    except HTTPException as e:
        assert e.status_code == 503, e.status_code


def test_development_sin_token_permite():
    os.environ["APP_ENV"] = "development"
    os.environ.pop("TWILIO_AUTH_TOKEN", None)
    # En dev, sin token, NO valida (no debe lanzar).
    asyncio.run(verificar_twilio(None))  # type: ignore[arg-type]


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fallos = 0
    for fn in funcs:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            fallos += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    total = len(funcs)
    print(f"\n{total - fallos}/{total} tests pasaron")
    sys.exit(1 if fallos else 0)
