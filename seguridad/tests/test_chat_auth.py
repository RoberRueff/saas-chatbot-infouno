"""Tests de auth y manejo de error del endpoint /chat.

Requieren fastapi + httpx instalados (vienen con el proyecto):
    .venv/bin/python seguridad/tests/test_chat_auth.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Fijar la API key ANTES de importar main (load_dotenv no pisa una env var ya seteada).
os.environ["APP_SECRET_KEY"] = "test-secret-123"

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_BODY = {"telefono_cliente": "+5491150000000", "mensaje": "hola"}
_HEAD_OK = {"X-API-Key": "test-secret-123"}


def test_chat_sin_api_key_rechaza():
    with TestClient(main.app) as client:
        r = client.post("/chat", json=_BODY)
        assert r.status_code == 401, r.status_code


def test_chat_con_api_key_incorrecta_rechaza():
    with TestClient(main.app) as client:
        r = client.post("/chat", json=_BODY, headers={"X-API-Key": "incorrecta"})
        assert r.status_code == 401, r.status_code


def test_chat_con_api_key_correcta_pasa():
    main._procesar_mensaje = lambda db, tel, txt: (1, main._respuesta_bloqueada("ok"))
    with TestClient(main.app) as client:
        r = client.post("/chat", json=_BODY, headers=_HEAD_OK)
        assert r.status_code == 200, r.status_code


def test_chat_no_filtra_el_error_interno():
    def _boom(db, tel, txt):
        raise RuntimeError("SECRETO-INTERNO-12345")
    main._procesar_mensaje = _boom
    with TestClient(main.app) as client:
        r = client.post("/chat", json=_BODY, headers=_HEAD_OK)
        assert r.status_code == 502, r.status_code
        assert "SECRETO-INTERNO-12345" not in r.text, "el endpoint filtró el error interno"


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
