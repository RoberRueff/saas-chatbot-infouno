"""Tests de la validación de firma de Twilio.

Requieren `fastapi` y `twilio` instalados (a diferencia de los tests de `ia/`),
así que corren dentro del venv del proyecto:

    pytest seguridad/tests/
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

# Raíz del proyecto al path para importar el paquete `seguridad`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

pytest.importorskip("fastapi")
pytest.importorskip("twilio")

from fastapi import HTTPException
from twilio.request_validator import RequestValidator

from seguridad.twilio import _url_publica, verificar_twilio


# ---------------------------------------------------------------------------
# Dobles de prueba (duck-typing del Request de Starlette)
# ---------------------------------------------------------------------------

class FakeURL:
    def __init__(self, scheme="http", netloc="localhost:8000", path="/whatsapp", query=""):
        self.scheme = scheme
        self.netloc = netloc
        self.path = path
        self.query = query


class FakeRequest:
    def __init__(self, headers, url, form_data):
        self.headers = headers
        self.url = url
        self._form = form_data

    async def form(self):
        return self._form


# ---------------------------------------------------------------------------
# _url_publica
# ---------------------------------------------------------------------------

def test_url_publica_usa_override(monkeypatch):
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", "https://x.ngrok.app/whatsapp")
    assert _url_publica(FakeRequest({}, FakeURL(), {})) == "https://x.ngrok.app/whatsapp"


def test_url_publica_reconstruye_con_proxy(monkeypatch):
    monkeypatch.delenv("TWILIO_WEBHOOK_URL", raising=False)
    req = FakeRequest({"X-Forwarded-Proto": "https", "Host": "abc.ngrok.app"}, FakeURL(), {})
    assert _url_publica(req) == "https://abc.ngrok.app/whatsapp"


# ---------------------------------------------------------------------------
# verificar_twilio
# ---------------------------------------------------------------------------

def test_sin_token_no_valida(monkeypatch):
    # Modo desarrollo: sin token, deja pasar (no lanza).
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    asyncio.run(verificar_twilio(FakeRequest({}, FakeURL(), {})))


def test_firma_valida_pasa(monkeypatch):
    token = "test_token_123"
    url = "https://abc.ngrok.app/whatsapp"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", url)
    params = {"From": "whatsapp:+5491100000000", "Body": "hola"}
    firma = RequestValidator(token).compute_signature(url, params)
    req = FakeRequest({"X-Twilio-Signature": firma}, FakeURL(), params)
    asyncio.run(verificar_twilio(req))  # no debe lanzar


def test_firma_invalida_rechaza_con_403(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_token_123")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", "https://abc.ngrok.app/whatsapp")
    params = {"From": "whatsapp:+5491100000000", "Body": "hola"}
    req = FakeRequest({"X-Twilio-Signature": "firma_falsa"}, FakeURL(), params)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verificar_twilio(req))
    assert exc.value.status_code == 403
