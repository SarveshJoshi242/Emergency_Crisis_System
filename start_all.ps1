$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "============================================================"
Write-Host "  Emergency Management System -- Startup"
Write-Host "============================================================"
Write-Host "[SETUP] Checking and installing Python dependencies..."
pip install -r "$Root\staff backend\requirements.txt" | Out-Null
pip install "pydantic[email]" | Out-Null
Write-Host "[SETUP] Dependencies checked."
Write-Host ""

function Start-Service {
    param(
        [string]$Title,
        [string]$WorkDir,
        [string]$Command
    )
    Write-Host "[START] $Title"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$WorkDir'; `$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
}

# 1. Guest Backend (port 8000)
Start-Service `
    -Title   "Guest Backend :8000" `
    -WorkDir "$Root\guest_backend" `
    -Command "python run.py"

Start-Sleep -Milliseconds 600

# 2. Staff Backend (port 8001)
Start-Service `
    -Title   "Staff Backend :8001" `
    -WorkDir "$Root\staff backend" `
    -Command "python run.py"

Start-Sleep -Milliseconds 600

# 3. Fire Risk API (port 8002)
Start-Service `
    -Title   "Fire Risk API :8002" `
    -WorkDir "$Root\fire_risk" `
    -Command "python -m uvicorn api:app --host 0.0.0.0 --port 8002 --reload"

Start-Sleep -Milliseconds 600

# 4. Frontend (port 5173)
Start-Service `
    -Title   "Frontend :5173" `
    -WorkDir "$Root\sign in_up_frontend" `
    -Command "npm run dev"

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host "  All services starting in separate windows."
Write-Host ""
Write-Host "  Guest Backend   --> http://localhost:8000/docs"
Write-Host "  Staff Backend   --> http://localhost:8001/docs"
Write-Host "  Fire Risk API   --> http://localhost:8002/docs"
Write-Host "  Frontend        --> http://localhost:5173"
Write-Host "------------------------------------------------------------"
Write-Host ""
