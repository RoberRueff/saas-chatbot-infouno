# Handoff a humano — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el cliente pueda pedir hablar con una persona; el bot confirma, marca la conversación en modo humano, avisa al equipo por email y deja de responder esa conversación (silencio) hasta que la ventana de 24 h la expire.

**Architecture:** El modelo marca un campo `solicita_humano`. `database.py` gana una marca atómica `marcar_estado_humano` y deja de filtrar por `estado_humano` en la búsqueda. `_procesar_mensaje` se bifurca: si la conversación ya está en modo humano → silencio (no llama a Gemini, persiste el mensaje); si el turno pide humano → marca + mensaje fijo + email de escalamiento en background, salteando la derivación. Los endpoints manejan la respuesta `None` (silencio).

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, SQLite, pytest. Tests con runner stdlib del repo (colectables por pytest), Gemini reemplazado por dobles. Correr con `.venv/bin/python`.

**Spec:** [docs/superpowers/specs/2026-06-15-handoff-humano-design.md](../specs/2026-06-15-handoff-humano-design.md)

---

## Notas de implementación

- Tests: cada archivo trae runner stdlib (`if __name__ == "__main__"`). Correr suelto con `.venv/bin/python <archivo>` o todo con `.venv/bin/python -m pytest`.
- En los tests de `_procesar_mensaje`, reemplazar `main._llamar_gemini` por un doble (no se llama a la API real). Resetear `ia.rate_limit` al empezar cada test para evitar acarreo de estado entre tests (pytest corre todo en un proceso).
- Orden: Task 1, 2 y 3 son independientes; Task 4 integra y depende de las tres.

## File Structure

- **Modify:** `database.py` — `marcar_estado_humano`; quitar filtro `estado_humano` de `obtener_o_crear_conversacion`.
- **Create:** `notificaciones/tests/test_estado_humano.py`.
- **Modify:** `notificaciones/email.py` — `intro` opcional en `construir_cuerpo`; `construir_asunto_escalamiento`; `enviar_aviso_escalamiento`.
- **Create:** `notificaciones/tests/test_escalamiento.py`.
- **Modify:** `main.py` — campo `solicita_humano` + regla en `SYSTEM_PROMPT`; `MSG_ESCALAMIENTO_HUMANO`; import `marcar_estado_humano` y `enviar_aviso_escalamiento`; `_escalar_en_background`; flujo de `_procesar_mensaje`; `RespuestaChat.datos` opcional; endpoints.
- **Create:** `ia/tests/test_respuesta_schema.py`, `seguridad/tests/test_handoff.py`.

---

### Task 1: DB — marca atómica de modo humano + búsqueda sin filtro

**Files:**
- Modify: `database.py` (`obtener_o_crear_conversacion` y nueva función)
- Create: `notificaciones/tests/test_estado_humano.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `notificaciones/tests/test_estado_humano.py` con este contenido EXACTO:

```python
"""Tests de la marca de modo humano y de la búsqueda sin filtro de estado."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import (
    Base,
    marcar_estado_humano,
    obtener_o_crear_conversacion,
)

TEL = "+5491150000077"


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_marcar_estado_humano_es_atomico_e_idempotente():
    with _db() as db:
        conv = obtener_o_crear_conversacion(db, TEL)
        assert marcar_estado_humano(db, conv.id) is True   # gana el primero
        assert marcar_estado_humano(db, conv.id) is False  # ya estaba marcada
        refrescada = obtener_o_crear_conversacion(db, TEL)
        assert refrescada.estado_humano is True


def test_obtener_devuelve_conversacion_aunque_este_en_modo_humano():
    # La búsqueda ya NO filtra por estado_humano: dentro de la ventana, devuelve
    # la misma conversación (para que el caller pueda callar al bot).
    with _db() as db:
        conv = obtener_o_crear_conversacion(db, TEL)
        marcar_estado_humano(db, conv.id)
        misma = obtener_o_crear_conversacion(db, TEL)
        assert misma.id == conv.id
        assert misma.estado_humano is True


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

Run: `.venv/bin/python notificaciones/tests/test_estado_humano.py`
Expected: FAIL — `ImportError: cannot import name 'marcar_estado_humano' from 'database'`.

- [ ] **Step 3: Quitar el filtro `estado_humano` en `obtener_o_crear_conversacion`**

En `database.py`, dentro de `obtener_o_crear_conversacion`, cambiar:

```python
    conversacion = (
        db.query(Conversacion)
        .filter(
            Conversacion.telefono_cliente == telefono,
            Conversacion.estado_humano == False,  # noqa: E712
        )
        .order_by(Conversacion.fecha_creacion.desc())
        .first()
    )
```

por:

```python
    conversacion = (
        db.query(Conversacion)
        .filter(Conversacion.telefono_cliente == telefono)
        .order_by(Conversacion.fecha_creacion.desc())
        .first()
    )
```

- [ ] **Step 4: Agregar `marcar_estado_humano`**

En `database.py`, agregar al final del archivo (junto a las otras funciones de mutación, después de `liberar_derivacion`):

```python


def marcar_estado_humano(db: Session, conversacion_id: int) -> bool:
    """Marca la conversación en modo humano de forma ATÓMICA.

    Devuelve True solo si ESTE llamado la marcó (gana la carrera); False si ya
    estaba en modo humano. El `UPDATE ... WHERE estado_humano = False` garantiza
    que el aviso de escalamiento se mande una sola vez.
    """
    resultado = db.execute(
        update(Conversacion)
        .where(Conversacion.id == conversacion_id, Conversacion.estado_humano == False)  # noqa: E712
        .values(estado_humano=True)
    )
    db.commit()
    return resultado.rowcount == 1
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `.venv/bin/python notificaciones/tests/test_estado_humano.py`
Expected: PASS — `2/2 tests pasaron`.

- [ ] **Step 6: Regresión (la búsqueda sin filtro no rompe el #1)**

Run: `.venv/bin/python notificaciones/tests/test_conversacion_ventana.py && .venv/bin/python notificaciones/tests/test_db_derivacion.py`
Expected: `5/5` y `2/2` tests pasaron.

- [ ] **Step 7: Commit**

```bash
git add database.py notificaciones/tests/test_estado_humano.py
git commit -m "feat(db): marca atómica de modo humano + búsqueda sin filtro de estado

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Email de escalamiento

**Files:**
- Modify: `notificaciones/email.py`
- Create: `notificaciones/tests/test_escalamiento.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `notificaciones/tests/test_escalamiento.py` con este contenido EXACTO:

```python
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
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv/bin/python notificaciones/tests/test_escalamiento.py`
Expected: FAIL — `ImportError: cannot import name 'enviar_aviso_escalamiento' from 'notificaciones.email'`.

- [ ] **Step 3: Agregar `intro` opcional a `construir_cuerpo`**

En `notificaciones/email.py`, cambiar la función `construir_cuerpo`:

```python
def construir_cuerpo(resultado, telefono: str) -> str:
    g = lambda campo: getattr(resultado, campo, None) or "-"
    return "\n".join([
        "Nuevo caso derivado desde el chatbot de WhatsApp.",
        "",
        f"Departamento: {_categoria_str(resultado)}",
        f"Empresa: {g('nombre_empresa')}",
        f"Rubro: {g('rubro')}",
        f"Línea de servicio: {g('linea_servicio')}",
        f"Necesidad: {g('necesidad')}",
        f"Ubicación: {g('ubicacion')}",
        f"Teléfono del cliente: {telefono}",
    ])
```

por (agrega el parámetro `intro` con el texto actual como default):

```python
def construir_cuerpo(resultado, telefono: str, *,
                     intro: str = "Nuevo caso derivado desde el chatbot de WhatsApp.") -> str:
    g = lambda campo: getattr(resultado, campo, None) or "-"
    return "\n".join([
        intro,
        "",
        f"Departamento: {_categoria_str(resultado)}",
        f"Empresa: {g('nombre_empresa')}",
        f"Rubro: {g('rubro')}",
        f"Línea de servicio: {g('linea_servicio')}",
        f"Necesidad: {g('necesidad')}",
        f"Ubicación: {g('ubicacion')}",
        f"Teléfono del cliente: {telefono}",
    ])
```

- [ ] **Step 4: Agregar el asunto y la función de escalamiento**

En `notificaciones/email.py`, agregar al final del archivo:

```python


def construir_asunto_escalamiento(resultado, telefono: str) -> str:
    quien = getattr(resultado, "nombre_empresa", None) or telefono
    return f"[infouno] PIDE HUMANO: {quien}"


def _destino_escalamiento(config: NotifConfig, categoria: str) -> str | None:
    """Ruteo por categoría; si no hay, fallback a Ventas y luego al primer destino."""
    return (
        config.destino_para(categoria)
        or config.destinos.get("Comercial/Ventas")
        or next((d for d in config.destinos.values() if d), None)
    )


def enviar_aviso_escalamiento(resultado, telefono: str, *,
                              config: NotifConfig | None = None,
                              sender=enviar_smtp) -> bool:
    """Avisa al equipo que el cliente pidió hablar con una persona.

    Devuelve True solo si el mail se envió OK. Nunca lanza: ante cualquier
    problema loguea y devuelve False (best-effort; el modo humano ya quedó marcado).
    """
    config = config or cargar_config()
    if not config.activo:
        logger.warning("Notificación por email DESACTIVADA (SMTP_PASSWORD vacío) — no se envía escalamiento")
        return False

    destino = _destino_escalamiento(config, _categoria_str(resultado))
    if not destino:
        logger.info("Sin destino para escalamiento — no se envía")
        return False

    try:
        sender(config, destino, construir_asunto_escalamiento(resultado, telefono),
               construir_cuerpo(resultado, telefono,
                                intro="El cliente pidió hablar con una persona (chatbot de WhatsApp)."))
        logger.info("Aviso de escalamiento enviado a %s", destino)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Falló el envío del aviso de escalamiento a %s", destino)
        return False
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `.venv/bin/python notificaciones/tests/test_escalamiento.py`
Expected: PASS — `2/2 tests pasaron`.

- [ ] **Step 6: Regresión del email de derivación**

Run: `.venv/bin/python notificaciones/tests/test_notificaciones.py`
Expected: `11/11 tests pasaron`.

- [ ] **Step 7: Commit**

```bash
git add notificaciones/email.py notificaciones/tests/test_escalamiento.py
git commit -m "feat(notif): email de escalamiento cuando el cliente pide un humano

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Campo `solicita_humano` + regla del system prompt

**Files:**
- Modify: `main.py` (`RespuestaChatbot`, `SYSTEM_PROMPT`)
- Create: `ia/tests/test_respuesta_schema.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `ia/tests/test_respuesta_schema.py` con este contenido EXACTO:

```python
"""Tests del schema RespuestaChatbot: el campo solicita_humano."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import main


def test_solicita_humano_default_false():
    r = main.RespuestaChatbot(
        categoria=main.Categoria.comercial,
        respuesta_al_cliente="hola",
        notificar_recepcion=False,
    )
    assert r.solicita_humano is False


def test_solicita_humano_se_parsea_true():
    r = main.RespuestaChatbot(
        categoria=main.Categoria.desconocido,
        respuesta_al_cliente="ok",
        notificar_recepcion=False,
        solicita_humano=True,
    )
    assert r.solicita_humano is True


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

Run: `.venv/bin/python ia/tests/test_respuesta_schema.py`
Expected: FAIL — `test_solicita_humano_default_false` falla con `AttributeError` (el campo no existe todavía); `test_solicita_humano_se_parsea_true` falla porque pasar un kwarg desconocido a un modelo Pydantic no lo setea (queda sin atributo) → AttributeError. Resultado `0/2`.

- [ ] **Step 3: Agregar el campo `solicita_humano` a `RespuestaChatbot`**

En `main.py`, dentro de `RespuestaChatbot`, después del campo `notificar_recepcion`:

```python
    notificar_recepcion: bool = Field(
        description="True si ya tenemos la información mínima para derivar el caso. False si todavía falta preguntar algo."
    )
```

agregar:

```python
    solicita_humano: bool = Field(
        default=False,
        description="True si el cliente pide explícitamente hablar con una persona / un asesor / un humano.",
    )
```

- [ ] **Step 4: Agregar la regla al `SYSTEM_PROMPT`**

En `main.py`, en `SYSTEM_PROMPT`, dentro de `## REGLAS ESTRICTAS DEL NEGOCIO`, agregar el punto 8 después del 7:

```
7. Una vez que tenés la información mínima para derivar, no seguís preguntando: confirmá la recepción y avisá que un asesor los va a contactar.
```

queda:

```
7. Una vez que tenés la información mínima para derivar, no seguís preguntando: confirmá la recepción y avisá que un asesor los va a contactar.
8. Si el cliente pide EXPLÍCITAMENTE hablar con una persona / un asesor / un humano, poné solicita_humano=True. No lo asumas si no lo pidió de forma explícita.
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `.venv/bin/python ia/tests/test_respuesta_schema.py`
Expected: PASS — `2/2 tests pasaron`.

- [ ] **Step 6: Regresión (el schema sigue parseando lo de antes)**

Run: `.venv/bin/python ia/tests/test_llamar_gemini.py`
Expected: `3/3 tests pasaron`.

- [ ] **Step 7: Commit**

```bash
git add main.py ia/tests/test_respuesta_schema.py
git commit -m "feat: campo solicita_humano en RespuestaChatbot + regla en el system prompt

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Integración — flujo de modo humano en `_procesar_mensaje` y endpoints

**Files:**
- Modify: `main.py` (imports, `MSG_ESCALAMIENTO_HUMANO`, `_escalar_en_background`, `_procesar_mensaje`, `RespuestaChat`, endpoints)
- Create: `seguridad/tests/test_handoff.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `seguridad/tests/test_handoff.py` con este contenido EXACTO:

```python
"""Tests de integración del handoff a humano (_procesar_mensaje + endpoints)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import main
from ia import rate_limit
from database import Base, obtener_o_crear_conversacion

TEL = "+5491150000088"


def _resultado(**kw):
    base = dict(
        categoria=main.Categoria.comercial,
        respuesta_al_cliente="hola",
        notificar_recepcion=False,
        solicita_humano=False,
    )
    base.update(kw)
    return main.RespuestaChatbot(**base)


class _BG:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *a, **k):
        self.tasks.append((fn, a, k))


def _nuevo_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_handoff_marca_humano_responde_fijo_y_agenda_email():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda hist, txt: _resultado(solicita_humano=True)
        with _nuevo_db() as db:
            bg = _BG()
            cid, res = main._procesar_mensaje(db, TEL, "quiero hablar con alguien", bg)
            assert res is not None
            assert res.respuesta_al_cliente == main.MSG_ESCALAMIENTO_HUMANO
            conv = obtener_o_crear_conversacion(db, TEL)
            assert conv.id == cid
            assert conv.estado_humano is True
            assert any(fn is main._escalar_en_background for fn, _, _ in bg.tasks)
    finally:
        main._llamar_gemini = original


def test_modo_humano_silencio_no_llama_gemini_y_persiste():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda hist, txt: _resultado(solicita_humano=True)
        with _nuevo_db() as db:
            bg = _BG()
            cid, _ = main._procesar_mensaje(db, TEL, "quiero un humano", bg)

            def _boom(hist, txt):
                raise AssertionError("no debe llamar a Gemini en modo humano")

            main._llamar_gemini = _boom
            cid2, res2 = main._procesar_mensaje(db, TEL, "otra cosa", bg)
            assert cid2 == cid
            assert res2 is None
            conv = obtener_o_crear_conversacion(db, TEL)
            assert "otra cosa" in [m.contenido for m in conv.mensajes]
    finally:
        main._llamar_gemini = original


def test_whatsapp_en_modo_humano_devuelve_twiml_vacio(monkeypatch=None):
    # Endpoint: si _procesar_mensaje devuelve respuesta None, TwiML sin <Message>.
    os.environ.pop("TWILIO_AUTH_TOKEN", None)
    os.environ["APP_ENV"] = "development"
    os.environ["GEMINI_API_KEY"] = "x"  # para pasar el check de _ia_configurada
    original = main._procesar_mensaje
    try:
        main._procesar_mensaje = lambda db, tel, txt, bg=None: (1, None)
        with TestClient(main.app) as client:
            r = client.post("/whatsapp", data={"From": "whatsapp:+5491100000000", "Body": "hola"})
            assert r.status_code == 200
            assert r.text == "<Response></Response>"
    finally:
        main._procesar_mensaje = original
        os.environ.pop("GEMINI_API_KEY", None)


def test_chat_en_modo_humano_devuelve_respuesta_vacia():
    os.environ["APP_SECRET_KEY"] = "secreto-test"
    os.environ["GEMINI_API_KEY"] = "x"
    original = main._procesar_mensaje
    try:
        main._procesar_mensaje = lambda db, tel, txt, bg=None: (7, None)
        with TestClient(main.app) as client:
            r = client.post(
                "/chat",
                json={"telefono_cliente": "+5491100000000", "mensaje": "hola"},
                headers={"X-API-Key": "secreto-test"},
            )
            assert r.status_code == 200, r.status_code
            cuerpo = r.json()
            assert cuerpo["respuesta"] == ""
            assert cuerpo["datos"] is None
            assert cuerpo["conversacion_id"] == 7
    finally:
        main._procesar_mensaje = original
        os.environ.pop("GEMINI_API_KEY", None)


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

Run: `.venv/bin/python seguridad/tests/test_handoff.py`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'MSG_ESCALAMIENTO_HUMANO'` (y `_escalar_en_background`), y los tests de endpoint fallan porque `_procesar_mensaje` aún no maneja `None`.

- [ ] **Step 3: Actualizar imports en `main.py`**

En `main.py`, cambiar el import de `database`:

```python
from database import (
    engine,
    get_db,
    guardar_mensaje,
    init_db,
    liberar_derivacion,
    obtener_o_crear_conversacion,
    reclamar_derivacion,
)
```

por (agrega `marcar_estado_humano`):

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

Y cambiar el import de notificaciones:

```python
from notificaciones.email import enviar_aviso_derivacion
```

por:

```python
from notificaciones.email import enviar_aviso_derivacion, enviar_aviso_escalamiento
```

- [ ] **Step 4: Relajar `RespuestaChat.datos` a opcional**

En `main.py`, cambiar la clase `RespuestaChat`:

```python
class RespuestaChat(BaseModel):
    conversacion_id: Optional[int] = None  # None si un guardrail bloqueó antes de crear conversación
    respuesta: str
    datos: RespuestaChatbot
```

por:

```python
class RespuestaChat(BaseModel):
    conversacion_id: Optional[int] = None  # None si un guardrail bloqueó antes de crear conversación
    respuesta: str = ""
    datos: Optional[RespuestaChatbot] = None  # None cuando el bot está en silencio (modo humano)
```

- [ ] **Step 5: Agregar `MSG_ESCALAMIENTO_HUMANO` y `_escalar_en_background`**

En `main.py`, después de la función `_derivar_en_background` (antes de `_procesar_mensaje`), agregar:

```python


MSG_ESCALAMIENTO_HUMANO = (
    "Dale, le aviso a un asesor para que te contacte. En breve te responde una persona."
)


def _escalar_en_background(resultado: RespuestaChatbot, telefono: str) -> None:
    """Envía el email de escalamiento FUERA del request. La marca atómica de
    `marcar_estado_humano` ya garantizó un único disparo, así que acá solo se envía."""
    enviar_aviso_escalamiento(resultado, telefono)
```

- [ ] **Step 6: Reescribir el cuerpo de `_procesar_mensaje`**

En `main.py`, reemplazar TODO el cuerpo de `_procesar_mensaje` (desde la firma hasta el `return conversacion.id, resultado` final) por:

```python
def _procesar_mensaje(
    db: Session,
    telefono: str,
    texto: str,
    background_tasks: BackgroundTasks | None = None,
) -> tuple[Optional[int], Optional[RespuestaChatbot]]:
    # --- Guardrails de entrada (rate limit -> validación -> anti-injection) ---
    # Si bloquea, NO llamamos a Gemini y NO persistimos el mensaje (evita que un
    # intento de injection quede en el historial y contamine las próximas llamadas).
    veredicto = guardrails.revisar_entrada(telefono, texto)
    if not veredicto.permitido:
        logger.warning("Guardrail de entrada bloqueó mensaje de %s — motivo: %s", telefono, veredicto.motivo)
        return None, _respuesta_sintetica(veredicto.respuesta_fija)

    conversacion = obtener_o_crear_conversacion(db, telefono)

    # --- Modo humano: el bot no responde, pero guardamos el mensaje del cliente
    # para que el asesor tenga el historial completo. No se llama a Gemini.
    if conversacion.estado_humano:
        guardar_mensaje(db, conversacion.id, "user", texto)
        logger.info("Conversación %s en modo humano — bot en silencio", conversacion.id)
        return conversacion.id, None

    mensajes = conversacion.mensajes[-MAX_HISTORIAL_MENSAJES:]
    # Gemini exige que el historial arranque con un turno de usuario.
    while mensajes and mensajes[0].rol != "user":
        mensajes = mensajes[1:]
    historial = [{"role": msg.rol, "content": msg.contenido} for msg in mensajes]
    # Llamamos a Gemini ANTES de persistir: si falla, no dejamos un turno "user"
    # huérfano que ensucie el historial (dos turnos de usuario seguidos) en el próximo mensaje.
    resultado = _llamar_gemini(historial, texto)

    # --- Guardrail de salida (reglas de negocio: sin precios ni diagnósticos) ---
    texto_seguro, motivo_salida = guardrails.sanitizar_salida(resultado.respuesta_al_cliente)
    if motivo_salida is not None:
        logger.warning("Guardrail de salida sanitizó respuesta para %s — motivo: %s", telefono, motivo_salida)
        resultado.respuesta_al_cliente = texto_seguro

    # --- Escalamiento a humano: el cliente pidió una persona. Marcamos modo humano
    # (atómico), respondemos un texto fijo y avisamos al equipo en background. La
    # derivación de este turno se saltea (el escalamiento la reemplaza).
    if resultado.solicita_humano:
        gano = marcar_estado_humano(db, conversacion.id)
        resultado.respuesta_al_cliente = MSG_ESCALAMIENTO_HUMANO
        nota_json = resultado.model_dump_json(exclude={"respuesta_al_cliente"}, exclude_none=False)
        guardar_mensaje(db, conversacion.id, "user", texto)
        guardar_mensaje(db, conversacion.id, "assistant", resultado.respuesta_al_cliente, nota_json)
        if gano and background_tasks is not None:
            background_tasks.add_task(_escalar_en_background, resultado, telefono)
        return conversacion.id, resultado

    nota_json = resultado.model_dump_json(exclude={"respuesta_al_cliente"}, exclude_none=False)
    guardar_mensaje(db, conversacion.id, "user", texto)
    guardar_mensaje(db, conversacion.id, "assistant", resultado.respuesta_al_cliente, nota_json)

    # --- Derivación: si el caso quedó listo y todavía no fue notificado, AGENDAR
    # el envío del email en BACKGROUND (no bloquea la respuesta al cliente, así el
    # webhook de Twilio no se cuelga si el SMTP está lento). El reclamo atómico
    # dentro de la tarea garantiza un único envío por caso.
    if (background_tasks is not None
            and resultado.notificar_recepcion
            and not conversacion.derivada
            and resultado.categoria != Categoria.desconocido):
        background_tasks.add_task(_derivar_en_background, conversacion.id, resultado, telefono)

    return conversacion.id, resultado
```

- [ ] **Step 7: Manejar el silencio en `/chat`**

En `main.py`, cambiar el cuerpo de `chat` después del `try/except`:

```python
    return RespuestaChat(
        conversacion_id=conv_id,
        respuesta=resultado.respuesta_al_cliente,
        datos=resultado,
    )
```

por:

```python
    if resultado is None:
        return RespuestaChat(conversacion_id=conv_id, respuesta="", datos=None)
    return RespuestaChat(
        conversacion_id=conv_id,
        respuesta=resultado.respuesta_al_cliente,
        datos=resultado,
    )
```

- [ ] **Step 8: Manejar el silencio en `/whatsapp`**

En `main.py`, cambiar el bloque `try/except` + armado del TwiML de `whatsapp_webhook`:

```python
    try:
        _, resultado = _procesar_mensaje(db, telefono, Body, background_tasks)
        respuesta_texto = resultado.respuesta_al_cliente
    except Exception:
        logger.exception("Error procesando /whatsapp para %s", telefono)
        respuesta_texto = "Hubo un problema procesando tu mensaje. Por favor intentá de nuevo en unos minutos."

    twiml = f"<Response><Message>{xml_escape(respuesta_texto)}</Message></Response>"
    return Response(content=twiml, media_type="application/xml")
```

por:

```python
    try:
        _, resultado = _procesar_mensaje(db, telefono, Body, background_tasks)
    except Exception:
        logger.exception("Error procesando /whatsapp para %s", telefono)
        respuesta_texto = "Hubo un problema procesando tu mensaje. Por favor intentá de nuevo en unos minutos."
    else:
        # Modo humano: el bot se calla (TwiML sin <Message>, Twilio no envía nada).
        if resultado is None:
            return Response(content="<Response></Response>", media_type="application/xml")
        respuesta_texto = resultado.respuesta_al_cliente

    twiml = f"<Response><Message>{xml_escape(respuesta_texto)}</Message></Response>"
    return Response(content=twiml, media_type="application/xml")
```

- [ ] **Step 9: Correr el test de integración y verificar que pasa**

Run: `.venv/bin/python seguridad/tests/test_handoff.py`
Expected: PASS — `4/4 tests pasaron`.

- [ ] **Step 10: Suite completa (sin regresiones)**

Run: `.venv/bin/python -m pytest`
Expected: PASS — todos los tests (incluye los nuevos de #2 handoff). Cero fallos, cero errores de colección.

- [ ] **Step 11: Commit**

```bash
git add main.py seguridad/tests/test_handoff.py
git commit -m "feat: handoff a humano — silencio del bot + escalamiento al pedir una persona

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Cobertura del spec:**
  - Campo `solicita_humano` + regla del prompt → Task 3. ✓
  - Quitar filtro `estado_humano` de la búsqueda → Task 1 Step 3. ✓
  - `marcar_estado_humano` atómico → Task 1 Step 4. ✓
  - Flujo: silencio si ya en modo humano (persiste user, no Gemini) → Task 4 Step 6. ✓
  - Transición: marca + mensaje fijo + email background + saltea derivación → Task 4 Step 6. ✓
  - Respuesta `None` + endpoints (`/whatsapp` TwiML vacío, `/chat` respuesta vacía, `datos` opcional) → Task 4 Steps 4,7,8. ✓
  - Email de escalamiento con ruteo + fallback a Ventas, best-effort → Task 2. ✓
  - `MSG_ESCALAMIENTO_HUMANO` voseo → Task 4 Step 5. ✓
  - Tests de cada parte → Tasks 1-4. ✓
  - Fuera de alcance (endpoint admin, consola de agentes) → no se tocan. ✓
- **Placeholders:** ninguno; todo el código y comandos están completos. ✓
- **Consistencia de tipos/nombres:** `marcar_estado_humano`, `enviar_aviso_escalamiento`, `_escalar_en_background`, `MSG_ESCALAMIENTO_HUMANO`, `solicita_humano`, `RespuestaChat.datos: Optional` usados igual en plan y tests. `_procesar_mensaje` ahora devuelve `tuple[Optional[int], Optional[RespuestaChatbot]]` y ambos endpoints manejan `None`. ✓
