@echo off
chcp 65001 > nul
setlocal

set "PYTHON_EXE=%~dp0python3\python.exe"
set "MAIN_PY=%~dp0main.py"

if not exist "%PYTHON_EXE%" (
    echo [!] Python executable not found at "%PYTHON_EXE%"
    echo Please run install.bat first.
    pause
    exit /b 1
)

if not exist "%MAIN_PY%" (
    echo [!] Main script not found at "%MAIN_PY%"
    pause
    exit /b 1
)

echo --- Patching boot.img with KernelSU Only ---
echo.

"%PYTHON_EXE%" "%MAIN_PY%" root

endlocal
pause