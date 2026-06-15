# Diseño — Clasificación por departamento y notificación por email al derivar

**Fecha:** 2026-06-15
**Estado:** Aprobado — pendiente de implementación
**Relacionado:** [2026-06-13-derivacion-casos-design.md](2026-06-13-derivacion-casos-design.md)
(panel `/casos` y `estado_humano`, que quedan para después)

## Problema

Hoy el bot clasifica por **línea de servicio** (`Automatización con IA` /
`Desarrollo Web`), pero ambas son en la práctica leads comerciales. Cuando el bot
reúne la info mínima marca `notificar_recepcion=True` y no pasa nada: el caso no
sale del bot. infouno necesita que cada caso, al quedar listo, **se derive por
email al departamento que corresponde**: Comercial/Ventas, Administración o
Servicio Técnico.

Esos tres departamentos son un **eje distinto** de IA-vs-Web: no es "qué servicio
querés" sino "qué área te atiende". Por lo tanto, para rutear bien, el bot tiene
que clasificar por **departamento**.

## Objetivo

1. Reclasificar la conversación por departamento (Comercial/Ventas,
   Administración, Servicio Técnico, Desconocido).
2. Cuando el caso queda listo para derivar, enviar **un** email al departamento
   correspondiente, **una sola vez** por caso, sin romper la respuesta al cliente.

## Fuera de alcance

- Panel `GET /casos` y traspaso a `estado_humano` (viven en el spec de derivación).
- `resumen_json` y otros campos de ese spec que no necesita el email.
- Más de un destinatario por caso, CC/BCC, plantillas HTML elaboradas.

## Diseño

### 1. Clasificación por departamento (`main.py`)

`Categoria` se reemplaza:

| Valor del enum            | Email destino                       | Cuándo aplica |
|---------------------------|-------------------------------------|---------------|
| `Comercial/Ventas`        | `ventas@infouno.com.ar`             | Prospecto nuevo que quiere cotizar/contratar (automatización IA o web). El grueso. |
| `Administración`          | `administracion@infouno.com.ar`     | Facturación, pagos, comprobantes, datos fiscales, contrato. |
| `Servicio Técnico`        | `servicio.tecnico@infouno.com.ar`   | Cliente existente con problema/soporte sobre algo ya entregado. |
| `Desconocido`             | — (no envía)                        | Ambiguo o fuera de tema → pide aclaración. |

El `SYSTEM_PROMPT` se reescribe para clasificar según esas definiciones. infouno
sigue siendo agencia de automatización con IA + desarrollo web; eso ahora se
captura en un campo (`linea_servicio`), no en la categoría.

### 2. Schema `RespuestaChatbot` (`main.py`)

- Se mantienen: `categoria`, `ubicacion`, `nombre_empresa`, `rubro`, `necesidad`,
  `info_faltante`, `respuesta_al_cliente`, `notificar_recepcion`.
- **Nuevo** `linea_servicio: Optional[str]` — `"Automatización con IA"`,
  `"Desarrollo Web"` o `None`. Aplica sobre todo a casos comerciales; es un dato,
  no afecta el ruteo.

**Info mínima para derivar (marca `notificar_recepcion=True`):**
- Comercial/Ventas: `necesidad` + `rubro` + `ubicacion`
- Administración: `nombre_empresa` + `necesidad` (qué trámite)
- Servicio Técnico: `nombre_empresa` + `necesidad` (qué problema, sobre qué proyecto)

### 3. Persistencia — disparador e idempotencia (`database.py`)

A `Conversacion` se agregan:

| Campo | Tipo | Default | Uso |
|---|---|---|---|
| `derivada` | `bool` | `False` | Marca que el caso ya fue notificado por email. Evita reenvíos. |
| `derivada_en` | `datetime \| None` | `None` | Momento del envío exitoso (UTC). |

La DB está vacía (se limpió antes), así que `init_db()` / `create_all` recrea la
tabla con las columnas nuevas borrando `chatbot.db`. **No hay migración**; si en el
futuro la tabla tuviera datos, habría que hacer `ALTER TABLE`.

> Nota: estos son los mismos campos que define el spec de derivación. Acá se
> introducen como prerequisito del email; el panel y `estado_humano` se suman
> después sobre el mismo modelo.

### 4. Lógica de envío (`_procesar_mensaje` en `main.py`)

Después de obtener la respuesta de Gemini y pasar el guardrail de salida, y luego
de persistir los mensajes (user + assistant):

```
si resultado.notificar_recepcion y not conversacion.derivada y categoria != Desconocido:
    ok = notificaciones.enviar_aviso_derivacion(resultado, telefono)
    si ok:
        conversacion.derivada = True
        conversacion.derivada_en = datetime.now(timezone.utc)
        db.commit()
```

**Manejo de errores (opción A):** se marca `derivada=True` **solo si el email se
envió OK**. Si falla, la conversación queda sin marcar y **reintenta en el próximo
mensaje del cliente**. El envío es **no bloqueante**: `enviar_aviso_derivacion`
captura cualquier excepción, la loguea y devuelve `False` — el cliente recibe su
respuesta por WhatsApp aunque el mail falle.

Limitación conocida (aceptada para esta etapa): si el envío falla y el cliente no
vuelve a escribir, el caso queda sin derivar hasta que exista el panel de casos.

### 5. Módulo aislado `notificaciones/`

Mismo patrón que `ia/` y `seguridad/`: `main.py` solo importa la fachada.

| Archivo | Responsabilidad |
|---|---|
| `notificaciones/config.py` | Mapa `categoría → email`, remitente, toggle (lee de env). Único lugar a tocar para cambiar casillas. |
| `notificaciones/email.py` | `enviar_aviso_derivacion(resultado, telefono) -> bool`: arma asunto + cuerpo, resuelve el destino, llama al sender. Captura errores y nunca propaga. |
| `notificaciones/sender.py` | Adapter fino sobre `smtplib` (`SMTP_SSL` a `mail.infouno.com.ar:465`). Inyectable para tests. |

**Contenido del email**
- Asunto: `[infouno] {categoria}: {nombre_empresa or telefono}`
- Cuerpo (texto plano): categoría · empresa · rubro · línea de servicio · necesidad ·
  ubicación · teléfono del cliente · fecha.

**Comportamiento del toggle:** si `SMTP_PASSWORD` está vacío, la notificación
queda **desactivada** (loguea un aviso y devuelve `False`), igual que el patrón de
`TWILIO_AUTH_TOKEN`. Permite correr en local sin enviar mails.

### 6. Config nueva (`.env` y `.env.example`)

Envío vía el **SMTP propio** de infouno (`mail.infouno.com.ar`, puerto 465
SSL/TLS). Los tres destinos son `@infouno.com.ar`, así que es correo interno —
entrega confiable, sin verificación de dominio ni servicios de terceros.

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

`SMTP_USER` es la cuenta de correo que envía (debe existir en el servidor) y suele
coincidir con `NOTIF_EMAIL_FROM`. El envío usa `smtplib` de la stdlib: **no se
agregan dependencias** a `requirements.txt`.

## Testing (TDD)

Con un **sender inyectado** (sin abrir una conexión SMTP de verdad):

1. **Ruteo correcto:** cada categoría resuelve a su casilla; `Desconocido` no envía.
2. **Armado del email:** asunto y cuerpo contienen los campos esperados
   (categoría, empresa/teléfono, necesidad, etc.) — función pura.
3. **Enviar una sola vez:** dos llamadas con `notificar_recepcion=True` sobre la
   misma conversación derivan un único email (idempotencia por `derivada`).
4. **Desactivado sin credenciales:** con `SMTP_PASSWORD` vacío no se intenta
   enviar y se devuelve `False`.
5. **Falla no rompe ni marca:** si el sender lanza/devuelve error, `derivada`
   queda en `False` y la respuesta al cliente igual se produce.

Los tests del módulo `notificaciones/` no deben requerir red ni la API real.

## Criterios de éxito

1. El bot clasifica en Comercial/Ventas, Administración, Servicio Técnico o
   Desconocido, y captura `linea_servicio` cuando aplica.
2. Al marcar `notificar_recepcion=True`, se envía un email al departamento
   correcto, una sola vez por caso.
3. Un fallo de email no rompe la respuesta al cliente ni marca el caso como
   derivado (reintenta en el próximo mensaje).
4. Sin `SMTP_PASSWORD`, el bot funciona igual y no intenta enviar.
5. Tests de `notificaciones/` verdes sin acceso a red; tests existentes
   actualizados a las categorías nuevas.
