"""Tests del reclamo atómico de derivación, con SQLite en memoria (no toca chatbot.db)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base, Conversacion, liberar_derivacion, reclamar_derivacion


def _conv(db) -> int:
    conv = Conversacion(telefono_cliente="+5491150000010")
    db.add(conv)
    db.commit()
    return conv.id


def test_reclamar_es_atomico_e_idempotente():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid = _conv(db)
        # El primer reclamo gana; el segundo ya la encuentra derivada.
        assert reclamar_derivacion(db, cid) is True
        assert reclamar_derivacion(db, cid) is False
        conv = db.get(Conversacion, cid)
        assert conv.derivada is True
        assert conv.derivada_en is not None


def test_liberar_permite_reintentar():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid = _conv(db)
        assert reclamar_derivacion(db, cid) is True
        liberar_derivacion(db, cid)
        conv = db.get(Conversacion, cid)
        assert conv.derivada is False
        # Tras liberar, se puede volver a reclamar (reintento).
        assert reclamar_derivacion(db, cid) is True


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
