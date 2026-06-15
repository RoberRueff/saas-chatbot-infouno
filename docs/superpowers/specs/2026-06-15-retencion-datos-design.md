# Diseño — Retención de datos (purga por antigüedad + borrado a pedido)

**Fecha:** 2026-06-15
**Estado:** Aprobado
**Rama:** feat/clasificacion-departamentos-email

## Problema

El chatbot guarda datos personales (número de teléfono y mensajes) en SQLite sin
ninguna política de retención: hoy se conservan indefinidamente. La Ley 25.326
(art. 4 inc. 7) ordena destruir los datos cuando dejan de ser necesarios para el
fin con que se recolectaron, y reconoce el derecho de supresión a pedido del
titular (art. 16).

## Investigación legal (resumen)

Verificado con deep-research (fuentes oficiales: Infoleg, argentina.gob.ar, AAIP,
OAS, MPF):

- **No hay plazo mínimo** de conservación en la 25.326; rige la **conservación
  limitada** (art. 4 inc. 7).
- **Ni el CCyC art. 328 ni la Ley 11.683** obligan a retener el chat: esos
  plazos (10 años) atan a libros, registros e **instrumentos respaldatorios /
  comprobantes de operaciones** (facturas, recibos), no a un chat de pre-venta
  sin factura. Prescripción fiscal general: 5 años (art. 56 Ley 11.683).
- El caso **"Torres Abad"** (cesión estatal de datos sin consentimiento) **no
  cambia** el diseño; si existe el fallo CSJN 2026 (no confirmado con fuente
  primaria), refuerza minimización/consentimiento.

→ Conclusión: la app puede (y debe) **purgar por finalidad cumplida** y permitir
el **borrado a pedido**.

## Decisiones (acordadas)

- **Umbral de retención:** 6 meses (`RETENCION_DIAS = 180`) desde la última
  actividad de la conversación.
- **Borrado a pedido:** endpoint de admin por teléfono, protegido con X-API-Key.
- **Cuándo purga:** al arrancar la app + tarea en background cada 24 h.

## Componentes

### 1. Regla de retención

"Última actividad" = fecha del último mensaje, o `fecha_creacion` si no hay
mensajes (reusa `_ultima_actividad` / `_as_utc` de la feature #1). Una
conversación es purgable si `ahora - última_actividad >= timedelta(days=180)`.
Purgar = borrar la `Conversacion` **y sus `HistorialMensaje`** (el teléfono vive
en la conversación, se elimina con ella).

### 2. `database.py` — funciones nuevas

```python
RETENCION_DIAS = 180  # 6 meses; conservación limitada (Ley 25.326 art. 4 inc. 7)


def purgar_conversaciones_antiguas(db, ahora=None) -> int:
    """Borra conversaciones (y sus mensajes) con última actividad >= RETENCION_DIAS.
    Devuelve cuántas borró. `ahora` es inyectable para tests."""


def borrar_datos_telefono(db, telefono) -> int:
    """Borra TODO lo de un teléfono (conversaciones + mensajes). Derecho de
    supresión (Ley 25.326 art. 16). Devuelve cuántas conversaciones borró."""
```

Implementación: juntar los `id` a borrar, eliminar primero los
`HistorialMensaje` con `conversacion_id IN (ids)` y luego las `Conversacion`
(no hay cascade configurado), un solo commit.

### 3. `main.py` — endpoint de admin

`POST /admin/borrar-datos`, dependencia `verificar_api_key` (mismo X-API-Key que
`/chat`). Body Pydantic `{"telefono": "..."}`. Respuesta:
`{"telefono": "...", "conversaciones_borradas": n}`. Se usa body (no path param)
para no URL-encodear el `+` del teléfono.

### 4. `main.py` — purga automática en `lifespan`

- Tras `init_db()`: una **purga inicial** (con `Session(engine)` propia), errores
  logueados, nunca tumban el arranque.
- Tarea en background `asyncio.create_task(_loop_purga())` que cada 24 h corre la
  purga; se cancela en el shutdown del lifespan. Cada iteración captura y loguea
  excepciones.

```python
INTERVALO_PURGA_SEG = 24 * 60 * 60


async def _loop_purga() -> None:
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

## Tests

- `purgar_conversaciones_antiguas`: con `ahora` inyectado, borra las ≥180 días,
  deja las recientes, y elimina también sus `HistorialMensaje`; devuelve el
  conteo correcto. Caso borde: conversación vieja sin mensajes (usa
  `fecha_creacion`) → se purga.
- `borrar_datos_telefono`: borra todas las conversaciones + mensajes de un
  teléfono y no toca los de otro teléfono; devuelve el conteo.
- Endpoint `/admin/borrar-datos`: sin API key → 401; con API key → 200 y borra.
- Runner stdlib del repo (colectable por pytest); Session SQLite en memoria;
  endpoint vía `TestClient` con monkeypatch del borrado (patrón de
  `test_chat_auth.py`).
- La **purga periódica** (timing del `asyncio`) no se testea por reloj; se cubre
  testeando `purgar_conversaciones_antiguas` y dejando el scheduling como glue
  fino.

## Edge

Una conversación en modo humano o ya derivada que cumple 180 días **igual se
purga** (el caso ya terminó). Correcto.

## Fuera de alcance (notas legales/operativas, NO código)

- **Aviso de privacidad** (Ley 25.326 art. 6): obligación real de informar
  finalidad, responsable y derechos al recabar. Queda anotado como pendiente
  operativo (p. ej. una línea en el primer mensaje o en la web).
- **Registro de la base ante la AAIP** (arts. 21/24): trámite administrativo, no
  código.
- Detección de pedido de borrado **en el chat** (autoservicio): descartado en
  favor del endpoint de admin, que cubre pedidos por cualquier canal.
