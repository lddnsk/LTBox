@echo off
chcp 65001 > nul
setlocal

:: --- 1. Initialization and Dependency Check ---
echo --- Initializing LTBox... ---
call "%~dp0tools\install.bat"
if errorlevel 1 (
    echo [!] Dependency installation failed. Please check tools\install.bat.
    pause
    goto :eof
)

:: --- 2. Set Python and Main Script Paths ---
set "PYTHON_EXE=%~dp0python3\python.exe"
set "MAIN_PY=%~dp0main.py"

if not exist "%PYTHON_EXE%" (
    echo [!] Python not found at: %PYTHON_EXE%
    echo [!] Please run tools\install.bat first.
    pause
    goto :eof
)
if not exist "%MAIN_PY%" (
    echo [!] Main script not found at: %MAIN_PY%
    pause
    goto :eof
)

:: --- 3. Main Menu Loop ---
:main_menu
cls
echo.
echo   ==========================================================
echo     LTBox - Main Menu
echo   ==========================================================
echo.
echo     --- Flashing Tools ---
echo     1. Convert ROM (PRC to ROW)
echo     2. Dump devinfo/persist via EDL
echo     3. Patch devinfo/persist (Region Code Reset)
echo     4. Write devinfo/persist via EDL (Flash patched)
echo     5. Create Rooted boot.img
echo     6. Bypass Anti-Rollback (Firmware Downgrade)
echo.
echo     --- Full Firmware Tools (RSA Firmware) ---
echo     7. Modify XML for Update (Decrypts *.x, modifies XMLs)
echo     8. Flash EDL (Flashes full firmware from 'image' folder)
echo.
echo     --- Maintenance ---
echo     9. Clean Workspace (Remove tools and I/O folders)
echo     10. Exit
echo.
echo   ==========================================================
echo.

set "CHOICE="
set /p "CHOICE=    Enter the number for the task you want to run: "

:: --- Call arguments updated with new descriptions (no special chars) ---
if "%CHOICE%"=="1" call :run_task convert "ROM Conversion PRC to ROW"
if "%CHOICE%"=="2" call :run_task read_edl "EDL Dump devinfo/persist"
if "%CHOICE%"=="3" call :run_task edit_dp "Patch devinfo/persist"
if "%CHOICE%"=="4" call :run_task write_edl "EDL Write devinfo/persist"
if "%CHOICE%"=="5" call :run_task root "Root boot.img"
if "%CHOICE%"=="6" call :run_task anti_rollback "Anti-Rollback Bypass"
if "%CHOICE%"=="7" call :run_task modify_xml "Modify XML for Update"
if "%CHOICE%"=="8" call :run_task flash_edl "Full EDL Flash"

:: --- Modified logic for Choice 9 (Clean) ---
if "%CHOICE%"=="9" (
    cls
    echo ==========================================================
    echo  Starting Task: [Workspace Cleanup]...
    echo ==========================================================
    echo.
    "%PYTHON_EXE%" "%MAIN_PY%" clean
    echo.
    echo ==========================================================
    echo  Task [Workspace Cleanup] has completed.
    echo ==========================================================
    echo.
    echo Press any key to exit...
    pause > nul
    goto :cleanup
)

if "%CHOICE%"=="10" goto :cleanup

:: Handle invalid input
echo.
echo     [!] Invalid choice. Please enter a number from 1-10.
pause
goto :main_menu

:: --- 4. Task Execution Subroutine ---
:run_task
cls
echo ==========================================================
echo  Starting Task: [%~2]...
echo ==========================================================
echo.

:: %1 is the main.py argument (e.g., convert), %~2 is the description string
"%PYTHON_EXE%" "%MAIN_PY%" %1

echo.
echo ==========================================================
echo  Task [%~2] has completed.
echo ==========================================================
echo.
echo Press any key to return to the main menu...
pause > nul
goto :main_menu

:: --- 5. Exit ---
:cleanup
endlocal
echo.
echo Exiting LTBox.
goto :eof
