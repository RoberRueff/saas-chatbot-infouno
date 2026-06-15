"""Tests de integración del handoff a humano (_procesar_mensaje + endpoints)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import main
from ia import rate_limit
from database import Base, obtener_o_crear_conversacion

TEL = "+5491150000088"


def _resultado(**kw):
    base = dict(
        categoria=main.Categoria.comercial,
        respuesta_al_cliente="hola",
        notificar_recepcion=False,
        solicita_humano=False,
    )
    base.update(kw)
    return main.RespuestaChatbot(**base)


class _BG:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *a, **k):
        self.tasks.append((fn, a, k))


def _nuevo_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_handoff_marca_humano_responde_fijo_y_agenda_email():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda hist, txt: _resultado(solicita_humano=True)
        with _nuevo_db() as db:
            bg = _BG()
            cid, res = main._procesar_mensaje(db, TEL, "quiero hablar con alguien", bg)
            assert res is not None
            assert res.respuesta_al_cliente == main.MSG_ESCALAMIENTO_HUMANO
            conv = obtener_o_crear_conversacion(db, TEL)
            assert conv.id == cid
            assert conv.estado_humano is True
            assert any(fn is main._escalar_en_background for fn, _, _ in bg.tasks)
    finally:
        main._llamar_gemini = original


def test_modo_humano_silencio_no_llama_gemini_y_persiste():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda hist, txt: _resultado(solicita_humano=True)
        with _nuevo_db() as db:
            bg = _BG()
            cid, _ = main._procesar_mensaje(db, TEL, "quiero un humano", bg)

            def _boom(hist, txt):
                raise AssertionError("no debe llamar a Gemini en modo humano")

            main._llamar_gemini = _boom
            cid2, res2 = main._procesar_mensaje(db, TEL, "otra cosa", bg)
            assert cid2 == cid
            assert res2 is None
            conv = obtener_o_crear_conversacion(db, TEL)
            assert "otra cosa" in [m.contenido for m in conv.mensajes]
    finally:
        main._llamar_gemini = original


def test_whatsapp_en_modo_humano_devuelve_twiml_vacio():
    # Endpoint: si _procesar_mensaje devuelve respuesta None, TwiML sin <Message>.
    os.environ.pop("TWILIO_AUTH_TOKEN", None)
    os.environ["APP_ENV"] = "development"
    os.environ["GEMINI_API_KEY"] = "x"  # para pasar el check de _ia_configurada
    original = main._procesar_mensaje
    try:
        main._procesar_mensaje = lambda db, tel, txt, bg=None: (1, None)
        with TestClient(main.app) as client:
            r = client.post("/whatsapp", data={"From": "whatsapp:+5491100000000", "Body": "hola"})
            assert r.status_code == 200
            assert r.text == "<Response></Response>"
    finally:
        main._procesar_mensaje = original
        os.environ.pop("GEMINI_API_KEY", None)


def test_chat_en_modo_humano_devuelve_respuesta_vacia():
    os.environ["APP_SECRET_KEY"] = "secreto-test"
    os.environ["GEMINI_API_KEY"] = "x"
    original = main._procesar_mensaje
    try:
        main._procesar_mensaje = lambda db, tel, txt, bg=None: (7, None)
        with TestClient(main.app) as client:
            r = client.post(
                "/chat",
                json={"telefono_cliente": "+5491100000000", "mensaje": "hola"},
                headers={"X-API-Key": "secreto-test"},
            )
            assert r.status_code == 200, r.status_code
            cuerpo = r.json()
            assert cuerpo["respuesta"] == ""
            assert cuerpo["datos"] is None
            assert cuerpo["conversacion_id"] == 7
    finally:
        main._procesar_mensaje = original
        os.environ.pop("GEMINI_API_KEY", None)


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
