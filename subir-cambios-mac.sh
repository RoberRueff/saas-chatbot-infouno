#!/usr/bin/env bash
# ============================================================
# subir-cambios-mac.sh  (version Mac/Linux de subir-cambios-windows.ps1)
# Sube las modificaciones del proyecto a GitHub.
# Uso:   ./subir-cambios-mac.sh "descripcion de los cambios"
#   o    ./subir-cambios-mac.sh           (te pregunta la descripcion)
# ============================================================

# --- Datos de tu repo de GitHub ---
REPO_URL="https://github.com/RoberRueff/saas-chatbot-infouno.git"

# Ubicarse en la carpeta del proyecto (donde esta este script)
cd "$(dirname "$0")" || exit 1

# Asegurar que 'origin' apunte a TU repo (lo crea o lo corrige si hace falta)
if git remote get-url origin >/dev/null 2>&1; then
  if [ "$(git remote get-url origin)" != "$REPO_URL" ]; then
    git remote set-url origin "$REPO_URL"
  fi
else
  git remote add origin "$REPO_URL"
fi

# Subir SIEMPRE la rama en la que estas parado (evita pushear la rama equivocada)
RAMA="$(git branch --show-current)"
if [ -z "$RAMA" ]; then
  echo "ERROR: no estas en ninguna rama (HEAD desacoplado)."
  exit 1
fi

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
echo "Subiendo cambios a GitHub (rama: $RAMA)..."
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

# Subir a GitHub (a la rama actual, creando el upstream si no existe)
if git push -u origin "$RAMA"; then
  echo ""
  echo "Listo! Cambios subidos a:"
  echo "https://github.com/RoberRueff/saas-chatbot-infouno  (rama $RAMA)"
else
  echo ""
  echo "ERROR al subir. Revisa tu conexion o credenciales de GitHub."
  exit 1
fi
