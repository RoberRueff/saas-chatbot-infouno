# Clasificación por departamento y notificación por email — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el bot clasifique cada conversación por departamento (Comercial/Ventas, Administración, Servicio Técnico, Desconocido) y, al quedar listo el caso, envíe un email al departamento correspondiente vía el SMTP propio de infouno — una sola vez por caso y sin romper la respuesta al cliente.

**Architecture:** Módulo aislado `notificaciones/` (mismo patrón que `ia/` y `seguridad/`): `config.py` (settings + ruteo desde env), `email.py` (fachada: arma asunto/cuerpo, resuelve destino, maneja errores), `sender.py` (adapter fino sobre `smtplib.SMTP_SSL`). `main.py` solo llama a una función. La idempotencia se persiste en `Conversacion.derivada`. El envío es no bloqueante e inyectable para tests.

**Tech Stack:** Python 3.11 (vía `.venv`), FastAPI, SQLAlchemy 2.x, Gemini 2.5 Flash, `smtplib`/`email` de la stdlib (sin dependencias nuevas).

**Spec:** [docs/superpowers/specs/2026-06-15-clasificacion-departamentos-y-email-design.md](../specs/2026-06-15-clasificacion-departamentos-y-email-design.md)

**Convención de tests:** se corren con el intérprete del venv y el runner propio de cada archivo (igual que `ia/tests/`):
`.venv/bin/python notificaciones/tests/test_notificaciones.py`

---

## File Structure

- **Create** `notificaciones/__init__.py` — paquete vacío.
- **Create** `notificaciones/config.py` — `NotifConfig` (dataclass) + `cargar_config()`; ruteo categoría→email y settings SMTP desde env.
- **Create** `notificaciones/sender.py` — `enviar_smtp(config, destino, asunto, cuerpo)`; adapter SMTP_SSL (boundary de I/O, no se unit-testea).
- **Create** `notificaciones/email.py` — `construir_asunto`, `construir_cuerpo`, `enviar_aviso_derivacion(...)`; fachada que usa `main.py`.
- **Create** `notificaciones/tests/__init__.py` — paquete vacío.
- **Create** `notificaciones/tests/test_notificaciones.py` — tests con `sender`/`config` inyectados (sin red).
- **Create** `database/tests` no aplica; **Modify** `database.py` — campos `derivada`/`derivada_en` + helper `marcar_derivada`.
- **Modify** `main.py` — enum `Categoria` (departamentos), campo `linea_servicio`, `SYSTEM_PROMPT`, y disparo del email en `_procesar_mensaje`.
- **Modify** `.env.example` — bloque SMTP (y el usuario replica en `.env`).

---

## Task 1: Config y ruteo de notificaciones

**Files:**
- Create: `notificaciones/__init__.py`
- Create: `notificaciones/config.py`
- Create: `notificaciones/tests/__init__.py`
- Create: `notificaciones/tests/test_notificaciones.py`

- [ ] **Step 1: Crear los `__init__.py` vacíos**

Crear `notificaciones/__init__.py` y `notificaciones/tests/__init__.py`, ambos vacíos.

- [ ] **Step 2: Escribir el test de config (falla)**

Crear `notificaciones/tests/test_notificaciones.py`:

```python
"""Tests del módulo de notificaciones.

Solo dependen de la stdlib (no de FastAPI/Gemini/pydantic), así que corren sin
instalar las dependencias del proyecto:

    .venv/bin/python notificaciones/tests/test_notificaciones.py
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from notificaciones.config import NotifConfig


def _config(**over):
    base = dict(
        smtp_host="mail.infouno.com.ar",
        smtp_port=465,
        smtp_user="bot@infouno.com.ar",
        smtp_password="secreta",
        email_from="bot@infouno.com.ar",
        destinos={
            "Comercial/Ventas": "ventas@infouno.com.ar",
            "Administración": "administracion@infouno.com.ar",
            "Servicio Técnico": "servicio.tecnico@infouno.com.ar",
        },
    )
    base.update(over)
    return NotifConfig(**base)


def test_destino_por_categoria():
    c = _config()
    assert c.destino_para("Comercial/Ventas") == "ventas@infouno.com.ar"
    assert c.destino_para("Administración") == "administracion@infouno.com.ar"
    assert c.destino_para("Servicio Técnico") == "servicio.tecnico@infouno.com.ar"


def test_destino_desconocido_es_none():
    c = _config()
    assert c.destino_para("Desconocido") is None
    assert c.destino_para("Cualquier Cosa") is None


def test_activo_segun_password():
    assert _config(smtp_password="x").activo is True
    assert _config(smtp_password="").activo is False


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fallos = 0
    for fn in funcs:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            fallos += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    total = len(funcs)
    print(f"\n{total - fallos}/{total} tests pasaron")
    sys.exit(1 if fallos else 0)
```

- [ ] **Step 3: Correr el test para verificar que falla**

Run: `.venv/bin/python notificaciones/tests/test_notificaciones.py`
Expected: ERROR — `ModuleNotFoundError: No module named 'notificaciones.config'`

- [ ] **Step 4: Implementar `notificaciones/config.py`**

```python
"""Config de las notificaciones por email.

Lee todo de variables de entorno (cargadas por `load_dotenv()` en main.py) y no
depende de FastAPI/Gemini, así que el módulo se puede testear con la stdlib.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class NotifConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    destinos: dict[str, str]  # categoria.value -> email del departamento

    def destino_para(self, categoria: str) -> str | None:
        """Email del departamento para una categoría, o None si no hay ruteo."""
        return self.destinos.get(categoria) or None

    @property
    def activo(self) -> bool:
        """La notificación está activa solo si hay contraseña SMTP configurada."""
        return bool(self.smtp_password)


def cargar_config() -> NotifConfig:
    """Construye la config desde el entorno (con defaults razonables)."""
    user = os.getenv("SMTP_USER", "")
    return NotifConfig(
        smtp_host=os.getenv("SMTP_HOST", "mail.infouno.com.ar"),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
        smtp_user=user,
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_from=os.getenv("NOTIF_EMAIL_FROM", user),
        destinos={
            "Comercial/Ventas": os.getenv("NOTIF_EMAIL_VENTAS", ""),
            "Administración": os.getenv("NOTIF_EMAIL_ADMIN", ""),
            "Servicio Técnico": os.getenv("NOTIF_EMAIL_SOPORTE", ""),
        },
    )
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/python notificaciones/tests/test_notificaciones.py`
Expected: PASS — `3/3 tests pasaron`

- [ ] **Step 6: Commit**

```bash
git add notificaciones/__init__.py notificaciones/config.py notificaciones/tests/
git commit -m "feat(notif): config y ruteo categoría->email"
```

---

## Task 2: Armado del asunto y el cuerpo del email

**Files:**
- Create: `notificaciones/email.py`
- Test: `notificaciones/tests/test_notificaciones.py`

- [ ] **Step 1: Agregar tests de armado (fallan)**

En `notificaciones/tests/test_notificaciones.py`, agregar el import y los tests antes del bloque `if __name__ == "__main__":`:

```python
from notificaciones.email import construir_asunto, construir_cuerpo


def _resultado(**over):
    base = dict(
        categoria="Comercial/Ventas",
        nombre_empresa="ModaSur",
        rubro="indumentaria",
        linea_servicio="Desarrollo Web",
        necesidad="tienda online",
        ubicacion="Rosario",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_asunto_incluye_categoria_y_empresa():
    asunto = construir_asunto(_resultado(), "+5491150000010")
    assert "Comercial/Ventas" in asunto
    assert "ModaSur" in asunto


def test_asunto_usa_telefono_si_no_hay_empresa():
    asunto = construir_asunto(_resultado(nombre_empresa=None), "+5491150000010")
    assert "+5491150000010" in asunto


def test_cuerpo_incluye_los_datos_del_caso():
    cuerpo = construir_cuerpo(_resultado(), "+5491150000010")
    for esperado in ["Comercial/Ventas", "ModaSur", "indumentaria",
                     "Desarrollo Web", "tienda online", "Rosario", "+5491150000010"]:
        assert esperado in cuerpo, f"falta en el cuerpo: {esperado}"


def test_cuerpo_tolera_campos_vacios():
    cuerpo = construir_cuerpo(_resultado(nombre_empresa=None, rubro=None,
                                         linea_servicio=None), "+5491150000010")
    assert "-" in cuerpo  # los campos faltantes se muestran como "-"
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `.venv/bin/python notificaciones/tests/test_notificaciones.py`
Expected: ERROR — `ModuleNotFoundError: No module named 'notificaciones.email'`

- [ ] **Step 3: Implementar `construir_asunto`/`construir_cuerpo` en `notificaciones/email.py`**

```python
"""Notificación por email al derivar un caso. Fachada que usa main.py.

`enviar_aviso_derivacion` arma el mail, resuelve el departamento destino y delega
el envío en un `sender` inyectable. Nunca propaga excepciones: si algo falla,
loguea y devuelve False (el cliente igual recibe su respuesta por WhatsApp).
"""
from __future__ import annotations

import logging

from notificaciones.config import NotifConfig, cargar_config
from notificaciones.sender import enviar_smtp

logger = logging.getLogger("chatbot.notificaciones")


def _categoria_str(resultado) -> str:
    """Acepta un enum (str, Enum) o un string y devuelve siempre el string."""
    cat = getattr(resultado, "categoria", None)
    return getattr(cat, "value", cat)


def construir_asunto(resultado, telefono: str) -> str:
    quien = getattr(resultado, "nombre_empresa", None) or telefono
    return f"[infouno] {_categoria_str(resultado)}: {quien}"


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

> Nota: el cuerpo no incluye una fecha calculada (se mantiene función pura y
> testeable); el header `Date` lo agrega el propio servidor SMTP al enviar.

- [ ] **Step 4: Correr para verificar que pasan**

Run: `.venv/bin/python notificaciones/tests/test_notificaciones.py`
Expected: PASS — `7/7 tests pasaron`

- [ ] **Step 5: Commit**

```bash
git add notificaciones/email.py notificaciones/tests/test_notificaciones.py
git commit -m "feat(notif): armado de asunto y cuerpo del email"
```

---

## Task 3: Orquestación del envío (toggle, ruteo, errores)

**Files:**
- Modify: `notificaciones/email.py`
- Test: `notificaciones/tests/test_notificaciones.py`

- [ ] **Step 1: Agregar tests de `enviar_aviso_derivacion` (fallan)**

En `notificaciones/tests/test_notificaciones.py`, agregar al import de email: `enviar_aviso_derivacion`, y estos tests:

```python
def _sender_espia(registro):
    def _sender(config, destino, asunto, cuerpo):
        registro.append((destino, asunto, cuerpo))
    return _sender


def test_envia_al_destino_correcto():
    enviados = []
    ok = enviar_aviso_derivacion(
        _resultado(categoria="Servicio Técnico"), "+5491150000010",
        config=_config(), sender=_sender_espia(enviados),
    )
    assert ok is True
    assert len(enviados) == 1
    assert enviados[0][0] == "servicio.tecnico@infouno.com.ar"


def test_no_envia_si_esta_desactivado():
    enviados = []
    ok = enviar_aviso_derivacion(
        _resultado(), "+549115", config=_config(smtp_password=""),
        sender=_sender_espia(enviados),
    )
    assert ok is False
    assert enviados == []


def test_no_envia_si_categoria_sin_destino():
    enviados = []
    ok = enviar_aviso_derivacion(
        _resultado(categoria="Desconocido"), "+549115",
        config=_config(), sender=_sender_espia(enviados),
    )
    assert ok is False
    assert enviados == []


def test_falla_del_sender_no_propaga_y_devuelve_false():
    def _sender_explota(config, destino, asunto, cuerpo):
        raise RuntimeError("SMTP caído")
    ok = enviar_aviso_derivacion(
        _resultado(), "+549115", config=_config(), sender=_sender_explota,
    )
    assert ok is False
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `.venv/bin/python notificaciones/tests/test_notificaciones.py`
Expected: ERROR — `ImportError: cannot import name 'enviar_aviso_derivacion'`

- [ ] **Step 3: Agregar `enviar_aviso_derivacion` al final de `notificaciones/email.py`**

```python
def enviar_aviso_derivacion(resultado, telefono: str, *,
                            config: NotifConfig | None = None,
                            sender=enviar_smtp) -> bool:
    """Envía el aviso de derivación al departamento que corresponde.

    Devuelve True solo si el mail se envió OK. Nunca lanza: ante cualquier
    problema (desactivado, sin destino, error de envío) loguea y devuelve False.
    """
    config = config or cargar_config()
    if not config.activo:
        logger.warning("Notificación por email DESACTIVADA (SMTP_PASSWORD vacío) — no se envía")
        return False

    destino = config.destino_para(_categoria_str(resultado))
    if not destino:
        logger.info("Sin destino para la categoría '%s' — no se envía", _categoria_str(resultado))
        return False

    try:
        sender(config, destino, construir_asunto(resultado, telefono),
               construir_cuerpo(resultado, telefono))
        logger.info("Aviso de derivación enviado a %s", destino)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Falló el envío del aviso de derivación a %s", destino)
        return False
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `.venv/bin/python notificaciones/tests/test_notificaciones.py`
Expected: PASS — `11/11 tests pasaron`

- [ ] **Step 5: Commit**

```bash
git add notificaciones/email.py notificaciones/tests/test_notificaciones.py
git commit -m "feat(notif): orquestación de envío con toggle, ruteo y manejo de errores"
```

---

## Task 4: Adapter SMTP

**Files:**
- Create: `notificaciones/sender.py`

> Capa fina de I/O sobre `smtplib`: es el boundary inevitable con la red, así que
> no se unit-testea (toda la lógica testeable vive en `email.py`/`config.py`, que
> reciben el sender inyectado). Se verifica con el envío real en la Task 8.

- [ ] **Step 1: Implementar `notificaciones/sender.py`**

```python
"""Adapter SMTP: capa fina sobre smtplib. El resto del módulo no toca la red.

Usa SMTP_SSL (puerto 465) contra el servidor propio de infouno. Lanza si el
envío falla; quien llama (`enviar_aviso_derivacion`) captura el error.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from notificaciones.config import NotifConfig


def enviar_smtp(config: NotifConfig, destino: str, asunto: str, cuerpo: str) -> None:
    msg = EmailMessage()
    msg["From"] = config.email_from
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.set_content(cuerpo)

    with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15) as smtp:
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(msg)
```

- [ ] **Step 2: Verificar import y que los tests siguen verdes**

Run: `.venv/bin/python -c "import notificaciones.sender; print('import OK')" && .venv/bin/python notificaciones/tests/test_notificaciones.py`
Expected: `import OK` y `11/11 tests pasaron`

- [ ] **Step 3: Commit**

```bash
git add notificaciones/sender.py
git commit -m "feat(notif): adapter SMTP_SSL"
```

---

## Task 5: Persistencia de derivación en la BD

**Files:**
- Modify: `database.py` (modelo `Conversacion` ~líneas 23-35; helpers al final)
- Test: `notificaciones/tests/test_db_derivacion.py` (nuevo, usa SQLite en memoria)

- [ ] **Step 1: Escribir el test de `marcar_derivada` (falla)**

Crear `notificaciones/tests/test_db_derivacion.py`:

```python
"""Test del marcado de derivación, con SQLite en memoria (no toca chatbot.db)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import database
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
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `.venv/bin/python notificaciones/tests/test_db_derivacion.py`
Expected: ERROR — `ImportError: cannot import name 'marcar_derivada'` (o `AttributeError` sobre `conv.derivada`)

- [ ] **Step 3: Agregar los campos al modelo `Conversacion` en `database.py`**

Después de la línea `fecha_creacion: Mapped[datetime] = mapped_column(...)` (dentro de `class Conversacion`, antes de la relación `mensajes`), agregar:

```python
    derivada: Mapped[bool] = mapped_column(Boolean, default=False)
    derivada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

(`Boolean` y `DateTime` ya están importados al inicio de `database.py`.)

- [ ] **Step 4: Agregar el helper `marcar_derivada` al final de `database.py`**

```python
def marcar_derivada(db: Session, conversacion: Conversacion) -> None:
    """Marca la conversación como derivada (caso ya notificado por email)."""
    conversacion.derivada = True
    conversacion.derivada_en = datetime.now(timezone.utc)
    db.commit()
```

- [ ] **Step 5: Correr para verificar que pasa**

Run: `.venv/bin/python notificaciones/tests/test_db_derivacion.py`
Expected: PASS — `1/1 tests pasaron`

- [ ] **Step 6: Commit**

```bash
git add database.py notificaciones/tests/test_db_derivacion.py
git commit -m "feat(db): campos derivada/derivada_en + helper marcar_derivada"
```

---

## Task 6: Clasificación por departamento en `main.py`

**Files:**
- Modify: `main.py` (enum `Categoria` líneas 71-74; campo nuevo tras `necesidad` ~línea 91; `SYSTEM_PROMPT` líneas 41-64)

> Cambios declarativos (enum, schema, prompt). No hay test unitario porque
> importar `main.py` exige FastAPI/Gemini; se valida con `py_compile` acá y con el
> smoke end-to-end en la Task 8.

- [ ] **Step 1: Reemplazar el enum `Categoria` (líneas 71-74)**

```python
class Categoria(str, Enum):
    comercial = "Comercial/Ventas"
    administracion = "Administración"
    servicio_tecnico = "Servicio Técnico"
    desconocido = "Desconocido"
```

- [ ] **Step 2: Agregar el campo `linea_servicio` al schema**

En `class RespuestaChatbot`, inmediatamente después del campo `necesidad` (antes de `info_faltante`), agregar:

```python
    linea_servicio: Optional[str] = Field(
        None,
        description="Línea de servicio cuando aplica: 'Automatización con IA' o 'Desarrollo Web'. None si no corresponde.",
    )
```

- [ ] **Step 3: Reescribir el `SYSTEM_PROMPT` (líneas 41-64)**

```python
SYSTEM_PROMPT = """
Sos el asistente virtual de infouno, una agencia argentina que ofrece automatización de procesos con IA y desarrollo web para pymes.
Atendés por WhatsApp a clientes reales y tu tarea es derivar cada consulta al DEPARTAMENTO correcto.

## DEPARTAMENTOS (categoría)
- "Comercial/Ventas": prospecto nuevo que quiere cotizar o contratar un servicio (automatización con IA o desarrollo web). Es el caso más común.
- "Administración": facturación, pagos, comprobantes, datos fiscales o temas de contrato.
- "Servicio Técnico": cliente existente con un problema o pedido de soporte sobre algo YA entregado (su web caída, su automatización fallando).
- "Desconocido": mensaje ambiguo o ajeno a infouno. Pedí aclaración, no derives.

## REGLAS ESTRICTAS DEL NEGOCIO
1. NUNCA des precios, cotizaciones ni valores estimados. Si preguntan, decí que un asesor los va a contactar con una propuesta a medida.
2. Hablá siempre de vos (voseo argentino), en tono profesional y cálido. Sin tuteo ni ustedeo formal.
3. Tu única función es capturar la información necesaria para derivar el caso. No resuelvas vos el pedido.
4. Si el cliente menciona una localidad o provincia, registrala; si no, preguntala.
5. Relevá el nombre de la empresa y el rubro de la pyme.
6. Para casos comerciales, identificá la línea de servicio (campo linea_servicio): "Automatización con IA" o "Desarrollo Web".
7. Una vez que tenés la información mínima para derivar, no seguís preguntando: confirmá la recepción y avisá que un asesor los va a contactar.

## INFORMACIÓN MÍNIMA PARA DERIVAR (recién ahí notificar_recepcion=True)
- Comercial/Ventas: necesidad (qué servicio) + rubro + ubicación
- Administración: nombre de la empresa + necesidad (qué trámite)
- Servicio Técnico: nombre de la empresa + necesidad (qué problema, sobre qué proyecto)

## IDIOMA
Solo español rioplatense. Ninguna respuesta en otro idioma.
""".strip()
```

- [ ] **Step 4: Verificar que compila**

Run: `.venv/bin/python -m py_compile main.py`
Expected: sin salida (compila OK)

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: clasificar por departamento (Comercial/Admin/Soporte) + campo linea_servicio"
```

---

## Task 7: Disparar el email al derivar (en `main.py`)

**Files:**
- Modify: `main.py` (imports líneas 18-20; `_procesar_mensaje` ~líneas 191-194)

- [ ] **Step 1: Actualizar los imports**

Reemplazar la línea 18 `from database import get_db, guardar_mensaje, init_db, obtener_o_crear_conversacion` por:

```python
from database import (
    get_db,
    guardar_mensaje,
    init_db,
    marcar_derivada,
    obtener_o_crear_conversacion,
)
```

Y debajo de `from ia import guardrails` (línea 19), agregar:

```python
from notificaciones.email import enviar_aviso_derivacion
```

- [ ] **Step 2: Disparar el aviso en `_procesar_mensaje`**

Reemplazar las dos líneas finales de la función (que hoy son):

```python
    guardar_mensaje(db, conversacion.id, "user", texto)
    guardar_mensaje(db, conversacion.id, "assistant", resultado.respuesta_al_cliente, nota_json)
    return conversacion.id, resultado
```

por:

```python
    guardar_mensaje(db, conversacion.id, "user", texto)
    guardar_mensaje(db, conversacion.id, "assistant", resultado.respuesta_al_cliente, nota_json)

    # --- Derivación: si el caso quedó listo y todavía no fue notificado, mandar
    # el email al departamento. Se marca derivada SOLO si el envío salió OK
    # (si falla, reintenta en el próximo mensaje del cliente). No bloqueante.
    if (resultado.notificar_recepcion
            and not conversacion.derivada
            and resultado.categoria != Categoria.desconocido):
        if enviar_aviso_derivacion(resultado, telefono):
            marcar_derivada(db, conversacion)

    return conversacion.id, resultado
```

- [ ] **Step 3: Verificar que compila**

Run: `.venv/bin/python -m py_compile main.py`
Expected: sin salida (compila OK)

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: enviar email al departamento al derivar el caso (idempotente, no bloqueante)"
```

---

## Task 8: Config `.env`, recrear DB y verificación end-to-end

**Files:**
- Modify: `.env.example`
- Modify (local, gitignored): `.env`
- Delete (local): `chatbot.db`

- [ ] **Step 1: Agregar el bloque SMTP a `.env.example`**

Al final de `.env.example`, agregar:

```
# SMTP — notificación por email al derivar un caso (servidor propio de infouno)
# Si SMTP_PASSWORD está vacío, la notificación se DESACTIVA (modo desarrollo).
SMTP_HOST=mail.infouno.com.ar
SMTP_PORT=465
SMTP_USER=bot@infouno.com.ar
SMTP_PASSWORD=
NOTIF_EMAIL_FROM=bot@infouno.com.ar
NOTIF_EMAIL_VENTAS=ventas@infouno.com.ar
NOTIF_EMAIL_ADMIN=administracion@infouno.com.ar
NOTIF_EMAIL_SOPORTE=servicio.tecnico@infouno.com.ar
```

- [ ] **Step 2: Replicar el bloque en `.env` (local)**

Copiar el mismo bloque a `.env`. Dejar `SMTP_PASSWORD` vacío por ahora (modo desactivado) o, si la cuenta `bot@infouno.com.ar` ya existe, completar la contraseña real.

- [ ] **Step 3: Recrear la base con el esquema nuevo**

La tabla `conversaciones` necesita las columnas nuevas. Como la DB está vacía:

Run: `cd "/Users/Rober/Desktop/Proyectos/saas chatbot infouno" && rm -f chatbot.db && .venv/bin/python -c "from database import init_db; init_db(); print('db recreada')"`
Expected: `db recreada`

- [ ] **Step 4: Correr toda la suite de tests**

Run: `.venv/bin/python notificaciones/tests/test_notificaciones.py && .venv/bin/python notificaciones/tests/test_db_derivacion.py && .venv/bin/python ia/tests/test_guardrails.py`
Expected: `11/11`, `1/1` y `17/17` tests pasaron.

- [ ] **Step 5: Smoke end-to-end en modo desactivado (sin mandar mails reales)**

Con `SMTP_PASSWORD` vacío, levantar el server en un puerto libre (NO el 8000, que puede tener otro server) y mandar un caso comercial completo:

```bash
cd "/Users/Rober/Desktop/Proyectos/saas chatbot infouno"
.venv/bin/uvicorn main:app --port 8010 > /tmp/infouno_e2e.log 2>&1 &
sleep 3
curl -s -X POST http://127.0.0.1:8010/chat -H "Content-Type: application/json" \
  -d '{"telefono_cliente":"+5491150000020","mensaje":"Hola, tengo una panadería en Córdoba y quiero automatizar pedidos por WhatsApp"}' | python3 -m json.tool
```

Expected: la respuesta clasifica `categoria: "Comercial/Ventas"`, captura `rubro`/`necesidad`/`ubicacion`, y `notificar_recepcion: true`. En `/tmp/infouno_e2e.log` aparece el warning `Notificación por email DESACTIVADA` (no se mandó mail, no se marcó derivada). Frenar el server: `kill %1`.

- [ ] **Step 6: (Opcional) Prueba de envío real**

Solo si la cuenta `bot@infouno.com.ar` existe: completar `SMTP_PASSWORD` en `.env`, recrear DB (`rm -f chatbot.db && .venv/bin/python -c "from database import init_db; init_db()"`), reiniciar el server y repetir el `curl` del Step 5. Verificar que llega el email a `ventas@infouno.com.ar`. Como el envío fue OK, `derivada` queda en True y un segundo `curl` con el mismo teléfono NO debe mandar otro mail (idempotencia).

- [ ] **Step 7: Commit**

```bash
git add .env.example
git commit -m "chore: variables SMTP de notificación en .env.example"
```

---

## Self-Review (completado al escribir el plan)

- **Cobertura del spec:** clasificación por departamento (Task 6), `linea_servicio` (Task 6), persistencia `derivada`/`derivada_en` (Task 5), disparo idempotente y no bloqueante (Task 7), módulo `notificaciones/` con config/email/sender (Tasks 1-4), ruteo por categoría (Task 1), toggle por `SMTP_PASSWORD` (Tasks 1/3), manejo de errores opción A (Task 7 + Task 3), config `.env` (Task 8), testing con sender inyectado (Tasks 1-3, 5). ✓
- **Sin placeholders:** todo el código está completo. ✓
- **Consistencia de tipos:** `NotifConfig.destino_para`/`.activo`, `enviar_aviso_derivacion(resultado, telefono, *, config, sender)`, `marcar_derivada(db, conversacion)`, `Categoria.desconocido` usados igual en todas las tasks. ✓
