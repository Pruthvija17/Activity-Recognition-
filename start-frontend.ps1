# Starts the BAS AI React frontend on http://localhost:5173.
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1
$Frontend = Join-Path $PSScriptRoot "frontend"

Push-Location $Frontend
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
        npm install
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Write-Host "Starting BAS AI frontend on http://localhost:5173 ..." -ForegroundColor Cyan
    npm run dev
} finally {
    Pop-Location
}
