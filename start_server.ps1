# M1 Automation Web Interface - Start Script

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "M1 Automation Web Interface" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment..." -ForegroundColor Green
    & ".\venv\Scripts\Activate.ps1"
} else {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run: python -m venv venv" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit
}

# Check if Flask is installed
Write-Host ""
Write-Host "Checking dependencies..." -ForegroundColor Yellow

try {
    python -c "import flask" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Flask not installed"
    }
    Write-Host "Dependencies OK" -ForegroundColor Green
} catch {
    Write-Host "Flask not found. Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# Check if templates folder exists
if (-not (Test-Path "templates")) {
    Write-Host ""
    Write-Host "WARNING: templates folder not found!" -ForegroundColor Red
    Write-Host "Creating templates folder..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path "templates" -Force | Out-Null
    Write-Host "Please make sure index.html is in the templates folder" -ForegroundColor Yellow
    Write-Host ""
}

# Start the server
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting web server..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Open your browser and go to:" -ForegroundColor White
Write-Host ""
Write-Host "    http://localhost:5000" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Start Flask app
python app.py