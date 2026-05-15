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

for /f "delims=" %%A in ('"%VENV_PY%" -c "import sys; print(str(sys.version_info.major) + '.' + str(sys.version_info.minor))"' ) do set "PY_VERSION=%%A"
for /f "delims=" %%A in ('"%VENV_PY%" -c "import torch; print(torch.__version__)"' ) do set "TORCH_VERSION=%%A"
for /f "delims=" %%A in ('"%VENV_PY%" -c "import torch; print(torch.version.cuda or '')"' ) do set "TORCH_CUDA_VERSION=%%A"
for /f "delims=" %%A in ('"%VENV_PY%" -c "import torch; print(torch.cuda.is_available())"' ) do set "TORCH_CUDA_AVAILABLE=%%A"

set "CONFIGURED_DEVICE=auto"
if exist ".env" (
    for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"WHISPER_DEVICE=" ".env"') do set "CONFIGURED_DEVICE=%%B"
)

set "NVIDIA_GPU=0"
set "NVIDIA_CUDA_VERSION="
where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    nvidia-smi >nul 2>nul
    if not errorlevel 1 set "NVIDIA_GPU=1"
)
if "%NVIDIA_GPU%"=="1" (
    for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$out = (& nvidia-smi 2>$null | Out-String); if ($out -match 'CUDA Version:\s*([0-9.]+)') { $matches[1] }"`) do set "NVIDIA_CUDA_VERSION=%%A"
)

set "CUDA_WHEEL_TAG="
if defined NVIDIA_CUDA_VERSION (
    for /f "delims=" %%A in ('"%VENV_PY%" -c "from smartvoice.preflight import recommend_cuda_wheel_tag; import sys; print(recommend_cuda_wheel_tag(sys.argv[1]) or '')" "%NVIDIA_CUDA_VERSION%"') do set "CUDA_WHEEL_TAG=%%A"
)

echo.
echo Environment check
echo   Python: %PY_VERSION%
echo   PyTorch: %TORCH_VERSION%
echo   PyTorch CUDA build: %TORCH_CUDA_VERSION%
echo   PyTorch CUDA usable: %TORCH_CUDA_AVAILABLE%
if "%NVIDIA_GPU%"=="1" (
    echo   NVIDIA GPU: detected
    echo   NVIDIA driver CUDA support: %NVIDIA_CUDA_VERSION%
) else (
    echo   NVIDIA GPU: not detected
)
echo   Configured WHISPER_DEVICE: %CONFIGURED_DEVICE%

if not "%PY_VERSION%"=="3.10" if not "%PY_VERSION%"=="3.11" (
    echo.
    echo WARNING: SmartVoice is tested on Python 3.10 or 3.11.
    echo          Install Python 3.11 if you hit package compatibility issues.
)

if "%NVIDIA_GPU%"=="1" (
    if /i not "%TORCH_CUDA_AVAILABLE%"=="True" (
        echo.
        echo WARNING: NVIDIA GPU detected, but this virtual environment cannot use CUDA.
        if defined CUDA_WHEEL_TAG (
            echo Recommended reinstall commands for this machine:
            echo   "%VENV_PY%" -m pip uninstall -y torch torchvision torchaudio
            echo   "%VENV_PY%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/%CUDA_WHEEL_TAG%
        ) else (
            echo Open https://pytorch.org/get-started/locally/ and choose the CUDA build that matches this machine.
        )
    )
) else (
    echo.
    echo INFO: No NVIDIA GPU detected. Real STT will run on CPU only.
)

if /i "%CONFIGURED_DEVICE%"=="cuda" if /i not "%TORCH_CUDA_AVAILABLE%"=="True" (
    echo.
    echo WARNING: WHISPER_DEVICE=cuda is configured, but CUDA is not usable.
    echo          Set WHISPER_DEVICE=cpu or WHISPER_DEVICE=auto in .env until CUDA is fixed.
)

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
"%VENV_PY%" -m streamlit run app.py --server.port 8501 --server.headless true
goto end

:error
echo.
echo SmartVoice could not start. Check the error above.
echo If this is the first run, confirm Python 3.10/3.11 and internet access are available.
pause
exit /b 1

:end
pause
