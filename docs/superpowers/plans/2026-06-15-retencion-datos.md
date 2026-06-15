# Retención de datos (purga + borrado a pedido) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cumplir la conservación limitada de la Ley 25.326: purgar automáticamente las conversaciones inactivas ≥ 6 meses y permitir el borrado a pedido de todos los datos de un teléfono.

**Architecture:** Dos funciones puras en `database.py` (`purgar_conversaciones_antiguas`, `borrar_datos_telefono`), un endpoint de admin protegido en `main.py` (`POST /admin/borrar-datos`), y la purga automática agendada en el `lifespan` (una purga inicial al arrancar + una tarea `asyncio` cada 24 h).

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, SQLite, pytest. Tests con runner stdlib del repo (colectables por pytest), SQLite en memoria; endpoints vía `TestClient`. Correr con `.venv/bin/python`.

**Spec:** [docs/superpowers/specs/2026-06-15-retencion-datos-design.md](../specs/2026-06-15-retencion-datos-design.md)

---

## Notas de implementación

- Reusa `_as_utc` y `_ultima_actividad` (ya existen en `database.py`, feature #1). `timedelta` ya está importado.
- "Última actividad" = fecha del último mensaje, o `fecha_creacion` si no hay mensajes. Purgable si `ahora - última_actividad >= timedelta(days=RETENCION_DIAS)`.
- No hay cascade configurado: borrar primero los `HistorialMensaje` y luego las `Conversacion`.
- En tests, envejecer datos seteando `mensaje.fecha` o `conversacion.fecha_creacion` a una fecha pasada, o inyectando `ahora` futuro.
- La tarea de purga periódica hace `sleep` ANTES de purgar, así un `TestClient` de vida corta (que arranca y apaga el `lifespan`) nunca dispara la purga periódica. La purga **inicial** sí corre al arrancar; sobre la BD real solo borra datos ≥180 días (en tests/CI es prácticamente un no-op).
- Orden: Task 1 (funciones DB) → Task 2 (endpoint, usa `borrar_datos_telefono`) → Task 3 (scheduling, usa `purgar_conversaciones_antiguas`).

## File Structure

- **Modify:** `database.py` — `RETENCION_DIAS`, `purgar_conversaciones_antiguas`, `borrar_datos_telefono`.
- **Create:** `notificaciones/tests/test_retencion.py`.
- **Modify:** `main.py` — import `borrar_datos_telefono`/`purgar_conversaciones_antiguas`; `import asyncio`; modelo `BorrarDatos`; endpoint `/admin/borrar-datos`; purga en `lifespan` (`_purga_inicial`, `_loop_purga`).
- **Create:** `seguridad/tests/test_borrado.py`.

---

### Task 1: Funciones de purga y borrado en `database.py`

**Files:**
- Modify: `database.py` (agregar al final)
- Create: `notificaciones/tests/test_retencion.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `notificaciones/tests/test_retencion.py` con este contenido EXACTO:

```python
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
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv/bin/python notificaciones/tests/test_retencion.py`
Expected: FAIL — `ImportError: cannot import name 'borrar_datos_telefono' from 'database'`.

- [ ] **Step 3: Agregar las funciones al final de `database.py`**

Agregar al FINAL de `database.py` (después de `marcar_estado_humano`):

```python


RETENCION_DIAS = 180  # 6 meses; conservación limitada (Ley 25.326 art. 4 inc. 7)


def purgar_conversaciones_antiguas(db: Session, ahora: datetime | None = None) -> int:
    """Borra conversaciones (y sus mensajes) con última actividad >= RETENCION_DIAS.

    Devuelve cuántas conversaciones borró. `ahora` es inyectable para tests.
    """
    instante = _as_utc(ahora or datetime.now(timezone.utc))
    corte = instante - timedelta(days=RETENCION_DIAS)
    ids = [c.id for c in db.query(Conversacion).all() if _ultima_actividad(db, c) < corte]
    if ids:
        db.query(HistorialMensaje).filter(
            HistorialMensaje.conversacion_id.in_(ids)
        ).delete(synchronize_session=False)
        db.query(Conversacion).filter(Conversacion.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    return len(ids)


def borrar_datos_telefono(db: Session, telefono: str) -> int:
    """Borra TODO lo de un teléfono (conversaciones + mensajes). Derecho de
    supresión (Ley 25.326 art. 16). Devuelve cuántas conversaciones borró.
    """
    ids = [
        c.id
        for c in db.query(Conversacion).filter(Conversacion.telefono_cliente == telefono).all()
    ]
    if ids:
        db.query(HistorialMensaje).filter(
            HistorialMensaje.conversacion_id.in_(ids)
        ).delete(synchronize_session=False)
        db.query(Conversacion).filter(Conversacion.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    return len(ids)
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/bin/python notificaciones/tests/test_retencion.py`
Expected: PASS — `3/3 tests pasaron`.

- [ ] **Step 5: Regresión**

Run: `.venv/bin/python notificaciones/tests/test_conversacion_ventana.py && .venv/bin/python notificaciones/tests/test_estado_humano.py`
Expected: `5/5` y `2/2` tests pasaron.

- [ ] **Step 6: Commit**

```bash
git add database.py notificaciones/tests/test_retencion.py
git commit -m "feat(db): purga por antigüedad (180d) y borrado total por teléfono

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Endpoint de admin `/admin/borrar-datos`

**Files:**
- Modify: `main.py` (import, modelo, endpoint)
- Create: `seguridad/tests/test_borrado.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `seguridad/tests/test_borrado.py` con este contenido EXACTO:

```python
"""Tests del endpoint de borrado a pedido (/admin/borrar-datos)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

import main

_BODY = {"telefono": "+5491100000000"}


def test_borrar_sin_api_key_rechaza():
    os.environ["APP_SECRET_KEY"] = "secreto-test"
    with TestClient(main.app) as client:
        r = client.post("/admin/borrar-datos", json=_BODY)
        assert r.status_code == 401, r.status_code


def test_borrar_con_api_key_borra():
    os.environ["APP_SECRET_KEY"] = "secreto-test"
    original = main.borrar_datos_telefono
    try:
        capturado = {}

        def _fake(db, telefono):
            capturado["telefono"] = telefono
            return 3

        main.borrar_datos_telefono = _fake
        with TestClient(main.app) as client:
            r = client.post("/admin/borrar-datos", json=_BODY, headers={"X-API-Key": "secreto-test"})
            assert r.status_code == 200, r.status_code
            cuerpo = r.json()
            assert cuerpo["conversaciones_borradas"] == 3
            assert cuerpo["telefono"] == "+5491100000000"
            assert capturado["telefono"] == "+5491100000000"
    finally:
        main.borrar_datos_telefono = original


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

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv/bin/python seguridad/tests/test_borrado.py`
Expected: FAIL — el POST a `/admin/borrar-datos` da 404 (el endpoint no existe), y `main.borrar_datos_telefono` no existe (`AttributeError`).

- [ ] **Step 3: Importar `borrar_datos_telefono` en `main.py`**

En `main.py`, en el import de `database`, agregar `borrar_datos_telefono`. Cambiar:

```python
from database import (
    engine,
    get_db,
    guardar_mensaje,
    init_db,
    liberar_derivacion,
    marcar_estado_humano,
    obtener_o_crear_conversacion,
    reclamar_derivacion,
)
```

por:

```python
from database import (
    borrar_datos_telefono,
    engine,
    get_db,
    guardar_mensaje,
    init_db,
    liberar_derivacion,
    marcar_estado_humano,
    obtener_o_crear_conversacion,
    reclamar_derivacion,
)
```

- [ ] **Step 4: Agregar el modelo `BorrarDatos`**

En `main.py`, en la sección Schemas, después de la clase `RespuestaChat`, agregar:

```python


class BorrarDatos(BaseModel):
    telefono: str = Field(description="Teléfono cuyos datos hay que borrar (derecho de supresión)")
```

- [ ] **Step 5: Agregar el endpoint**

En `main.py`, después del endpoint `chat` (antes de `whatsapp_webhook`), agregar:

```python


@app.post("/admin/borrar-datos", dependencies=[Depends(verificar_api_key)])
def borrar_datos(entrada: BorrarDatos, db: Session = Depends(get_db)):
    n = borrar_datos_telefono(db, entrada.telefono)
    logger.info("Borrado a pedido: %s conversaciones del teléfono %s", n, entrada.telefono)
    return {"telefono": entrada.telefono, "conversaciones_borradas": n}
```

- [ ] **Step 6: Correr el test y verificar que pasa**

Run: `.venv/bin/python seguridad/tests/test_borrado.py`
Expected: PASS — `2/2 tests pasaron`.

- [ ] **Step 7: Regresión (auth y app siguen ok)**

Run: `.venv/bin/python seguridad/tests/test_chat_auth.py && .venv/bin/python -c "import main; print('import main ok')"`
Expected: `4/4 tests pasaron` y `import main ok`.

- [ ] **Step 8: Commit**

```bash
git add main.py seguridad/tests/test_borrado.py
git commit -m "feat: endpoint admin /admin/borrar-datos (derecho de supresión)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Purga automática en el `lifespan`

**Files:**
- Modify: `main.py` (import `asyncio` y `purgar_conversaciones_antiguas`; `_purga_inicial`, `_loop_purga`, `lifespan`)
- Create: (test de humo en) `seguridad/tests/test_borrado.py` (agregar una función)

- [ ] **Step 1: Agregar el test de humo del arranque con purga**

En `seguridad/tests/test_borrado.py`, agregar esta función ANTES del bloque `if __name__ == "__main__"`:

```python
def test_app_arranca_con_purga_y_responde_root():
    # Arrancar el lifespan (que ahora corre la purga inicial) no debe romper.
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200
```

- [ ] **Step 2: Correr y verificar que falla (o pasa trivial)**

Run: `.venv/bin/python seguridad/tests/test_borrado.py`
Expected: las 2 anteriores PASAN y `test_app_arranca_con_purga_y_responde_root` PASA también (el lifespan actual no rompe). Este test es una red de seguridad para el cambio del Step siguiente: tras modificar el `lifespan`, debe seguir en verde. Resultado: `3/3 tests pasaron`.

- [ ] **Step 3: Agregar `import asyncio` y el import de la función de purga**

En `main.py`, agregar `import asyncio` al inicio (junto a los otros imports de stdlib, p. ej. después de `import os`).

Y en el import de `database`, agregar `purgar_conversaciones_antiguas`. Cambiar:

```python
from database import (
    borrar_datos_telefono,
    engine,
    get_db,
    guardar_mensaje,
    init_db,
    liberar_derivacion,
    marcar_estado_humano,
    obtener_o_crear_conversacion,
    reclamar_derivacion,
)
```

por:

```python
from database import (
    borrar_datos_telefono,
    engine,
    get_db,
    guardar_mensaje,
    init_db,
    liberar_derivacion,
    marcar_estado_humano,
    obtener_o_crear_conversacion,
    purgar_conversaciones_antiguas,
    reclamar_derivacion,
)
```

- [ ] **Step 4: Agregar `_purga_inicial` y `_loop_purga`**

En `main.py`, justo ANTES de la función `lifespan` (después del bloque de imports/`_validar_config_produccion`), agregar:

```python
INTERVALO_PURGA_SEG = 24 * 60 * 60  # purga periódica diaria


def _purga_inicial() -> None:
    """Corre una purga al arrancar. Best-effort: loguea y nunca tumba el arranque."""
    try:
        with Session(engine) as db:
            n = purgar_conversaciones_antiguas(db)
        if n:
            logger.info("Purga inicial: %s conversaciones eliminadas", n)
    except Exception:  # noqa: BLE001
        logger.exception("Error en la purga inicial")


async def _loop_purga() -> None:
    """Purga periódica cada 24 h. Duerme ANTES de purgar (así un arranque corto no dispara)."""
    while True:
        await asyncio.sleep(INTERVALO_PURGA_SEG)
        try:
            with Session(engine) as db:
                n = purgar_conversaciones_antiguas(db)
            if n:
                logger.info("Purga periódica: %s conversaciones eliminadas", n)
        except Exception:  # noqa: BLE001
            logger.exception("Error en la purga periódica")
```

- [ ] **Step 5: Conectar la purga en el `lifespan`**

En `main.py`, cambiar la función `lifespan`:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    global gemini_client
    _validar_config_produccion()
    init_db()
    if _ia_configurada():
        gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    yield
```

por:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    global gemini_client
    _validar_config_produccion()
    init_db()
    _purga_inicial()
    tarea_purga = asyncio.create_task(_loop_purga())
    if _ia_configurada():
        gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    try:
        yield
    finally:
        tarea_purga.cancel()
```

- [ ] **Step 6: Correr el test de humo y verificar que pasa**

Run: `.venv/bin/python seguridad/tests/test_borrado.py`
Expected: PASS — `3/3 tests pasaron`.

- [ ] **Step 7: Suite completa (sin regresiones)**

Run: `.venv/bin/python -m pytest`
Expected: PASS — todos los tests (incluye retención y borrado). Cero fallos, cero errores de colección.

- [ ] **Step 8: Commit**

```bash
git add main.py seguridad/tests/test_borrado.py
git commit -m "feat: purga automática de datos al arrancar + cada 24h (lifespan)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Cobertura del spec:**
  - `RETENCION_DIAS = 180` + `purgar_conversaciones_antiguas` (última actividad, cascade manual) → Task 1. ✓
  - `borrar_datos_telefono` (derecho de supresión) → Task 1. ✓
  - Endpoint `POST /admin/borrar-datos` con `verificar_api_key`, body `{telefono}`, respuesta con conteo → Task 2. ✓
  - Purga inicial al arrancar + tarea `asyncio` cada 24 h, cancelada en shutdown, errores logueados → Task 3. ✓
  - Tests: purga (vieja/reciente/sin-mensajes), borrado por teléfono (aísla otros), endpoint (401/200), humo de arranque → Tasks 1-3. ✓
  - Fuera de alcance (aviso de privacidad, registro AAIP, detección en chat) → no se implementan. ✓
- **Placeholders:** ninguno; todo el código y comandos están completos. ✓
- **Consistencia de nombres:** `purgar_conversaciones_antiguas`, `borrar_datos_telefono`, `RETENCION_DIAS`, `BorrarDatos`, `_purga_inicial`, `_loop_purga`, `INTERVALO_PURGA_SEG` usados igual en plan y tests. El endpoint usa `main.borrar_datos_telefono` (monkeypatcheable). `_as_utc`/`_ultima_actividad` ya existen en `database.py`. ✓
