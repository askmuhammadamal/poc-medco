@echo off
REM ---------------------------------------------------------------------------
REM Verify the install on Windows.
REM   1. Runs the pytest suite (deterministic, no PLC needed).
REM   2. Optional /sim : end-to-end smoke — start the simulator, run the service
REM      ~12s against it, confirm /api/state responds and a CSV is written.
REM
REM   verify-windows.bat          (tests only)
REM   verify-windows.bat /sim     (tests + e2e smoke)
REM ---------------------------------------------------------------------------
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "MW=%ROOT%middleware"
set "SIM=%ROOT%plc-simulator"
set "MWPY=%MW%\.venv\Scripts\python.exe"
set "SIMPY=%SIM%\.venv\Scripts\python.exe"
set "DO_SIM=0"
if /I "%~1"=="/sim" set "DO_SIM=1"

if not exist "%MWPY%" (
    echo ERROR: middleware venv not found. Run setup-windows.bat first.
    pause
    exit /b 1
)

REM --- 1. tests ---------------------------------------------------------------
echo.
echo ==^> pytest
pushd "%MW%"
"%MWPY%" -m pytest -q
set "TESTRC=%ERRORLEVEL%"
popd
if not "%TESTRC%"=="0" (
    echo.
    echo TESTS FAILED ^(exit %TESTRC%^).
    pause
    exit /b %TESTRC%
)
echo Tests passed.

REM --- 2. optional e2e smoke --------------------------------------------------
set "SMOKERC=0"
if "%DO_SIM%"=="0" goto done
if not exist "%SIMPY%" (
    echo WARNING: simulator venv not found - skipping e2e smoke. Run setup-windows.bat.
    goto done
)

echo.
echo ==^> e2e smoke (sim + service, ~15s)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$sim=Start-Process -FilePath '%SIMPY%' -ArgumentList 'plc_sim.py','--mode','known' -WorkingDirectory '%SIM%' -PassThru -WindowStyle Hidden;" ^
  "Start-Sleep -Seconds 3;" ^
  "$svc=Start-Process -FilePath '%MWPY%' -ArgumentList '-m','driftwatch','--mode','scan' -WorkingDirectory '%MW%' -PassThru -WindowStyle Hidden;" ^
  "Start-Sleep -Seconds 10;" ^
  "$ok=$false; try { $r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/state -TimeoutSec 5; $n=(ConvertFrom-Json $r.Content).Count; Write-Host ('  /api/state items: '+$n); $ok=($n -gt 0) } catch { Write-Host ('  /api/state failed: '+$_) };" ^
  "try { Stop-Process -Id $svc.Id -Force -ErrorAction SilentlyContinue } catch {};" ^
  "try { Stop-Process -Id $sim.Id -Force -ErrorAction SilentlyContinue } catch {};" ^
  "$csv = Get-ChildItem -Path (Join-Path '%MW%' 'logs') -Filter 'changes-*.csv' -ErrorAction SilentlyContinue ^| Select-Object -First 1;" ^
  "Write-Host ('  CSV written: '+[bool]$csv);" ^
  "if($ok -and $csv){ Write-Host 'SMOKE PASSED' -ForegroundColor Green; exit 0 } else { Write-Host 'SMOKE FAILED' -ForegroundColor Red; exit 1 }"
set "SMOKERC=%ERRORLEVEL%"

:done
echo.
if "%DO_SIM%"=="1" (
    if "%SMOKERC%"=="0" ( echo VERIFY OK: tests + e2e smoke passed. ) else ( echo VERIFY FAILED: e2e smoke failed ^(exit %SMOKERC%^). )
) else (
    echo VERIFY OK: tests passed. ^(Run with /sim for the e2e smoke.^)
)
pause
exit /b %SMOKERC%
