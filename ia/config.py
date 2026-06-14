"""Parámetros ajustables de la capa de guardrails.

Todo lo configurable (umbrales, patrones, mensajes fijos) vive acá para no
tener que tocar la lógica cuando se afina el comportamiento.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Validación de entrada
# ---------------------------------------------------------------------------

# Longitud máxima de un mensaje del cliente (caracteres). Evita abuso de tokens.
MAX_LONGITUD_MENSAJE = 2000

# ---------------------------------------------------------------------------
# Rate limiting (ventana deslizante en memoria, por teléfono)
# ---------------------------------------------------------------------------

RATE_LIMIT_MAX_MENSAJES = 15      # máx. mensajes permitidos...
RATE_LIMIT_VENTANA_SEG = 60       # ...dentro de esta ventana (segundos)

# ---------------------------------------------------------------------------
# Detección de prompt injection / jailbreak (heurística, defensa en profundidad)
#
# Lista no exhaustiva: es una primera barrera barata y determinista, NO un
# sustituto del system prompt ni de un clasificador dedicado. Las regex se
# evalúan sobre el texto en minúsculas.
# ---------------------------------------------------------------------------

PATRONES_INJECTION = [
    re.compile(p)
    for p in (
        r"ignor[aá]\w*\s+(?:\w+\s+){0,3}instruc",
        r"olvid[aá]\w*\s+(?:\w+\s+){0,3}(instruc|reglas|lo anterior|todo)",
        r"(actu[aá]|comport[aá]te|hac[eé]te|fing[ií])\s+como\s+(si|un|una)\b",
        r"a partir de ahora\s+(sos|eres|act[uú]a)",
        r"\bahora\s+sos\b",
        r"(revel[aá]|mostr[aá]|repet[ií]|dec[ií]me)\w*\s+(?:\w+\s+){0,3}(prompt|system|instruc|reglas del sistema)",
        r"system\s*prompt|prompt del sistema|instrucciones del sistema",
        r"modo\s+(dan|desarrollador|sin restricciones)|jailbreak|dan mode|developer mode",
        r"ignore\s+(?:\w+\s+){0,3}instructions",
        r"disregard\s+(?:\w+\s+){0,3}(instructions|prompt|rules)",
        r"you are now\b|pretend to be\b|act as (an|a)\b",
    )
]

# ---------------------------------------------------------------------------
# Filtro de salida — reglas de negocio (#1 no precios, #2 no diagnósticos)
#
# Red de seguridad sobre la respuesta del bot. Patrones conservadores para
# minimizar falsos positivos; la detección de diagnóstico es best-effort.
# Cada entrada es (motivo, patrón) y se evalúa sobre el texto en minúsculas.
# ---------------------------------------------------------------------------

PATRONES_PROHIBIDOS_SALIDA = [
    ("precio", re.compile(r"\$\s?\d")),
    ("precio", re.compile(r"\b\d[\d.,]*\s?(pesos|d[oó]lares|usd|ars|us\$|u\$s)\b")),
    ("precio", re.compile(r"\b(cuesta|sale|vale|precio de|cotiza(?:ci[oó]n)? de|sale por)\s+\$?\s*\d")),
    ("diagnostico", re.compile(r"\bel problema es\s+(que\s+)?(el|la|los|las|un|una|tu)\b")),
    ("diagnostico", re.compile(r"\b(ten[eé]s|hay)\s+que\s+(reemplazar|cambiar|reparar)\s+(el|la|los|las|tu)\b")),
]

# ---------------------------------------------------------------------------
# Mensajes fijos al cliente cuando un guardrail bloquea / sanitiza
# ---------------------------------------------------------------------------

MSG_BLOQUEO_INJECTION = (
    "Solo puedo ayudarte con consultas sobre balanzas e instrumentos de pesaje "
    "industrial (ventas, servicio técnico o calibración). ¿En qué te puedo ayudar?"
)

MSG_ENTRADA_INVALIDA = (
    "No pude leer bien tu mensaje. ¿Podés escribirlo de nuevo, más corto?"
)

MSG_RATE_LIMIT = (
    "Estás enviando muchos mensajes muy seguido. Esperá un momentito y volvé a "
    "escribirme, por favor."
)

MSG_SALIDA_SANITIZADA = (
    "Por ese tema te va a contactar un asesor para darte la información precisa. "
    "¿Querés dejarme algún dato más (ubicación, tipo de equipo) para agilizar?"
)
