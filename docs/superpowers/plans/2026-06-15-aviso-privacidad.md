# Aviso de privacidad (art. 6) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar un aviso de privacidad corto (finalidad + responsable + derechos) en la primera respuesta del bot de cada conversación nueva, cumpliendo el deber de informar al recabar (Ley 25.326 art. 6).

**Architecture:** Una constante `MSG_AVISO_PRIVACIDAD` y un helper `_con_aviso_si_primero` en `main.py`. En `_procesar_mensaje` se captura `es_primer_turno` (conversación sin mensajes) y se agrega el aviso a la respuesta del cliente en las dos ramas que responden (normal y escalamiento a humano).

**Tech Stack:** Python 3.11, FastAPI, pytest. Tests con runner stdlib del repo (colectables por pytest), `main._llamar_gemini` reemplazado por un doble, SQLite en memoria. Correr con `.venv/bin/python`.

**Spec:** [docs/superpowers/specs/2026-06-15-aviso-privacidad-design.md](../specs/2026-06-15-aviso-privacidad-design.md)

---

## Notas de implementación

- `es_primer_turno = not conversacion.mensajes`: una conversación recién creada no tiene mensajes.
- El aviso se aplica DESPUÉS de fijar el texto final de cada rama: en escalamiento se envuelve `MSG_ESCALAMIENTO_HUMANO`; en la rama normal se envuelve `resultado.respuesta_al_cliente` recién después del `if resultado.solicita_humano` (que hace `return`), para no perderlo si hubo escalamiento.
- Se persiste el mensaje del bot CON el aviso (registro fiel de lo que recibió el cliente).

## File Structure

- **Modify:** `main.py` — constante `MSG_AVISO_PRIVACIDAD`, helper `_con_aviso_si_primero`, y 3 ediciones puntuales en `_procesar_mensaje`.
- **Create:** `seguridad/tests/test_aviso_privacidad.py`.

---

### Task 1: Aviso de privacidad en el primer turno

**Files:**
- Modify: `main.py`
- Create: `seguridad/tests/test_aviso_privacidad.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `seguridad/tests/test_aviso_privacidad.py` con este contenido EXACTO:

```python
"""Tests del aviso de privacidad (art. 6) en el primer turno de cada conversación."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import main
from ia import rate_limit
from database import Base

TEL = "+5491150000055"


def _resultado(**kw):
    base = dict(
        categoria=main.Categoria.comercial,
        respuesta_al_cliente="Hola, contame en qué te ayudo.",
        notificar_recepcion=False,
        solicita_humano=False,
    )
    base.update(kw)
    return main.RespuestaChatbot(**base)


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_primer_mensaje_incluye_aviso():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda h, t: _resultado()
        with _db() as db:
            _, res = main._procesar_mensaje(db, TEL, "hola", None)
            assert res is not None
            assert main.MSG_AVISO_PRIVACIDAD in res.respuesta_al_cliente
    finally:
        main._llamar_gemini = original


def test_segundo_mensaje_no_incluye_aviso():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda h, t: _resultado()
        with _db() as db:
            main._procesar_mensaje(db, TEL, "hola", None)            # primer turno
            _, res2 = main._procesar_mensaje(db, TEL, "otra cosa", None)  # segundo turno
            assert res2 is not None
            assert main.MSG_AVISO_PRIVACIDAD not in res2.respuesta_al_cliente
    finally:
        main._llamar_gemini = original


def test_escalamiento_primer_turno_incluye_aviso():
    rate_limit.reset()
    original = main._llamar_gemini
    try:
        main._llamar_gemini = lambda h, t: _resultado(solicita_humano=True)
        with _db() as db:
            _, res = main._procesar_mensaje(db, TEL, "quiero hablar con alguien", None)
            assert res is not None
            assert main.MSG_ESCALAMIENTO_HUMANO in res.respuesta_al_cliente
            assert main.MSG_AVISO_PRIVACIDAD in res.respuesta_al_cliente
    finally:
        main._llamar_gemini = original


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

Run: `.venv/bin/python seguridad/tests/test_aviso_privacidad.py`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'MSG_AVISO_PRIVACIDAD'`. Resultado `0/3 tests pasaron`.

- [ ] **Step 3: Agregar la constante y el helper en `main.py`**

En `main.py`, reemplazar este bloque (el final de `_escalar_en_background` seguido de la firma de `_procesar_mensaje`):

```python
def _escalar_en_background(resultado: RespuestaChatbot, telefono: str) -> None:
    """Envía el email de escalamiento FUERA del request. La marca atómica de
    `marcar_estado_humano` ya garantizó un único disparo, así que acá solo se envía."""
    enviar_aviso_escalamiento(resultado, telefono)


def _procesar_mensaje(
```

por:

```python
def _escalar_en_background(resultado: RespuestaChatbot, telefono: str) -> None:
    """Envía el email de escalamiento FUERA del request. La marca atómica de
    `marcar_estado_humano` ya garantizó un único disparo, así que acá solo se envía."""
    enviar_aviso_escalamiento(resultado, telefono)


MSG_AVISO_PRIVACIDAD = (
    "Aviso de privacidad: tus datos (teléfono y mensajes) los trata infouno solo "
    "para atender y derivar tu consulta. Podés pedir acceder a ellos o borrarlos "
    "cuando quieras."
)


def _con_aviso_si_primero(texto: str, es_primer_turno: bool) -> str:
    """Agrega el aviso de privacidad (art. 6) si es el primer turno de la conversación."""
    if es_primer_turno:
        return f"{texto}\n\n{MSG_AVISO_PRIVACIDAD}"
    return texto


def _procesar_mensaje(
```

- [ ] **Step 4: Capturar `es_primer_turno` en `_procesar_mensaje`**

En `main.py`, reemplazar:

```python
    conversacion = obtener_o_crear_conversacion(db, telefono)

    # --- Modo humano: el bot no responde, pero guardamos el mensaje del cliente
```

por:

```python
    conversacion = obtener_o_crear_conversacion(db, telefono)
    es_primer_turno = not conversacion.mensajes  # conversación nueva → aviso de privacidad

    # --- Modo humano: el bot no responde, pero guardamos el mensaje del cliente
```

- [ ] **Step 5: Aplicar el aviso en la rama de escalamiento**

En `main.py`, dentro del `if resultado.solicita_humano:`, reemplazar:

```python
        resultado.respuesta_al_cliente = MSG_ESCALAMIENTO_HUMANO
```

por:

```python
        resultado.respuesta_al_cliente = _con_aviso_si_primero(MSG_ESCALAMIENTO_HUMANO, es_primer_turno)
```

- [ ] **Step 6: Aplicar el aviso en la rama normal**

En `main.py`, reemplazar (el `return` de la rama de escalamiento, seguido del `nota_json` de la rama normal):

```python
        return conversacion.id, resultado

    nota_json = resultado.model_dump_json(exclude={"respuesta_al_cliente"}, exclude_none=False)
    guardar_mensaje(db, conversacion.id, "user", texto)
```

por:

```python
        return conversacion.id, resultado

    resultado.respuesta_al_cliente = _con_aviso_si_primero(resultado.respuesta_al_cliente, es_primer_turno)
    nota_json = resultado.model_dump_json(exclude={"respuesta_al_cliente"}, exclude_none=False)
    guardar_mensaje(db, conversacion.id, "user", texto)
```

- [ ] **Step 7: Correr el test y verificar que pasa**

Run: `.venv/bin/python seguridad/tests/test_aviso_privacidad.py`
Expected: PASS — `3/3 tests pasaron`.

- [ ] **Step 8: Suite completa (sin regresiones)**

Run: `.venv/bin/python -m pytest`
Expected: PASS — todos los tests (incluye handoff, que comparte `_procesar_mensaje`). Cero fallos, cero errores de colección.

- [ ] **Step 9: Commit**

```bash
git add main.py seguridad/tests/test_aviso_privacidad.py
git commit -m "feat: aviso de privacidad (art. 6) en el primer mensaje de cada conversación

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Cobertura del spec:**
  - Constante `MSG_AVISO_PRIVACIDAD` (responsable + finalidad + derechos) → Step 3. ✓
  - Helper `_con_aviso_si_primero` → Step 3. ✓
  - `es_primer_turno = not conversacion.mensajes` → Step 4. ✓
  - Aviso en rama de escalamiento → Step 5. ✓
  - Aviso en rama normal (después del `if solicita_humano`) → Step 6. ✓
  - NO aparece en guardrail-block (retorna antes) ni en modo humano (retorna antes) ni en turnos siguientes (`es_primer_turno` False). ✓
  - Tests: primer turno incluye, segundo no, escalamiento primer turno incluye → Step 1. ✓
  - Fuera de alcance (registro AAIP) → no se toca. ✓
- **Placeholders:** ninguno; todo el código y comandos están completos. ✓
- **Consistencia de nombres:** `MSG_AVISO_PRIVACIDAD`, `_con_aviso_si_primero`, `es_primer_turno` usados igual en plan y tests. El helper se aplica al texto final de cada rama (no antes del override de escalamiento). ✓
