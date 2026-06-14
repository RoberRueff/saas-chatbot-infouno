#!/usr/bin/env bash
#
# Inicia el chatbot completo (servidor + tunel ngrok con URL fija).
# Uso:  ./iniciar-chatbot.sh
# Frenar todo:  apreta Ctrl+C en esta misma terminal.
#
set -euo pipefail

# --- Configuracion ---
PROYECTO="/Users/Rober/Desktop/Proyectos/saas chatbot balanzas"
PUERTO=8000
DOMINIO="repeal-emphases-prior.ngrok-free.dev"   # tu dominio fijo de ngrok

export PATH="$HOME/.local/bin:$PATH"
cd "$PROYECTO"

echo "============================================================"
echo "  CHATBOT BALANZAS — iniciando..."
echo "============================================================"

# Limpieza al salir: frena servidor y tunel juntos
limpiar() {
  echo ""
  echo "Frenando chatbot y tunel..."
  kill "${SERVER_PID:-}" "${NGROK_PID:-}" 2>/dev/null || true
  exit 0
}
trap limpiar INT TERM

# 1) Servidor FastAPI
echo "-> Levantando servidor en el puerto $PUERTO ..."
uv run uvicorn main:app --port "$PUERTO" > /tmp/chatbot_server.log 2>&1 &
SERVER_PID=$!

sleep 3
if ! curl -s "http://127.0.0.1:$PUERTO/" > /dev/null; then
  echo "ERROR: el servidor no arranco. Revisa /tmp/chatbot_server.log"
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
echo "   servidor OK"

# 2) Tunel ngrok con URL fija
echo "-> Abriendo tunel ngrok ..."
ngrok http "$PUERTO" --url="https://$DOMINIO" --log=/tmp/ngrok.log --log-format=logfmt > /dev/null 2>&1 &
NGROK_PID=$!

sleep 4
echo ""
echo "============================================================"
echo "  LISTO. Tu chatbot esta ONLINE."
echo ""
echo "  URL publica fija:"
echo "      https://$DOMINIO"
echo ""
echo "  Webhook para Twilio (ya configurado, no se toca mas):"
echo "      https://$DOMINIO/whatsapp"
echo ""
echo "  Manda un WhatsApp al numero del Sandbox de Twilio y probalo."
echo "  Para FRENAR todo: apreta Ctrl+C aca."
echo "============================================================"

# Mantener vivo hasta Ctrl+C
wait
