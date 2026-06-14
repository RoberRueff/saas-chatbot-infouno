# ============================================================
# subir-cambios-windows.ps1
# Sube las modificaciones del proyecto a GitHub (Windows / PowerShell)
# Uso: .\subir-cambios-windows.ps1 "descripcion de los cambios"
# ============================================================

param(
    [string]$mensaje = ""
)

# Si no se paso mensaje, pedirlo
if ($mensaje -eq "") {
    $mensaje = Read-Host "Describe los cambios que hiciste"
}

if ($mensaje -eq "") {
    Write-Host "ERROR: Necesitas escribir una descripcion de los cambios." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Subiendo cambios a GitHub..." -ForegroundColor Cyan

# Ver que archivos cambiaron
Write-Host ""
Write-Host "Archivos modificados:" -ForegroundColor Yellow
git status --short

# Agregar todos los cambios
git add .

# Crear el commit
git commit -m $mensaje

if ($LASTEXITCODE -ne 0) {
    Write-Host "No habia nada nuevo para commitear." -ForegroundColor Yellow
    exit 0
}

# Subir a GitHub
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Listo! Cambios subidos a:" -ForegroundColor Green
    Write-Host "https://github.com/RoberRueff/saas-chatbot-balanzas" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "ERROR al subir. Revisa tu conexion o credenciales de GitHub." -ForegroundColor Red
}
