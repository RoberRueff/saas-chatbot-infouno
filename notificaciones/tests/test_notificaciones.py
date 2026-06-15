"""Tests del módulo de notificaciones.

Solo dependen de la stdlib (no de FastAPI/Gemini/pydantic), así que corren sin
instalar las dependencias del proyecto:

    .venv/bin/python notificaciones/tests/test_notificaciones.py
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from notificaciones.config import NotifConfig


def _config(**over):
    base = dict(
        smtp_host="mail.infouno.com.ar",
        smtp_port=465,
        smtp_user="bot@infouno.com.ar",
        smtp_password="secreta",
        email_from="bot@infouno.com.ar",
        destinos={
            "Comercial/Ventas": "ventas@infouno.com.ar",
            "Administración": "administracion@infouno.com.ar",
            "Servicio Técnico": "servicio.tecnico@infouno.com.ar",
        },
    )
    base.update(over)
    return NotifConfig(**base)


def test_destino_por_categoria():
    c = _config()
    assert c.destino_para("Comercial/Ventas") == "ventas@infouno.com.ar"
    assert c.destino_para("Administración") == "administracion@infouno.com.ar"
    assert c.destino_para("Servicio Técnico") == "servicio.tecnico@infouno.com.ar"


def test_destino_desconocido_es_none():
    c = _config()
    assert c.destino_para("Desconocido") is None
    assert c.destino_para("Cualquier Cosa") is None


def test_activo_segun_password():
    assert _config(smtp_password="x").activo is True
    assert _config(smtp_password="").activo is False


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
