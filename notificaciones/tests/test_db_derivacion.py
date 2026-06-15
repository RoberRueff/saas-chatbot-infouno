"""Test del marcado de derivación, con SQLite en memoria (no toca chatbot.db)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base, Conversacion, marcar_derivada


def test_marcar_derivada_setea_flag_y_fecha():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        conv = Conversacion(telefono_cliente="+5491150000010")
        db.add(conv)
        db.commit()
        assert conv.derivada is False

        marcar_derivada(db, conv)

        db.refresh(conv)
        assert conv.derivada is True
        assert conv.derivada_en is not None


if __name__ == "__main__":
    try:
        test_marcar_derivada_setea_flag_y_fecha()
        print("  ok   test_marcar_derivada_setea_flag_y_fecha")
        print("\n1/1 tests pasaron")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: {type(e).__name__}: {e}")
        sys.exit(1)
