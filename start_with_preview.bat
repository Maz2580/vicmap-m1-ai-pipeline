@echo off
echo Starting M1 Automation System with Data Preview...

echo.
echo Starting Main Application...
start "M1 Main App" cmd /k "cd /d %~dp0 && python app.py"

echo.
echo Starting AI Validation API...
start "AI Validation API" cmd /k "cd /d %~dp0 && python v2_m1_ai_validator/api/m1_validation_api.py"

echo.
echo Starting Preview API...
start "Preview API" cmd /k "cd /d %~dp0 && python v2_m1_ai_validator/api/preview_api.py"

echo.
echo All services started!
echo.
echo Main Application: http://localhost:5000
echo AI Validation API: http://localhost:5001
echo Preview API: http://localhost:5002
echo.
echo Press any key to exit...
pause > nul
