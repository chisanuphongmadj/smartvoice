@echo off
setlocal
title SmartVoice Launcher
cd /d "%~dp0"

echo.
echo ========================================
echo   SmartVoice - one-click launcher
echo ========================================
echo.

set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.11 --version >nul 2>nul && set "PY_CMD=py -3.11"
    if not defined PY_CMD py -3.10 --version >nul 2>nul && set "PY_CMD=py -3.10"
    if not defined PY_CMD py -3 --version >nul 2>nul && set "PY_CMD=py -3"
)

if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo Python was not found.
    echo Install Python 3.10 or 3.11 from https://www.python.org/downloads/
    echo Make sure "Add python.exe to PATH" is checked during install.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto error
)

set "VENV_PY=.venv\Scripts\python.exe"

if not exist ".env" (
    if exist ".env.example" (
        echo Creating .env from .env.example...
        copy ".env.example" ".env" >nul
    ) else (
        echo .env.example was not found. Continuing with built-in defaults.
    )
)

echo Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto error

echo Installing SmartVoice dependencies. This can take a while on first run...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo Installing SmartVoice package...
"%VENV_PY%" -m pip install -e . --no-deps
if errorlevel 1 goto error

where ollama >nul 2>nul
if %ERRORLEVEL%==0 (
    echo Starting Ollama in the background if it is not already running...
    start "SmartVoice Ollama" /min ollama serve
) else (
    echo.
    echo NOTE: Ollama is not installed or not in PATH.
    echo Install Ollama from https://ollama.com for real LLM analysis.
)

echo.
echo Opening SmartVoice at http://localhost:8501
echo Keep this window open while using the app.
echo.
start "" "http://localhost:8501"
"%VENV_PY%" -m streamlit run app.py --server.port 8501
goto end

:error
echo.
echo SmartVoice could not start. Check the error above.
echo If this is the first run, confirm Python 3.10/3.11 and internet access are available.
pause
exit /b 1

:end
pause
