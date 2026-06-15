"""Test de los PRAGMAs de SQLite (WAL + busy_timeout) sobre un engine temporal."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, event, text

from database import _aplicar_pragmas_sqlite


def test_wal_y_busy_timeout_activos():
    with tempfile.TemporaryDirectory() as d:
        eng = create_engine(f"sqlite:///{os.path.join(d, 't.db')}")
        event.listen(eng, "connect", _aplicar_pragmas_sqlite)
        with eng.connect() as c:
            modo = c.execute(text("PRAGMA journal_mode")).scalar()
            timeout = c.execute(text("PRAGMA busy_timeout")).scalar()
        assert modo.lower() == "wal", modo
        assert timeout == 5000, timeout


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
