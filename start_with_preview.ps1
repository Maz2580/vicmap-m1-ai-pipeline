# Start M1 Automation System with Data Preview
Write-Host "Starting M1 Automation System with Data Preview..." -ForegroundColor Green

Write-Host ""
Write-Host "Starting Main Application..." -ForegroundColor Yellow
Start-Process -FilePath "cmd" -ArgumentList "/k", "cd /d $PWD && python app.py" -WindowStyle Normal

Write-Host ""
Write-Host "Starting AI Validation API..." -ForegroundColor Yellow
Start-Process -FilePath "cmd" -ArgumentList "/k", "cd /d $PWD && python v2_m1_ai_validator/api/m1_validation_api.py" -WindowStyle Normal

Write-Host ""
Write-Host "Starting Preview API..." -ForegroundColor Yellow
Start-Process -FilePath "cmd" -ArgumentList "/k", "cd /d $PWD && python v2_m1_ai_validator/api/preview_api.py" -WindowStyle Normal

Write-Host ""
Write-Host "All services started!" -ForegroundColor Green
Write-Host ""
Write-Host "Main Application: http://localhost:5000" -ForegroundColor Cyan
Write-Host "AI Validation API: http://localhost:5001" -ForegroundColor Cyan
Write-Host "Preview API: http://localhost:5002" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor White
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
