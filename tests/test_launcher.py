from pathlib import Path


def test_batch_python_probes_call_quoted_venv_python():
    run_bat = Path("run.bat").read_text(encoding="utf-8")

    python_probe_lines = [
        line.strip()
        for line in run_bat.splitlines()
        if 'for /f ' in line and 'call "%VENV_PY%" -c ' in line
    ]

    assert python_probe_lines
    assert all('for /f "delims="' in line for line in python_probe_lines)


def test_launcher_bootstraps_supported_python_without_unsupported_fallbacks():
    run_bat = Path("run.bat").read_text(encoding="utf-8")

    assert 'set "PY311_INSTALLER_URL=' in run_bat
    assert 'choice /c YN /m "Install Python 3.11 now"' in run_bat
    assert 'Start-Process -FilePath $installer' in run_bat
    assert 'py -3 --version' not in run_bat
    assert 'if not defined PY_CMD (' in run_bat
    assert r'%LOCALAPPDATA%\Programs\Python\Python311\python.exe' in run_bat
    assert 'set "PATH_PY_VERSION="' in run_bat
    assert 'if "%PATH_PY_VERSION%"=="3.10" set "PY_CMD=python"' in run_bat
    assert 'if "%PATH_PY_VERSION%"=="3.11" set "PY_CMD=python"' in run_bat
