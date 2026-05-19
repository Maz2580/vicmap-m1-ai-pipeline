@echo off
echo ========================================
echo M1 Automation Web Interface
echo ========================================
echo.

REM Activate virtual environment
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    echo Virtual environment activated
) else (
    echo WARNING: Virtual environment not found!
    echo Please run: python -m venv venv
    pause
    exit
)

echo.
echo Checking dependencies...
python -c "import flask" 2>nul
if errorlevel 1 (
    echo Flask not found. Installing dependencies...
    pip install -r requirements.txt
) else (
    echo Dependencies OK
)

echo.
echo ========================================
echo Starting web server...
echo ========================================
echo.
echo Open your browser and go to:
echo.
echo     http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

REM Start the Flask app
python app.py

pause