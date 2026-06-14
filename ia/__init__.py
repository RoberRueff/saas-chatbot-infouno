"""Capa de seguridad y guardrails del chatbot.

Expone la fachada `guardrails` que orquesta los controles de entrada
(rate limit, validación, anti prompt-injection) y de salida (reglas de negocio).
"""
