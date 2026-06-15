"""Tests de purga por antigüedad y borrado a pedido (SQLite en memoria)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import (
    Base,
    Conversacion,
    HistorialMensaje,
    borrar_datos_telefono,
    guardar_mensaje,
    obtener_o_crear_conversacion,
    purgar_conversaciones_antiguas,
)


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_purga_borra_viejas_conserva_recientes():
    with _db() as db:
        vieja = obtener_o_crear_conversacion(db, "+5491100000001")
        m = guardar_mensaje(db, vieja.id, "user", "hola vieja")
        m.fecha = datetime.now(timezone.utc) - timedelta(days=200)  # envejecer
        db.commit()
        vieja_id = vieja.id

        reciente = obtener_o_crear_conversacion(db, "+5491100000002")
        guardar_mensaje(db, reciente.id, "user", "hola reciente")
        reciente_id = reciente.id

        n = purgar_conversaciones_antiguas(db)
        assert n == 1
        assert db.get(Conversacion, vieja_id) is None
        assert db.query(HistorialMensaje).filter_by(conversacion_id=vieja_id).count() == 0
        assert db.get(Conversacion, reciente_id) is not None


def test_purga_conversacion_vieja_sin_mensajes():
    # Sin mensajes: usa fecha_creacion. Inyectamos `ahora` 200 días en el futuro.
    with _db() as db:
        conv = obtener_o_crear_conversacion(db, "+5491100000003")
        cid = conv.id
        n = purgar_conversaciones_antiguas(db, ahora=datetime.now(timezone.utc) + timedelta(days=200))
        assert n == 1
        assert db.get(Conversacion, cid) is None


def test_borrar_datos_telefono():
    with _db() as db:
        a = obtener_o_crear_conversacion(db, "+5491100000010")
        guardar_mensaje(db, a.id, "user", "uno")
        guardar_mensaje(db, a.id, "assistant", "dos")
        b = obtener_o_crear_conversacion(db, "+5491100000020")
        guardar_mensaje(db, b.id, "user", "otro")
        a_id, b_id = a.id, b.id

        n = borrar_datos_telefono(db, "+5491100000010")
        assert n == 1
        assert db.get(Conversacion, a_id) is None
        assert db.query(HistorialMensaje).filter_by(conversacion_id=a_id).count() == 0
        # El otro teléfono queda intacto.
        assert db.get(Conversacion, b_id) is not None
        assert db.query(HistorialMensaje).filter_by(conversacion_id=b_id).count() == 1


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
