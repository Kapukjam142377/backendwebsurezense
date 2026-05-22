@echo off
echo ===================================================
echo   Surazense Cancer Report Backend Setup ^& Launcher
echo ===================================================

cd /d "%~dp0"

REM Detect Python executable using goto logic to avoid batch parentheses expansion bugs
set PYTHON_CMD=python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Detected Python python.exe
    goto python_found
)

py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    echo [INFO] Detected Python Launcher py.exe
    goto python_found
)

echo [ERROR] Python is not installed or not in PATH!
echo Please install Python and try again.
pause
exit /b 1

:python_found
echo [INFO] Python command selected: %PYTHON_CMD%

REM Create virtual environment if it doesn't exist
if not exist venv (
    echo [INFO] Creating Python virtual environment...
    %PYTHON_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
)

REM Activate virtual environment and install packages
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

echo [INFO] Installing required python libraries...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements!
    pause
    exit /b 1
)

echo [INFO] Launching FastAPI backend server on port 5000...
echo [INFO] Swagger Docs will be available at http://localhost:5000/docs
uvicorn main:app --reload --port 5000

pause
