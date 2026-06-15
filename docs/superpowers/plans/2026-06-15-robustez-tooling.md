# Robustez y tooling (#5 WAL, #6 guarda prod, #3 pytest) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tres mejoras de robustez/tooling independientes: pragmas SQLite (WAL + busy_timeout), guarda fail-fast de configuración de producción, y suite de tests corrible con pytest.

**Architecture:** #5 agrega un listener `connect` en `database.py`. #6 agrega una guarda llamada al inicio del `lifespan` en `main.py`. #3 agrega `requirements-dev.txt`, `pytest.ini` y una sección en el README; no toca código de tests.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, SQLite, FastAPI, pytest. Tests con runner stdlib del repo (también colectables por pytest). Correr con `.venv/bin/python`.

**Spec:** [docs/superpowers/specs/2026-06-15-robustez-tooling-design.md](../specs/2026-06-15-robustez-tooling-design.md)

---

## Notas de implementación

- Sin pytest para los runners stdlib: cada test file se corre con `.venv/bin/python <archivo>`. pytest ya está en el venv.
- Orden de tareas: #5 → #6 → #3 (el #3 corre la suite completa al final, incluyendo los tests nuevos).
- En #6, los tests guardan y restauran `os.environ` con `try/finally` para no contaminar otros tests (pytest corre todo en un proceso).

## File Structure

- **Modify:** `database.py` — `event` en el import; función `_aplicar_pragmas_sqlite` + `event.listen`.
- **Create:** `notificaciones/tests/test_db_pragmas.py`.
- **Modify:** `main.py` — constante `SECRETOS_REQUERIDOS_PROD`, función `_validar_config_produccion`, llamada en `lifespan`.
- **Create:** `seguridad/tests/test_config_prod.py`.
- **Create:** `requirements-dev.txt`, `pytest.ini`.
- **Modify:** `README.md` — sección Tests.

---

### Task 1 (#5): Pragmas SQLite (WAL + busy_timeout)

**Files:**
- Modify: `database.py` (import ~3-12; tras `engine` ~17)
- Create: `notificaciones/tests/test_db_pragmas.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `notificaciones/tests/test_db_pragmas.py` con este contenido EXACTO:

```python
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
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv/bin/python notificaciones/tests/test_db_pragmas.py`
Expected: FAIL — `ImportError: cannot import name '_aplicar_pragmas_sqlite' from 'database'`. Resultado `0/1 tests pasaron`.

- [ ] **Step 3: Agregar `event` al import de SQLAlchemy en `database.py`**

Cambiar el bloque de import (líneas ~3-12):

```python
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    update,
)
```

por (agrega `event`):

```python
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    update,
)
```

- [ ] **Step 4: Agregar la función y registrar el listener**

En `database.py`, justo después de la creación del engine:

```python
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
```

agregar:

```python


def _aplicar_pragmas_sqlite(dbapi_conn, _record) -> None:
    """Pragmas por conexión nueva:
    - WAL: lectores concurrentes + 1 escritor sin 'database is locked' inmediato.
    - busy_timeout: el escritor espera hasta 5 s por el lock en vez de fallar al toque.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


event.listen(engine, "connect", _aplicar_pragmas_sqlite)
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `.venv/bin/python notificaciones/tests/test_db_pragmas.py`
Expected: PASS — `1/1 tests pasaron`.

- [ ] **Step 6: Regresión rápida**

Run: `.venv/bin/python notificaciones/tests/test_db_derivacion.py && .venv/bin/python notificaciones/tests/test_conversacion_ventana.py`
Expected: `2/2` y `5/5` tests pasaron.

- [ ] **Step 7: Commit**

```bash
git add database.py notificaciones/tests/test_db_pragmas.py
git commit -m "perf: activar WAL + busy_timeout en SQLite para reducir 'database is locked'

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2 (#6): Guarda de configuración de producción (fail-fast)

**Files:**
- Modify: `main.py` (sección de setup, antes de `lifespan`; y dentro de `lifespan`)
- Create: `seguridad/tests/test_config_prod.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `seguridad/tests/test_config_prod.py` con este contenido EXACTO:

```python
"""Test de la guarda de configuración de producción (fail-fast)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import main

_VARS = ("APP_ENV", "APP_SECRET_KEY", "TWILIO_AUTH_TOKEN", "GEMINI_API_KEY")


def _con_entorno(**valores):
    """Devuelve (aplicar, restaurar): aplicar setea `valores` y borra el resto de
    _VARS; restaurar deja os.environ como estaba."""
    previo = {k: os.environ.get(k) for k in _VARS}

    def aplicar():
        for k in _VARS:
            os.environ.pop(k, None)
        for k, v in valores.items():
            os.environ[k] = v

    def restaurar():
        for k, v in previo.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return aplicar, restaurar


def test_dev_no_lanza_aunque_falten_secretos():
    aplicar, restaurar = _con_entorno(APP_ENV="development")
    try:
        aplicar()
        main._validar_config_produccion()  # no debe lanzar
    finally:
        restaurar()


def test_prod_lanza_si_falta_un_secreto():
    # Falta TWILIO_AUTH_TOKEN.
    aplicar, restaurar = _con_entorno(
        APP_ENV="production", APP_SECRET_KEY="x", GEMINI_API_KEY="y"
    )
    try:
        aplicar()
        lanzo = False
        try:
            main._validar_config_produccion()
        except RuntimeError as e:
            lanzo = True
            assert "TWILIO_AUTH_TOKEN" in str(e), str(e)
        assert lanzo, "esperaba RuntimeError por secreto faltante"
    finally:
        restaurar()


def test_prod_no_lanza_si_estan_todos():
    aplicar, restaurar = _con_entorno(
        APP_ENV="production",
        APP_SECRET_KEY="x",
        TWILIO_AUTH_TOKEN="y",
        GEMINI_API_KEY="z",
    )
    try:
        aplicar()
        main._validar_config_produccion()  # no debe lanzar
    finally:
        restaurar()


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

Run: `.venv/bin/python seguridad/tests/test_config_prod.py`
Expected: FAIL — los tests fallan con `AttributeError: module 'main' has no attribute '_validar_config_produccion'`. Resultado `0/3 tests pasaron`.

- [ ] **Step 3: Agregar la constante y la función en `main.py`**

En `main.py`, después de la configuración del logger:

```python
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot")
```

insertar:

```python


SECRETOS_REQUERIDOS_PROD = ("APP_SECRET_KEY", "TWILIO_AUTH_TOKEN", "GEMINI_API_KEY")


def _validar_config_produccion() -> None:
    """En producción, no arrancar si falta un secreto crítico (fail-fast).

    En desarrollo no hace nada. Evita servir mal configurado de forma silenciosa
    (p. ej. Twilio fail-open o /chat sin auth).
    """
    if os.getenv("APP_ENV", "development").lower() != "production":
        return
    faltantes = [k for k in SECRETOS_REQUERIDOS_PROD if not os.getenv(k)]
    if faltantes:
        raise RuntimeError(
            "Configuración de producción incompleta: faltan "
            + ", ".join(faltantes)
            + ". Definílas en el entorno antes de arrancar."
        )
```

- [ ] **Step 4: Llamar la guarda al inicio del `lifespan`**

En `main.py`, cambiar el cuerpo de `lifespan`:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    global gemini_client
    init_db()
    if _ia_configurada():
        gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    yield
```

por (agrega la primera línea):

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

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `.venv/bin/python seguridad/tests/test_config_prod.py`
Expected: PASS — `3/3 tests pasaron`.

- [ ] **Step 6: Regresión (la app importa y los tests de auth siguen ok)**

Run: `.venv/bin/python -c "import main; print('import main ok')" && .venv/bin/python seguridad/tests/test_chat_auth.py`
Expected: `import main ok` y `4/4 tests pasaron`.

- [ ] **Step 7: Commit**

```bash
git add main.py seguridad/tests/test_config_prod.py
git commit -m "feat(seguridad): fail-fast al arrancar en producción si falta un secreto crítico

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3 (#3): pytest + suite corrible

**Files:**
- Create: `requirements-dev.txt`, `pytest.ini`
- Modify: `README.md`

- [ ] **Step 1: Crear `requirements-dev.txt`**

Contenido EXACTO:

```
-r requirements.txt
pytest>=8.0
```

- [ ] **Step 2: Crear `pytest.ini`**

Contenido EXACTO:

```ini
[pytest]
testpaths = ia notificaciones seguridad
addopts = -q
```

- [ ] **Step 3: Agregar la sección Tests al README**

En `README.md`, insertar una sección nueva ANTES de la línea `## Seguridad y guardrails (\`ia/\`)`. Es decir, reemplazar:

```markdown
## Seguridad y guardrails (`ia/`)
```

por:

```markdown
## Tests

Instalá las dependencias de desarrollo y corré toda la suite con pytest:

```bash
pip install -r requirements-dev.txt
pytest
```

Cada archivo de test también trae un runner propio para correrlo aislado sin pytest:

```bash
python3 ia/tests/test_guardrails.py
```

## Seguridad y guardrails (`ia/`)
```

- [ ] **Step 4: Verificar que pytest corre toda la suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS — todos los tests pasan (las 49 previas + las de #5 y #6; ~53 passed). No debe haber fallos ni errores de colección.

- [ ] **Step 5: Commit**

```bash
git add requirements-dev.txt pytest.ini README.md
git commit -m "chore: pytest como runner unificado (requirements-dev, pytest.ini, README)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Cobertura del spec:**
  - #5 WAL + busy_timeout vía listener `connect`, función nombrada y testeable → Task 1. ✓
  - #6 guarda fail-fast solo en production, llamada en lifespan, mensaje que nombra faltantes → Task 2. ✓
  - #3 requirements-dev.txt + pytest.ini + README + corre toda la suite → Task 3. ✓
  - Tests de cada uno con runner stdlib + colectables por pytest. ✓
  - Fuera de alcance (Postgres, reescritura README a uv, script de arranque) → no se tocan. ✓
- **Placeholders:** ninguno; todo el contenido de archivos y comandos está completo. ✓
- **Consistencia de nombres:** `_aplicar_pragmas_sqlite`, `_validar_config_produccion`, `SECRETOS_REQUERIDOS_PROD` usados igual en plan y tests. El test de #5 importa la función de `database`; el de #6 usa `main._validar_config_produccion`. ✓
