"""Tests del endpoint de borrado a pedido (/admin/borrar-datos)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

import main

_BODY = {"telefono": "+5491100000000"}


def _restaurar_secret(prev):
    if prev is None:
        os.environ.pop("APP_SECRET_KEY", None)
    else:
        os.environ["APP_SECRET_KEY"] = prev


def test_borrar_sin_api_key_rechaza():
    prev = os.environ.get("APP_SECRET_KEY")
    os.environ["APP_SECRET_KEY"] = "secreto-test"
    try:
        with TestClient(main.app) as client:
            r = client.post("/admin/borrar-datos", json=_BODY)
            assert r.status_code == 401, r.status_code
    finally:
        _restaurar_secret(prev)


def test_borrar_con_api_key_borra():
    prev = os.environ.get("APP_SECRET_KEY")
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
        _restaurar_secret(prev)


def test_app_arranca_con_purga_y_responde_root():
    # Arrancar el lifespan (que ahora corre la purga inicial) no debe romper.
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200


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
