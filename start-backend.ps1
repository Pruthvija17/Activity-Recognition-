# Starts the BAS AI FastAPI backend on http://127.0.0.1:8000 using the project-root .venv.
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
param(
    [int]$Port = 8000,
    [switch]$Reload
)

$Root = $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Python environment not found at $Python" -ForegroundColor Red
    Write-Host "Create it with:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\python -m pip install -r backend\requirements.txt"
    exit 1
}

& $Python -c "import fastapi, uvicorn, cv2, ultralytics" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Required packages are missing from .venv. Run:" -ForegroundColor Red
    Write-Host "  .venv\Scripts\python -m pip install -r backend\requirements.txt"
    exit 1
}

$UvicornArgs = @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) { $UvicornArgs += "--reload" }

Write-Host "Starting BAS AI backend on http://127.0.0.1:$Port ..." -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend")
try {
    & $Python @UvicornArgs
} finally {
    Pop-Location
}
