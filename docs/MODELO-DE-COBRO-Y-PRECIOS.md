# Modelo de cobro y precios — SaaS Chatbot (mercado pymes Argentina)

> Documento de referencia comercial. Última actualización: 2026-06-15.
> Tipo de cambio usado en este documento: dólar blue/MEP ≈ **$1.450 ARS/USD** (15-jun-2026).
> Regla general: **cotizar en USD, facturar en pesos del día** y ajustar mensualmente por inflación.

---

## 1. Formas de cobrar (modelos disponibles)

| # | Modelo | En qué consiste | Cuándo conviene | Contras |
|---|--------|-----------------|-----------------|---------|
| 1 | **Suscripción por planes** | Cuota fija mensual según tier con límites (conversaciones, canales, agentes) | Base del negocio; ingresos predecibles (MRR) | Hay que diseñar bien los límites |
| 2 | **Por uso / consumo** | Por conversación, mensaje o tokens de IA | Cuando el coste variable es alto (IA, WhatsApp) | Ingreso menos predecible; miedo a "factura sorpresa" |
| 3 | **Híbrido (cuota + excedente)** | Cuota fija con cupo incluido + pago por excedente | **Recomendado** para chatbots con IA | Requiere medir consumo |
| 4 | **Por agente / asiento** | Precio por cada usuario del cliente | Clientes con equipos grandes | Penaliza la automatización (menos agentes = más éxito) |
| 5 | **Por resultado / valor** | Pago por conversación resuelta o lead generado | Muy vendible, alta alineación | Difícil de medir/atribuir; riesgo propio |
| 6 | **Setup + recurrente** | Cobro inicial único de implantación + mensualidad | Cuando hay integración/personalización (ej. clasificación de email) | — |
| 7 | **Enterprise / a medida** | Contrato anual, precio negociado, SLA, on-prem/data residency | Clientes grandes | Ciclo de venta largo |

**Modelo elegido para este producto:** **híbrido por planes + excedente**, con **setup opcional** para cuentas que pidan integración.

---

## 2. Lista de precios — ajustada a la plaza pyme Argentina (RECOMENDADO)

Referencias de competencia local: Wasapi desde ~30 USD, Whaticket ~49 USD, Cliengo 59–199 USD.

> **Cupos corregidos (2026-06-15):** los cupos de conversaciones se recalcularon para que cada plan
> deje ~55-57% de margen bruto con el costo actual de WhatsApp/Twilio (~$0,034/conv, ver sección 5).
> Los cupos anteriores (Starter 1.000 / Pro 5.000 / Business ilimitado) daban margen negativo.

| Plan | USD/mes | ARS/mes (al blue) | Conv. incluidas | Costo est. | Margen bruto | Incluye |
|------|---------|-------------------|-----------------|-----------|--------------|---------|
| **Starter** | 30 USD | ~$43.500 | **400** | ~$13,6 | ~55% | 1 canal, bot por reglas |
| **Pro** | 79 USD | ~$115.000 | **1.000** | ~$34 | ~57% | 3 canales, clasificación de email + IA |
| **Business** | 199 USD | ~$290.000 | **2.500** | ~$85 | ~57% | canales ilimitados, SLA, retención configurable |
| **Enterprise** | a medida | negociado | a medida | — | — | on-prem / data residency / soporte dedicado |
| **Setup (única vez)** | 300–1.500 USD | ~$435.000 – $2.175.000 | — | — | — | integración + onboarding |

**Excedente:** **~0,06 USD por conversación extra (~$87 ARS)** — cubre el costo (~$0,034) + margen.

> **Nota:** el cupo "Business" ya no es ilimitado: con costo por conversación, "ilimitado" es un riesgo
> de margen. Se fija un tope (2.500) + excedente. La forma definitiva de poder ofrecer cupos altos y
> baratos es el **Cambio 2** (migrar a WhatsApp Cloud API de Meta directo), que baja el costo ~10×.

---

## 3. Lista de precios — referencia "premium" (conversión directa en euros)

Set original pensado para mercados de mayor poder adquisitivo. Sirve como techo / referencia para clientes grandes.

| Plan | Precio orig. | ≈ USD | ≈ ARS/mes |
|------|--------------|-------|-----------|
| Starter | 49 € | ~53 USD | ~$77.000 |
| Pro | 149 € | ~161 USD | ~$233.000 |
| Business | 399 € | ~431 USD | ~$625.000 |
| Setup (única vez) | 500–5.000 € | 540–5.400 USD | ~$780.000 – $7.800.000 |

---

## 4. Reglas prácticas para vender en Argentina

- **Cotizar en USD, facturar en pesos del día** (dólar MEP/tarjeta). Evita que la inflación licúe el precio. En B2C local se puede mostrar en pesos pero con cláusula de ajuste mensual.
- **Sumar IVA 21%** al facturar formalmente a empresas (las cifras de este doc son sin IVA).
- **Plan anual con descuento** (~2 meses gratis) cobrado por adelantado: mejora la caja en contexto inflacionario y reduce churn.
- **Repercutir el coste variable real**: tokens de IA + WhatsApp Business API se pagan en USD por conversación. Aunque cobres en pesos, ese coste es en dólares → protegerlo en el precio.
- **Punto de entrada**: el Starter en USD 30 es el ancla psicológica de la pyme chica. El salto grande de facturación se hace en Pro/Business.
- **Empezar simple** (2–3 planes) y agregar granularidad cuando haya datos reales de uso.

---

## 5. Coste por conversación (metodología y cálculo)

> Esto es lo que nos cuesta operar **cada conversación**. Sirve para validar que cada plan deje margen.
> Basado en la arquitectura real del bot (ver `docs/COMO-FUNCIONA-EL-CHATBOT.md`).

### Fórmula

```
Coste por conversación = Coste IA (Gemini) + Coste WhatsApp (Twilio) + Email (≈$0)
```

El email es SMTP propio (`mail.infouno.com.ar`) → **$0**. Quedan dos componentes.

### Componente 1 — IA (Gemini 2.5 Flash)

- Precio (jun-2026): **$0,30 / millón de tokens de entrada** y **$2,50 / millón de salida**.
- El bot hace **1 llamada a Gemini por cada mensaje del cliente**. Cada llamada envía:
  SYSTEM_PROMPT + historial (hasta 30 mensajes) + mensaje nuevo, y devuelve un JSON.
- **Cómo medir los tokens REALES (exacto, no estimado):** la respuesta de `google-genai` trae
  `response.usage_metadata` con `prompt_token_count` y `candidates_token_count`. Loguear esos dos
  valores en `main.py` tras cada llamada a Gemini durante ~1 semana → consumo real por conversación.

```
Coste IA = (tokens_entrada × 0,30/1.000.000) + (tokens_salida × 2,50/1.000.000)
```

### Componente 2 — WhatsApp (Twilio)

- Twilio cobra **$0,005 por mensaje** (entrante o saliente).
- El bot es **reactivo** (el cliente escribe primero) → todos los mensajes caen en la **ventana de
  servicio de 24 h**, donde **Meta NO cobra su fee**. Solo se paga el $0,005 de Twilio.

```
Coste WhatsApp = (mensajes_cliente + respuestas_bot) × 0,005
```

### Cálculo de ejemplo — conversación típica (3 idas y vueltas)

Supuestos: 3 mensajes del cliente (3 llamadas Gemini) · 6 mensajes WhatsApp totales ·
~5.400 tokens de entrada acumulados · ~750 tokens de salida.

| Componente | Cálculo | USD |
|---|---|---|
| IA — entrada | ~5.400 × $0,30/M | $0,0016 |
| IA — salida | ~750 × $2,50/M | $0,0019 |
| WhatsApp | 6 msgs × $0,005 | $0,0300 |
| Email | SMTP propio | $0,0000 |
| **TOTAL** | | **~$0,034 USD ≈ $49 ARS** |

**Rango realista según largo de charla: $0,03–0,07 USD/conversación (~$50–100 ARS).**

### ⚠️ Hallazgo clave: el coste lo domina WhatsApp, no la IA

- WhatsApp/Twilio ≈ **88%** del coste; Gemini ≈ **12%**. La IA es casi gratis.
- **Impacto en el plan Starter:** 30 USD/mes con 1.000 conversaciones incluidas →
  coste 1.000 × $0,034 = **$34** → **margen NEGATIVO**. Hay que corregirlo.

### Dos palancas de margen

1. **Bajar el cupo del Starter** a ~500 conversaciones (o subir el precio).
2. **Migrar de Twilio a la WhatsApp Cloud API de Meta directo.** Elimina el $0,005 de Twilio y, en
   ventana de servicio, Meta no cobra → el coste cae a **solo la IA (~$0,0035/conv)**, ~**10× más
   barato**. 1.000 conversaciones pasarían de $34 a **~$3,50**. Es la mayor mejora de margen disponible.

---

## 6. Pendiente / próximos pasos

- [x] Definir **metodología de coste por conversación** (ver sección 5).
- [ ] **Medir tokens reales** logueando `usage_metadata` de Gemini durante ~1 semana.
- [x] **Corregir cupos de los planes** (Starter 400 / Pro 1.000 / Business 2.500 + excedente) — ver sección 2.
- [ ] Evaluar **migración Twilio → WhatsApp Cloud API de Meta directo** (palanca 10× de margen).
- [ ] Armar **calculadora de margen** (coste por conversación vs. precio del plan).
- [ ] Confirmar tratamiento impositivo (IVA, percepciones) con contador.
- [ ] Revisar tipo de cambio y actualizar tabla ARS periódicamente.

---

## Fuentes (consultadas 2026-06-15)

- [El Destape — cotización dólar 15 junio 2026](https://www.eldestapeweb.com/economia/cuanto-cotiza-dolar-feriado-20266158352)
- [Página12 — dólar 12 junio 2026](https://www.pagina12.com.ar/2026/06/12/dolar-blue-dolar-hoy-a-cuanto-cotizan-el-viernes-12-de-junio-de-2026/)
- [Artics — precios chatbot IA Argentina 2026](https://www.artics.com.ar/cuanto-cuesta-chatbot-ia-para-empresas-argentina/)
- [SODI — cuánto cuesta un bot de WhatsApp 2026](https://www.sodi.com.ar/blog/cuanto-cuesta-bot-whatsapp-empresas)
- [Basework — WhatsApp Business API Argentina 2026](https://www.basework.com.ar/blog/whatsapp-business-api-argentina)
- [Gemini 2.5 Flash — precios por token (Google AI)](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini 2.5 Flash — pricepertoken](https://pricepertoken.com/pricing-page/model/google-gemini-2.5-flash)
- [Twilio — WhatsApp pricing](https://www.twilio.com/en-us/whatsapp/pricing)
- [Twilio — costo de mensajes WhatsApp (Help Center)](https://help.twilio.com/articles/360037672734-How-Much-Does-it-Cost-to-Send-and-Receive-WhatsApp-Messages-with-Twilio-)
