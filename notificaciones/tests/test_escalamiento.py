"""Tests del email de escalamiento (ruteo por categoría + fallback a Ventas)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from notificaciones.config import NotifConfig
from notificaciones.email import enviar_aviso_escalamiento


def _cfg(destinos: dict) -> NotifConfig:
    return NotifConfig(
        smtp_host="h", smtp_port=465, smtp_user="u", smtp_password="pw",
        email_from="f", destinos=destinos,
    )


class _R:
    """Doble duck-typed de RespuestaChatbot (lo que usa el email)."""
    def __init__(self, categoria, nombre_empresa=None):
        self.categoria = categoria
        self.nombre_empresa = nombre_empresa
        self.rubro = None
        self.linea_servicio = None
        self.necesidad = None
        self.ubicacion = None


def test_escalamiento_rutea_por_categoria():
    enviados = []
    cfg = _cfg({"Comercial/Ventas": "ventas@x", "Administración": "admin@x", "Servicio Técnico": "sop@x"})
    ok = enviar_aviso_escalamiento(
        _R("Administración", "Pyme SA"), "+5491100000000",
        config=cfg, sender=lambda c, d, a, b: enviados.append((d, a)),
    )
    assert ok is True
    assert enviados[0][0] == "admin@x"
    assert "PIDE HUMANO" in enviados[0][1]


def test_escalamiento_fallback_a_ventas_si_categoria_sin_destino():
    enviados = []
    cfg = _cfg({"Comercial/Ventas": "ventas@x", "Administración": "", "Servicio Técnico": ""})
    ok = enviar_aviso_escalamiento(
        _R("Desconocido"), "+5491100000000",
        config=cfg, sender=lambda c, d, a, b: enviados.append((d, a)),
    )
    assert ok is True
    assert enviados[0][0] == "ventas@x"


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
