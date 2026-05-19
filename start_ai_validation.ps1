# PowerShell script to start M1 Automation System with AI Validation
Write-Host "Starting M1 Automation System with AI Validation..." -ForegroundColor Green
Write-Host ""

# Start AI Validation API on port 5001
Write-Host "Starting AI Validation API on port 5001..." -ForegroundColor Yellow
Start-Process -FilePath "python" -ArgumentList "v2_m1_ai_validator/api/m1_validation_api.py" -WindowStyle Normal

# Wait for API to start
Write-Host "Waiting 5 seconds for API to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Start Main M1 Automation System on port 5000
Write-Host "Starting Main M1 Automation System on port 5000..." -ForegroundColor Yellow
Start-Process -FilePath "python" -ArgumentList "app.py" -WindowStyle Normal

Write-Host ""
Write-Host "Both services are starting..." -ForegroundColor Green
Write-Host "- Main System: http://localhost:5000" -ForegroundColor Cyan
Write-Host "- AI Validation API: http://localhost:5001" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
