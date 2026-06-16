# Ciclo de vida de la conversación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el próximo mensaje de un cliente arranque una conversación nueva cuando la anterior estuvo inactiva ≥24 h, de modo que un cliente que vuelve pueda volver a derivarse.

**Architecture:** Cambio acotado a `obtener_o_crear_conversacion` en `database.py`: además de buscar la última conversación activa del teléfono, verifica que su última actividad (fecha del último mensaje, o `fecha_creacion` si no hay mensajes) sea reciente; si superó la ventana, crea una conversación nueva (que nace con `derivada=False`). Sin cambios de schema ni en `main.py`.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, SQLite. Tests con runner stdlib propio del repo (no pytest), SQLite en memoria.

**Spec:** [docs/superpowers/specs/2026-06-15-ciclo-vida-conversacion-design.md](../specs/2026-06-15-ciclo-vida-conversacion-design.md)

---

## Notas de implementación (leer antes de empezar)

- **Timezone gotcha (verificado):** SQLite devuelve los `DateTime(timezone=True)` como `datetime` **naive** (sin `tzinfo`), aunque se guardan en UTC. Restar `datetime.now(timezone.utc)` (aware) menos un valor leído de la BD (naive) lanza `TypeError: can't subtract offset-naive and offset-aware datetimes`. Por eso se normaliza todo a UTC tz-aware con un helper `_as_utc` antes de comparar.
- **Convención de tests del repo:** no hay pytest. Cada archivo de test trae un bloque `if __name__ == "__main__"` que corre las funciones `test_*` con la stdlib. Se ejecuta con `python <ruta_al_test>`. Usar SQLite en memoria (`sqlite:///:memory:`), no `chatbot.db`.
- **Compatibilidad hacia atrás:** el nuevo parámetro `ahora` es opcional (default `None` → ahora real), así que las llamadas existentes en `main.py` no cambian.

## File Structure

- **Modify:** `database.py` — agrega constante `VENTANA_CONVERSACION_HORAS`, helpers `_as_utc` y `_ultima_actividad`, y reescribe `obtener_o_crear_conversacion` con el chequeo de ventana y el parámetro `ahora`.
- **Create:** `notificaciones/tests/test_conversacion_ventana.py` — tests de la ventana de inactividad (SQLite en memoria, runner stdlib).

---

### Task 1: Ventana de inactividad en `obtener_o_crear_conversacion`

**Files:**
- Modify: `database.py:1` (import), `database.py:67-82` (`obtener_o_crear_conversacion`)
- Create: `notificaciones/tests/test_conversacion_ventana.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `notificaciones/tests/test_conversacion_ventana.py` con este contenido completo:

```python
"""Tests de la ventana de inactividad de conversaciones (SQLite en memoria)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import (
    Base,
    guardar_mensaje,
    obtener_o_crear_conversacion,
    reclamar_derivacion,
)

TEL = "+5491150000099"


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_reutiliza_dentro_de_ventana():
    # Conversación recién creada (sin mensajes): un mensaje 1 h después la reutiliza.
    with _db() as db:
        conv1 = obtener_o_crear_conversacion(db, TEL)
        ahora = datetime.now(timezone.utc) + timedelta(hours=1)
        conv2 = obtener_o_crear_conversacion(db, TEL, ahora=ahora)
        assert conv2.id == conv1.id


def test_crea_nueva_pasada_la_ventana():
    # Conversación vacía y vieja (>24 h): se crea una nueva con derivada=False.
    with _db() as db:
        conv1 = obtener_o_crear_conversacion(db, TEL)
        ahora = datetime.now(timezone.utc) + timedelta(hours=25)
        conv2 = obtener_o_crear_conversacion(db, TEL, ahora=ahora)
        assert conv2.id != conv1.id
        assert conv2.derivada is False


def test_reutiliza_segun_ultimo_mensaje():
    # La ventana se mide desde el ÚLTIMO mensaje, no desde la creación.
    with _db() as db:
        conv1 = obtener_o_crear_conversacion(db, TEL)
        guardar_mensaje(db, conv1.id, "user", "hola")
        ahora = datetime.now(timezone.utc) + timedelta(hours=23)
        conv2 = obtener_o_crear_conversacion(db, TEL, ahora=ahora)
        assert conv2.id == conv1.id


def test_cliente_derivado_que_vuelve_se_puede_rederivar():
    # Bug original: cliente derivado que vuelve pasada la ventana arranca
    # conversación nueva con derivada=False (vuelve a poder derivarse).
    with _db() as db:
        conv1 = obtener_o_crear_conversacion(db, TEL)
        assert reclamar_derivacion(db, conv1.id) is True
        ahora = datetime.now(timezone.utc) + timedelta(hours=25)
        conv2 = obtener_o_crear_conversacion(db, TEL, ahora=ahora)
        assert conv2.id != conv1.id
        assert conv2.derivada is False


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
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/bin/python notificaciones/tests/test_conversacion_ventana.py`
Expected: FAIL. Los tests que pasan `ahora=` fallan con `TypeError: obtener_o_crear_conversacion() got an unexpected keyword argument 'ahora'` (la firma actual no acepta `ahora`).

- [ ] **Step 3: Actualizar el import de datetime en `database.py`**

En `database.py:1`, cambiar:

```python
from datetime import datetime, timezone
```

por:

```python
from datetime import datetime, timedelta, timezone
```

- [ ] **Step 4: Reescribir `obtener_o_crear_conversacion` y agregar helpers**

En `database.py`, reemplazar la función actual (`database.py:67-82`):

```python
def obtener_o_crear_conversacion(db: Session, telefono: str) -> Conversacion:
    conversacion = (
        db.query(Conversacion)
        .filter(
            Conversacion.telefono_cliente == telefono,
            Conversacion.estado_humano == False,
        )
        .order_by(Conversacion.fecha_creacion.desc())
        .first()
    )
    if conversacion is None:
        conversacion = Conversacion(telefono_cliente=telefono)
        db.add(conversacion)
        db.commit()
        db.refresh(conversacion)
    return conversacion
```

por:

```python
# Inactividad tras la cual el próximo mensaje arranca una conversación NUEVA.
# Coincide con la ventana de sesión de WhatsApp/Twilio. Así un cliente que
# vuelve (incluso ya derivado) abre un caso nuevo y puede volver a derivarse.
VENTANA_CONVERSACION_HORAS = 24


def _as_utc(dt: datetime) -> datetime:
    """SQLite devuelve datetimes naive; los tratamos como UTC para poder comparar."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _ultima_actividad(db: Session, conversacion: Conversacion) -> datetime:
    """Fecha (UTC, tz-aware) del último mensaje; fecha_creacion si no hay mensajes."""
    fila = (
        db.query(HistorialMensaje.fecha)
        .filter(HistorialMensaje.conversacion_id == conversacion.id)
        .order_by(HistorialMensaje.id.desc())
        .first()
    )
    return _as_utc(fila[0] if fila else conversacion.fecha_creacion)


def obtener_o_crear_conversacion(
    db: Session, telefono: str, ahora: datetime | None = None
) -> Conversacion:
    """Devuelve la conversación activa y RECIENTE del teléfono, o crea una nueva.

    "Reciente" = con última actividad dentro de VENTANA_CONVERSACION_HORAS. Si la
    última conversación expiró (o no hay), se crea una nueva (con derivada=False).
    `ahora` es inyectable para tests.
    """
    instante = _as_utc(ahora or datetime.now(timezone.utc))
    conversacion = (
        db.query(Conversacion)
        .filter(
            Conversacion.telefono_cliente == telefono,
            Conversacion.estado_humano == False,  # noqa: E712
        )
        .order_by(Conversacion.fecha_creacion.desc())
        .first()
    )
    if conversacion is not None:
        dentro_de_ventana = (
            instante - _ultima_actividad(db, conversacion)
            < timedelta(hours=VENTANA_CONVERSACION_HORAS)
        )
        if dentro_de_ventana:
            return conversacion

    conversacion = Conversacion(telefono_cliente=telefono)
    db.add(conversacion)
    db.commit()
    db.refresh(conversacion)
    return conversacion
```

- [ ] **Step 5: Correr el test nuevo y verificar que pasa**

Run: `.venv/bin/python notificaciones/tests/test_conversacion_ventana.py`
Expected: PASS — `4/4 tests pasaron`.

- [ ] **Step 6: Correr la suite existente para descartar regresiones**

Run los tests que tocan database.py y la app:

```bash
.venv/bin/python notificaciones/tests/test_db_derivacion.py
.venv/bin/python seguridad/tests/test_chat_auth.py
```

Expected: ambos PASS (el parámetro `ahora` es opcional, no rompe las llamadas existentes en `main.py`).

- [ ] **Step 7: Commit**

```bash
git add database.py notificaciones/tests/test_conversacion_ventana.py
git commit -m "feat: expirar conversación por inactividad (24h) para permitir re-derivar

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Cobertura del spec:**
  - Disparador por inactividad + ventana 24 h → `VENTANA_CONVERSACION_HORAS` + chequeo en Step 4. ✓
  - Opción A (sin cambio de schema) → no se toca ninguna tabla/columna. ✓
  - Última actividad = último mensaje, fallback a `fecha_creacion` → `_ultima_actividad`. ✓
  - Parámetro `ahora` inyectable → firma nueva. ✓
  - Conversación nueva con `derivada=False` → se crea `Conversacion(...)` sin setear `derivada` (default False). ✓
  - Comparación tz-consistente → `_as_utc`. ✓
  - Tests: dentro de ventana, pasada la ventana, según último mensaje, cliente derivado que vuelve, edge de conversación vacía vieja (test 2). ✓
- **Placeholders:** ninguno; todo el código y los comandos están completos. ✓
- **Consistencia de tipos/nombres:** `obtener_o_crear_conversacion(db, telefono, ahora=None)`, `_as_utc`, `_ultima_actividad`, `VENTANA_CONVERSACION_HORAS` usados igual en plan y tests. `HistorialMensaje` ya está definido en `database.py`. ✓
