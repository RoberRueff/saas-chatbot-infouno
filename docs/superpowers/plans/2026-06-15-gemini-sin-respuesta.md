# Fallback grácil cuando Gemini no devuelve texto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cuando Gemini no produzca texto (filtro de seguridad / MAX_TOKENS), el chatbot responda con un mensaje amable que invite a reformular, en vez de romperse con un `TypeError` que termina en 502.

**Architecture:** Cambio acotado a `_llamar_gemini` en `main.py`: si `response.text` es falsy, loguear `warning` y devolver una `RespuestaChatbot` sintética (categoría Desconocido, no notificar). Se renombra el helper `_respuesta_bloqueada` → `_respuesta_sintetica` porque ahora cubre dos casos (bloqueo de guardrail + IA sin respuesta).

**Tech Stack:** Python 3.11, FastAPI, google-genai 2.8.0. Tests con runner stdlib del repo (no pytest), usando un cliente Gemini falso (monkeypatch del global `main.gemini_client`).

**Spec:** [docs/superpowers/specs/2026-06-15-gemini-sin-respuesta-design.md](../specs/2026-06-15-gemini-sin-respuesta-design.md)

---

## Notas de implementación (leer antes de empezar)

- **`response.text` no lanza:** en google-genai 2.8.0 la property devuelve `None`
  cuando no hay candidato/contenido/partes (filtro de seguridad, MAX_TOKENS), y
  `""` solo si hubiera una parte de texto vacía. `if not response.text:` cubre
  ambos.
- **Forward reference OK:** `_respuesta_sintetica` se define más abajo en el
  archivo que `_llamar_gemini`, pero se llama en runtime, así que la referencia
  hacia adelante es válida en Python.
- **Único call site del helper:** `_respuesta_bloqueada` se usa solo en
  `_procesar_mensaje`. Confirmá con `git grep -n _respuesta_bloqueada` antes y
  después del rename (debe quedar 0 ocurrencias del nombre viejo).
- **Convención de tests:** sin pytest; runner stdlib (`python <archivo>`). Usá
  `.venv/bin/python`.

## File Structure

- **Modify:** `main.py` — agrega constante `MSG_IA_SIN_RESPUESTA`, guarda el caso
  sin texto en `_llamar_gemini`, y renombra `_respuesta_bloqueada` →
  `_respuesta_sintetica` (definición + call site).
- **Create:** `ia/tests/test_llamar_gemini.py` — tests del fallback con un cliente
  Gemini falso.

---

### Task 1: Fallback grácil en `_llamar_gemini` + rename del helper

**Files:**
- Modify: `main.py` (`_llamar_gemini` ~150-174; `_respuesta_bloqueada` ~184-190; call site ~219)
- Create: `ia/tests/test_llamar_gemini.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `ia/tests/test_llamar_gemini.py` con este contenido EXACTO:

```python
"""Tests de _llamar_gemini: fallback grácil cuando el modelo no devuelve texto."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import main


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.candidates = []


class _FakeModels:
    def __init__(self, resp):
        self._resp = resp

    def generate_content(self, **kwargs):
        return self._resp


class _FakeClient:
    def __init__(self, resp):
        self.models = _FakeModels(resp)


def _con_cliente(text):
    return _FakeClient(_FakeResp(text))


def test_devuelve_respuesta_parseada_si_hay_texto():
    original = main.gemini_client
    try:
        payload = json.dumps({
            "categoria": "Comercial/Ventas",
            "respuesta_al_cliente": "Hola, contame en qué te puedo ayudar.",
            "notificar_recepcion": False,
        })
        main.gemini_client = _con_cliente(payload)
        r = main._llamar_gemini([], "quiero automatizar mi local")
        assert r.categoria == main.Categoria.comercial
        assert r.respuesta_al_cliente == "Hola, contame en qué te puedo ayudar."
        assert r.notificar_recepcion is False
    finally:
        main.gemini_client = original


def test_fallback_si_text_es_none():
    original = main.gemini_client
    try:
        main.gemini_client = _con_cliente(None)
        r = main._llamar_gemini([], "hola")
        assert r.categoria == main.Categoria.desconocido
        assert r.notificar_recepcion is False
        assert r.respuesta_al_cliente == main.MSG_IA_SIN_RESPUESTA
    finally:
        main.gemini_client = original


def test_fallback_si_text_es_vacio():
    original = main.gemini_client
    try:
        main.gemini_client = _con_cliente("")
        r = main._llamar_gemini([], "hola")
        assert r.categoria == main.Categoria.desconocido
        assert r.respuesta_al_cliente == main.MSG_IA_SIN_RESPUESTA
    finally:
        main.gemini_client = original


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

Run: `.venv/bin/python ia/tests/test_llamar_gemini.py`
Expected: FAIL parcial. `test_devuelve_respuesta_parseada_si_hay_texto` PASA (la lógica actual ya parsea JSON válido). `test_fallback_si_text_es_none` y `test_fallback_si_text_es_vacio` FALLAN: el primero con `TypeError` (json.loads(None)), el segundo con `JSONDecodeError`/`ValueError` (json.loads("")), y ambos además con `AttributeError` si `MSG_IA_SIN_RESPUESTA` todavía no existe. Resultado: `1/3 tests pasaron`.

- [ ] **Step 3: Agregar la constante `MSG_IA_SIN_RESPUESTA`**

En `main.py`, insertar la constante justo ANTES de la función `_llamar_gemini` (dentro de la sección "IA — Google Gemini"), después de la función `verificar_api_key`:

```python
MSG_IA_SIN_RESPUESTA = (
    "Perdoná, no pude procesar bien tu mensaje. ¿Lo podés escribir de otra forma?"
)
```

- [ ] **Step 4: Guardar el caso sin texto en `_llamar_gemini`**

En `main.py`, reemplazar el final de `_llamar_gemini`. Cambiar:

```python
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RespuestaChatbot,
            temperature=0.3,
        ),
    )
    data = json.loads(response.text)
    return RespuestaChatbot(**data)
```

por:

```python
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RespuestaChatbot,
            temperature=0.3,
        ),
    )
    # El modelo puede no devolver texto (filtro de seguridad, MAX_TOKENS): en ese
    # caso response.text es None. No es un crash: degradamos con un mensaje amable
    # en vez de reventar al parsear.
    if not response.text:
        finish = None
        try:
            finish = response.candidates[0].finish_reason
        except Exception:  # noqa: BLE001
            pass
        logger.warning("Gemini no devolvió texto (finish_reason=%s) — fallback al cliente", finish)
        return _respuesta_sintetica(MSG_IA_SIN_RESPUESTA)
    data = json.loads(response.text)
    return RespuestaChatbot(**data)
```

- [ ] **Step 5: Renombrar `_respuesta_bloqueada` → `_respuesta_sintetica`**

En `main.py`, en la definición (~líneas 184-190), cambiar:

```python
def _respuesta_bloqueada(texto_fijo: str) -> RespuestaChatbot:
    """Respuesta sintética para cuando un guardrail de entrada bloquea el mensaje."""
```

por:

```python
def _respuesta_sintetica(texto_fijo: str) -> RespuestaChatbot:
    """Respuesta que arma la app (no el modelo): guardrail que bloquea o IA sin respuesta."""
```

Y en el call site dentro de `_procesar_mensaje` (~línea 219), cambiar:

```python
        return None, _respuesta_bloqueada(veredicto.respuesta_fija)
```

por:

```python
        return None, _respuesta_sintetica(veredicto.respuesta_fija)
```

- [ ] **Step 6: Verificar que no quedan referencias al nombre viejo**

Run: `git grep -n _respuesta_bloqueada -- main.py`
Expected: sin salida (0 ocurrencias).

- [ ] **Step 7: Correr el test nuevo y verificar que pasa**

Run: `.venv/bin/python ia/tests/test_llamar_gemini.py`
Expected: PASS — `3/3 tests pasaron`.

- [ ] **Step 8: Correr suite relacionada para descartar regresiones**

Run:
```bash
.venv/bin/python seguridad/tests/test_chat_auth.py
.venv/bin/python ia/tests/test_guardrails.py
.venv/bin/python -c "import main; print('import main ok')"
```
Expected: `4/4` y `17/17` tests pasaron; `import main ok`.

- [ ] **Step 9: Commit**

```bash
git add main.py ia/tests/test_llamar_gemini.py
git commit -m "fix: fallback grácil cuando Gemini no devuelve texto (filtro/MAX_TOKENS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Cobertura del spec:**
  - Guarda `if not response.text:` con warning + fallback → Step 4. ✓
  - `finish_reason` defensivo en el log → Step 4. ✓
  - Fallback con categoría Desconocido + no notificar → vía `_respuesta_sintetica` (que arma `categoria=Categoria.desconocido`, `notificar_recepcion=False`). ✓
  - Constante `MSG_IA_SIN_RESPUESTA` en `main.py` → Step 3. ✓
  - Rename `_respuesta_bloqueada` → `_respuesta_sintetica` + call site → Step 5, verificado en Step 6. ✓
  - Fuera de alcance (errores de red, JSON malformado) → no se tocan. ✓
  - Tests: texto válido, None, "" → Step 1. ✓
- **Placeholders:** ninguno; todo el código y los comandos están completos. ✓
- **Consistencia de tipos/nombres:** `_respuesta_sintetica`, `MSG_IA_SIN_RESPUESTA`, `Categoria.desconocido`, `main.gemini_client` usados igual en plan y tests. El helper devuelve `RespuestaChatbot` con los campos requeridos. ✓
