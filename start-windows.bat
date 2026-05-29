@echo off
REM ===========================================================================
REM  batam-poc — one-click Windows launcher.
REM  Double-click this. It will:
REM    1. install Python via winget if missing,
REM    2. create the venvs + install deps on first run (via setup-windows.ps1),
REM    3. ask for a PLC (blank = use the bundled simulator),
REM    4. start the simulator (if needed) + the middleware service,
REM    5. open the dashboard at http://127.0.0.1:8000.
REM
REM  Pass /no-winget to skip the Python install attempt.
REM ===========================================================================
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "MW=%ROOT%middleware"
set "SIM=%ROOT%plc-simulator"
set "MWPY=%MW%\.venv\Scripts\python.exe"
set "SIMPY=%SIM%\.venv\Scripts\python.exe"
set "DO_WINGET=1"
if /I "%~1"=="/no-winget" set "DO_WINGET=0"

REM --- 1. Python ---------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    if "%DO_WINGET%"=="1" (
        where winget >nul 2>&1
        if not errorlevel 1 (
            echo ==^> Installing Python via winget...
            winget install --id Python.Python.3.12 -e --silent --accept-source-agreements --accept-package-agreements
            for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command ^
              "[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P"
        ) else (
            echo ERROR: Python and winget both missing. Install Python 3.9+ from python.org, then re-run.
            pause
            exit /b 1
        )
    ) else (
        echo ERROR: Python not on PATH and /no-winget was given.
        pause
        exit /b 1
    )
)

REM --- 2. Deps (first run) -----------------------------------------------------
if not exist "%MWPY%"  goto setup
if not exist "%SIMPY%" goto setup
goto ready

:setup
echo ==^> First run: installing dependencies (this can take a minute)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%setup-windows.ps1"
if errorlevel 1 (
    echo ERROR: setup failed. See output above.
    pause
    exit /b 1
)

:ready
REM --- 3. Prompt for target ----------------------------------------------------
echo.
set "PLC_HOST="
set /p "PLC_HOST=PLC host/IP (blank = use the built-in simulator): "

set "SVC_ARGS=--mode scan"
set "USE_SIM=1"
if not "%PLC_HOST%"=="" (
    set "USE_SIM=0"
    set "PLC_PORT=502"
    set /p "PLC_PORT=PLC port [502]: "
    set "PLC_UNIT=1"
    set /p "PLC_UNIT=Unit id [1]: "
    set "SVC_ARGS=--mode scan --host !PLC_HOST! --port !PLC_PORT! --unit !PLC_UNIT!"
)

set "WR="
set /p "WR=Enable writes? Reaches real hardware. (y/N): "
if /I "%WR%"=="y" set "SVC_ARGS=%SVC_ARGS% --allow-writes"

REM --- 4. Launch ---------------------------------------------------------------
if "%USE_SIM%"=="1" (
    echo ==^> Starting simulator on :5020 ...
    start "PLC Simulator" /min cmd /c "cd /d ""%SIM%"" ^&^& "".venv\Scripts\python.exe"" plc_sim.py --mode known"
    timeout /t 3 /nobreak >nul
)

echo ==^> Starting middleware service on :8000 ...
start "Modbus Middleware" cmd /c "cd /d ""%MW%"" ^&^& "".venv\Scripts\python.exe"" -m driftwatch %SVC_ARGS%"

REM --- 5. Open dashboard -------------------------------------------------------
timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:8000

echo.
echo ===========================================================================
echo  Dashboard:  http://127.0.0.1:8000
if "%USE_SIM%"=="1" ( echo  Source:     built-in simulator ^(:5020^) ) else ( echo  Source:     %PLC_HOST%:%PLC_PORT% unit %PLC_UNIT% )
echo  Writes:     %WR%  ^(blank/N = disabled^)
echo  To stop:    close the "Modbus Middleware"^(and "PLC Simulator"^) windows.
echo ===========================================================================
echo.
pause
endlocal
