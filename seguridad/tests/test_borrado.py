"""Tests del endpoint de borrado a pedido (/admin/borrar-datos)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

import main

_BODY = {"telefono": "+5491100000000"}


def test_borrar_sin_api_key_rechaza():
    os.environ["APP_SECRET_KEY"] = "secreto-test"
    with TestClient(main.app) as client:
        r = client.post("/admin/borrar-datos", json=_BODY)
        assert r.status_code == 401, r.status_code


def test_borrar_con_api_key_borra():
    os.environ["APP_SECRET_KEY"] = "secreto-test"
    original = main.borrar_datos_telefono
    try:
        capturado = {}

        def _fake(db, telefono):
            capturado["telefono"] = telefono
            return 3

        main.borrar_datos_telefono = _fake
        with TestClient(main.app) as client:
            r = client.post("/admin/borrar-datos", json=_BODY, headers={"X-API-Key": "secreto-test"})
            assert r.status_code == 200, r.status_code
            cuerpo = r.json()
            assert cuerpo["conversaciones_borradas"] == 3
            assert cuerpo["telefono"] == "+5491100000000"
            assert capturado["telefono"] == "+5491100000000"
    finally:
        main.borrar_datos_telefono = original


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
