#!/usr/bin/env bash
# ============================================================
# subir-cambios-mac.sh  (version Mac/Linux de subir-cambios-windows.ps1)
# Sube las modificaciones del proyecto a GitHub.
# Uso:   ./subir-cambios-mac.sh "descripcion de los cambios"
#   o    ./subir-cambios-mac.sh           (te pregunta la descripcion)
# ============================================================

# Ubicarse en la carpeta del proyecto (donde esta este script)
cd "$(dirname "$0")" || exit 1

mensaje="$1"

# Si no se paso mensaje, pedirlo
if [ -z "$mensaje" ]; then
  read -r -p "Describe los cambios que hiciste: " mensaje
fi

if [ -z "$mensaje" ]; then
  echo "ERROR: Necesitas escribir una descripcion de los cambios."
  exit 1
fi

echo ""
echo "Subiendo cambios a GitHub..."
echo ""
echo "Archivos modificados:"
git status --short

# Agregar todos los cambios
git add .

# Crear el commit (si no hay nada nuevo, avisar y salir)
if ! git commit -m "$mensaje"; then
  echo "No habia nada nuevo para commitear."
  exit 0
fi

# Subir a GitHub
if git push origin main; then
  echo ""
  echo "Listo! Cambios subidos a:"
  echo "https://github.com/RoberRueff/saas-chatbot-balanzas"
else
  echo ""
  echo "ERROR al subir. Revisa tu conexion o credenciales de GitHub."
  exit 1
fi
