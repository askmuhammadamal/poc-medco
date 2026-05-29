@echo off
REM ---------------------------------------------------------------------------
REM Double-click wrapper for setup-windows.ps1 (Python-only setup).
REM   1. Installs Python via winget if missing.
REM   2. Runs setup-windows.ps1 (creates venvs + installs deps for sim + middleware).
REM
REM No admin needed for the .ps1 step; the winget Python install may prompt UAC.
REM   setup-windows.bat              (install Python if needed, then set up)
REM   setup-windows.bat /no-winget   (skip Python install; assume it's on PATH)
REM ---------------------------------------------------------------------------
setlocal EnableDelayedExpansion

set "SCRIPT=%~dp0setup-windows.ps1"
set "DO_WINGET=1"
if /I "%~1"=="/no-winget" set "DO_WINGET=0"

if not exist "%SCRIPT%" (
    echo ERROR: setup-windows.ps1 not found next to this .bat ^(%SCRIPT%^).
    pause
    exit /b 1
)

if "%DO_WINGET%"=="0" goto run_ps

where python >nul 2>&1
if not errorlevel 1 (
    echo Python already on PATH - skipping install.
    goto run_ps
)

where winget >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Python and winget both missing. Install Python 3.9+ from python.org, then re-run.
    echo.
    goto run_ps
)

echo ==^> Installing Python via winget...
winget install --id Python.Python.3.12 -e --silent --accept-source-agreements --accept-package-agreements
REM Refresh this session's PATH from the registry so the freshly installed python is visible.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command ^
  "[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P"

:run_ps
echo.
echo ==^> Running setup-windows.ps1 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" ( echo Setup finished OK. ) else ( echo Setup FAILED with exit code %RC%. )
pause
exit /b %RC%
