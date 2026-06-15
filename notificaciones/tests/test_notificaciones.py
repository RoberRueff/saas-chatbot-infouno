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
from notificaciones.email import construir_asunto, construir_cuerpo, enviar_aviso_derivacion


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


def _resultado(**over):
    base = dict(
        categoria="Comercial/Ventas",
        nombre_empresa="ModaSur",
        rubro="indumentaria",
        linea_servicio="Desarrollo Web",
        necesidad="tienda online",
        ubicacion="Rosario",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_asunto_incluye_categoria_y_empresa():
    asunto = construir_asunto(_resultado(), "+5491150000010")
    assert "Comercial/Ventas" in asunto
    assert "ModaSur" in asunto


def test_asunto_usa_telefono_si_no_hay_empresa():
    asunto = construir_asunto(_resultado(nombre_empresa=None), "+5491150000010")
    assert "+5491150000010" in asunto


def test_cuerpo_incluye_los_datos_del_caso():
    cuerpo = construir_cuerpo(_resultado(), "+5491150000010")
    for esperado in ["Comercial/Ventas", "ModaSur", "indumentaria",
                     "Desarrollo Web", "tienda online", "Rosario", "+5491150000010"]:
        assert esperado in cuerpo, f"falta en el cuerpo: {esperado}"


def test_cuerpo_tolera_campos_vacios():
    cuerpo = construir_cuerpo(_resultado(nombre_empresa=None, rubro=None,
                                         linea_servicio=None), "+5491150000010")
    assert "-" in cuerpo  # los campos faltantes se muestran como "-"


def _sender_espia(registro):
    def _sender(config, destino, asunto, cuerpo):
        registro.append((destino, asunto, cuerpo))
    return _sender


def test_envia_al_destino_correcto():
    enviados = []
    ok = enviar_aviso_derivacion(
        _resultado(categoria="Servicio Técnico"), "+5491150000010",
        config=_config(), sender=_sender_espia(enviados),
    )
    assert ok is True
    assert len(enviados) == 1
    assert enviados[0][0] == "servicio.tecnico@infouno.com.ar"


def test_no_envia_si_esta_desactivado():
    enviados = []
    ok = enviar_aviso_derivacion(
        _resultado(), "+549115", config=_config(smtp_password=""),
        sender=_sender_espia(enviados),
    )
    assert ok is False
    assert enviados == []


def test_no_envia_si_categoria_sin_destino():
    enviados = []
    ok = enviar_aviso_derivacion(
        _resultado(categoria="Desconocido"), "+549115",
        config=_config(), sender=_sender_espia(enviados),
    )
    assert ok is False
    assert enviados == []


def test_falla_del_sender_no_propaga_y_devuelve_false():
    def _sender_explota(config, destino, asunto, cuerpo):
        raise RuntimeError("SMTP caído")
    ok = enviar_aviso_derivacion(
        _resultado(), "+549115", config=_config(), sender=_sender_explota,
    )
    assert ok is False


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
