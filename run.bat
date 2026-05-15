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
set "CONFIGURED_OLLAMA_MODEL=scb10x/llama3.1-typhoon2-8b-instruct"
if exist ".env" (
    for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"WHISPER_DEVICE=" ".env"') do set "CONFIGURED_DEVICE=%%B"
    for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"OLLAMA_MODEL=" ".env"') do set "CONFIGURED_OLLAMA_MODEL=%%B"
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
            echo.
            choice /c YN /m "Install the recommended CUDA-enabled PyTorch build now"
            if errorlevel 2 (
                echo Skipping CUDA-enabled PyTorch install.
            ) else (
                echo.
                echo Installing CUDA-enabled PyTorch build...
                "%VENV_PY%" -m pip uninstall -y torch torchvision torchaudio
                if errorlevel 1 goto error
                "%VENV_PY%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/%CUDA_WHEEL_TAG%
                if errorlevel 1 goto error
                for /f "delims=" %%A in ('"%VENV_PY%" -c "import torch; print(torch.__version__)"' ) do set "TORCH_VERSION=%%A"
                for /f "delims=" %%A in ('"%VENV_PY%" -c "import torch; print(torch.version.cuda or '')"' ) do set "TORCH_CUDA_VERSION=%%A"
                for /f "delims=" %%A in ('"%VENV_PY%" -c "import torch; print(torch.cuda.is_available())"' ) do set "TORCH_CUDA_AVAILABLE=%%A"
                echo.
                echo CUDA install result
                echo   PyTorch: %TORCH_VERSION%
                echo   PyTorch CUDA build: %TORCH_CUDA_VERSION%
                echo   PyTorch CUDA usable: %TORCH_CUDA_AVAILABLE%
                if /i not "%TORCH_CUDA_AVAILABLE%"=="True" (
                    echo WARNING: CUDA is still not usable after install. Check the NVIDIA driver and restart this launcher.
                )
            )
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

set "OLLAMA_CMD="
where ollama >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%A in ('where ollama') do if not defined OLLAMA_CMD set "OLLAMA_CMD=%%A"
)
if not defined OLLAMA_CMD if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"

if not defined OLLAMA_CMD (
    echo.
    echo NOTE: Ollama is not installed or not in PATH.
    echo Real LLM analysis needs Ollama for Windows.
    echo Official installer source: https://ollama.com/download/windows
    echo.
    choice /c YN /m "Install Ollama for Windows now"
    if errorlevel 2 (
        echo Skipping Ollama install.
    ) else (
        echo.
        echo Installing Ollama for Windows...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://ollama.com/install.ps1 | iex"
        if errorlevel 1 goto error
        if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        if not defined OLLAMA_CMD (
            echo WARNING: Ollama installation finished, but ollama.exe was not found yet.
            echo          Open a new terminal or restart this launcher after installation.
        )
    )
)

if defined OLLAMA_CMD (
    echo Starting Ollama in the background if it is not already running...
    start "SmartVoice Ollama" /min "%OLLAMA_CMD%" serve
    timeout /t 3 /nobreak >nul

    set "OLLAMA_MODEL_INSTALLED=0"
    "%OLLAMA_CMD%" list | findstr /i /c:"%CONFIGURED_OLLAMA_MODEL%" >nul 2>nul
    if not errorlevel 1 set "OLLAMA_MODEL_INSTALLED=1"

    if "%OLLAMA_MODEL_INSTALLED%"=="0" (
        echo.
        echo NOTE: Required Ollama model is not installed:
        echo   %CONFIGURED_OLLAMA_MODEL%
        echo Model downloads can be several GB.
        echo.
        choice /c YN /m "Download the required Ollama model now"
        if errorlevel 2 (
            echo Skipping Ollama model download.
        ) else (
            echo.
            echo Downloading Ollama model...
            "%OLLAMA_CMD%" pull "%CONFIGURED_OLLAMA_MODEL%"
            if errorlevel 1 goto error
        )
    )
) else (
    echo Install Ollama from https://ollama.com/download/windows for real LLM analysis.
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
