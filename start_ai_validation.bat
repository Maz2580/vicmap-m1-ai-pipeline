@echo off
echo Starting M1 Automation System with AI Validation...
echo.

echo Starting AI Validation API on port 5001...
start "AI Validation API" cmd /k "cd /d %~dp0 && python v2_m1_ai_validator/api/m1_validation_api.py"

echo Waiting 5 seconds for API to start...
timeout /t 5 /nobreak > nul

echo Starting Main M1 Automation System on port 5000...
start "M1 Automation System" cmd /k "cd /d %~dp0 && python app.py"

echo.
echo Both services are starting...
echo - Main System: http://localhost:5000
echo - AI Validation API: http://localhost:5001
echo.
echo Press any key to exit...
pause > nul
