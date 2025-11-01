@echo off
CHCP 65001 > nul
SETLOCAL

SET "SCRIPT_DIR=%~dp0"
CD /D "%SCRIPT_DIR%"

echo ===================================
echo.

IF NOT EXIST "tools/install.bat" (
    echo Error: 'tools/install.bat' not found.
    goto :error
)
CALL "tools/install.bat"
IF %ERRORLEVEL% NEQ 0 (
    echo Error during tool installation.
    goto :error
)

IF NOT EXIST "python3/python.exe" (
    echo Error: Python executable not found.
    goto :error
)
IF NOT EXIST "main.py" (
    echo Error: 'main.py' not found.
    goto :error
)

echo Starting Anti-Anti-Rollback process...
echo.
python3\python.exe main.py anti_rollback

IF %ERRORLEVEL% NEQ 0 (
    echo An error occurred during the Python script execution.
    goto :error
)

echo.
echo Process completed.
goto :end

:error
echo.
echo An error occurred. Press Enter to exit.
pause > nul
EXIT /B 1

:end
ENDLOCAL