# Diseño — Robustez y tooling (#3 pytest, #5 SQLite WAL, #6 guarda de producción)

**Fecha:** 2026-06-15
**Estado:** Aprobado
**Rama:** feat/clasificacion-departamentos-email

Tres cambios independientes de robustez/tooling, sin decisiones de producto. Cada
uno es commiteable por separado.

---

## #3 — pytest + suite corrible

**Problema:** existen 49 tests pero no hay forma estándar de correrlos todos
juntos. `test_twilio.py` requiere pytest (usa `monkeypatch`, `pytest.raises`,
`importorskip`) y pytest no estaba declarado como dependencia ni instalado. El
resto de los archivos trae su propio runner stdlib (`python <archivo>`).

**Hecho verificado:** con pytest instalado, `pytest -q` corre los 49 tests en un
solo proceso y **pasan todos** (no hay contaminación de estado entre tests).

**Cambio:**
- Crear `requirements-dev.txt`:
  ```
  -r requirements.txt
  pytest>=8.0
  ```
- Crear `pytest.ini` (no hay pyproject):
  ```ini
  [pytest]
  testpaths = ia notificaciones seguridad
  addopts = -q
  ```
- README: agregar una sección **Tests** que documente
  `pip install -r requirements-dev.txt` y `pytest` como comando unificado.
- **No** se tocan los archivos de test: los runners stdlib (`if __name__ ==
  "__main__"`) se conservan como fallback per-archivo sin pytest.

**Verificación:** `pytest` → todos los tests pasan (49 + los que agreguen #5 y #6).

---

## #5 — SQLite WAL + busy_timeout

**Problema:** SQLite en modo journal por defecto + `check_same_thread=False` +
tareas en background (envío de email) puede dar `database is locked` bajo
concurrencia. Hoy el `engine` no setea pragmas.

**Cambio:** registrar un listener `connect` sobre el `engine` en `database.py`
que, en cada conexión nueva, aplique:
- `PRAGMA journal_mode=WAL` — permite lectores concurrentes con un escritor sin
  bloquear de inmediato.
- `PRAGMA busy_timeout=5000` — el escritor espera hasta 5 s por el lock en vez de
  fallar al toque.

El cuerpo del listener se extrae a una función nombrada
`_aplicar_pragmas_sqlite(dbapi_conn, record)` y se registra con
`event.listen(engine, "connect", _aplicar_pragmas_sqlite)`, para poder testearla
sobre un engine de archivo temporal.

**Nota:** WAL no aplica a bases `:memory:` (reportan `memory`); por eso el test
usa un archivo temporal. WAL es idempotente: re-setearlo en cada connect no hace
daño; `busy_timeout` es por conexión, así que debe setearse siempre.

**Tests** (`notificaciones/tests/test_db_pragmas.py`, runner stdlib + pytest):
1. Sobre un engine de archivo temporal con el listener: `PRAGMA journal_mode` ==
   `wal` y `PRAGMA busy_timeout` == `5000`.

---

## #6 — Guarda de configuración de producción (fail-fast)

**Problema:** el fail-closed de Twilio ([seguridad/twilio.py](../../../seguridad/twilio.py))
y la auth de `/chat` dependen de que existan `TWILIO_AUTH_TOKEN` y
`APP_SECRET_KEY`. Si un deploy de producción arranca sin ellas, el servicio queda
mal configurado de forma silenciosa (p. ej. Twilio en modo dev fail-open si
además `APP_ENV` no es `production`).

**Cambio:** una guarda al arrancar la app que, **solo cuando
`APP_ENV=production`**, rechaza el arranque si falta algún secreto crítico
(fail-fast con mensaje claro). Protege cualquier método de deploy, no solo el
script local.

En `main.py`:
```python
SECRETOS_REQUERIDOS_PROD = ("APP_SECRET_KEY", "TWILIO_AUTH_TOKEN", "GEMINI_API_KEY")


def _validar_config_produccion() -> None:
    """En producción, no arrancar si falta un secreto crítico (fail-fast)."""
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

Se llama al inicio de `lifespan`, antes de `init_db()`. Un `RuntimeError` en el
startup de lifespan aborta el arranque de uvicorn con el mensaje (fail-fast).

**Tests** (`seguridad/tests/test_config_prod.py`, runner stdlib + pytest; guardan
y restauran `os.environ` para no contaminar otros tests):
1. `APP_ENV` != production → no lanza aunque falten secretos.
2. `APP_ENV=production` + falta uno → lanza `RuntimeError` que nombra el faltante.
3. `APP_ENV=production` + todos presentes → no lanza.

---

## Fuera de alcance

- No se migra a Postgres (WAL alcanza para el volumen del MVP).
- No se reescribe el flujo de instalación del README a `uv` (inconsistencia
  preexistente, ajena a esta tanda).
- No se toca `iniciar-chatbot.sh` (elegimos la guarda a nivel app, que cubre todo
  método de arranque).
