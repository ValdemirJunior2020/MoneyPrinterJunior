@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Ollama Video Studio - Smart Start

set "ROOT=%CD%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "REQ=%BACKEND%\requirements.txt"
set "VENV=%BACKEND%\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "PIP=%VENV%\Scripts\pip.exe"

set "OLLAMA_MODEL=qwen3:8b"
set "OLLAMA_URL=http://127.0.0.1:11434"
set "FRONTEND_URL=http://127.0.0.1:5173"

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs" >nul 2>&1
set "LOG=%ROOT%\logs\start.log"

cls
echo ============================================================
echo       OLLAMA VIDEO STUDIO - SMART START
echo ============================================================
echo Project:
echo %ROOT%
echo.

echo [1/10] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo Install Python 3.11 or newer and try again.
    goto FAIL
)
python --version
if errorlevel 1 goto FAIL
echo [OK] Python found.
echo.

echo [2/10] Checking backend requirements file...
if not exist "%REQ%" (
    echo [ERROR] requirements.txt was not found:
    echo %REQ%
    goto FAIL
)
echo [OK] Found:
echo %REQ%
echo.

echo [3/10] Checking backend virtual environment...
if not exist "%PYTHON%" (
    echo Backend virtual environment not found.
    echo Creating:
    echo %VENV%
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create backend virtual environment.
        goto FAIL
    )
)
echo [OK] Backend virtual environment ready.
echo.

echo [4/10] Checking/updating Python requirements...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Could not update pip.
    goto FAIL
)

echo.
echo Installing ONLY missing/outdated packages from requirements.txt...
echo Existing correct packages will be kept.
"%PYTHON%" -m pip install -r "%REQ%"
if errorlevel 1 (
    echo.
    echo [ERROR] Python requirements installation failed.
    echo Check the package error above.
    goto FAIL
)

echo.
echo Running pip dependency check...
"%PYTHON%" -m pip check
if errorlevel 1 (
    echo.
    echo [ERROR] Python dependency conflicts were detected.
    goto FAIL
)
echo [OK] Backend Python requirements are installed.
echo.

echo [5/10] Checking Node.js / frontend requirements...
if exist "%FRONTEND%\package.json" (
    where node >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Node.js is required but was not found.
        echo Install Node.js LTS and try again.
        goto FAIL
    )

    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] npm was not found.
        goto FAIL
    )

    echo Node:
    node --version
    echo npm:
    npm --version

    if not exist "%FRONTEND%\node_modules" (
        echo Frontend node_modules not found. Installing packages...
        pushd "%FRONTEND%"
        if exist "package-lock.json" (
            call npm ci
        ) else (
            call npm install
        )
        set "NPMERR=!errorlevel!"
        popd
        if not "!NPMERR!"=="0" (
            echo [ERROR] Frontend npm install failed.
            goto FAIL
        )
    ) else (
        echo [OK] frontend node_modules already exists.
    )
) else (
    echo [INFO] No frontend\package.json found. Docker may provide the frontend.
)
echo.

echo [6/10] Checking Ollama...
set "OLLAMA=ollama"
where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    ) else (
        echo [ERROR] Ollama was not found.
        goto FAIL
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "try { Invoke-RestMethod '%OLLAMA_URL%/api/tags' -TimeoutSec 3 ^| Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo Ollama is installed but not running. Starting Ollama...
    start "" /min "%OLLAMA%" serve

    set "OLLAMA_READY=0"
    for /l %%I in (1,1,30) do (
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
         "try { Invoke-RestMethod '%OLLAMA_URL%/api/tags' -TimeoutSec 2 ^| Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
        if not errorlevel 1 (
            set "OLLAMA_READY=1"
            goto OLLAMA_READY
        )
        timeout /t 2 /nobreak >nul
    )
    :OLLAMA_READY
    if "!OLLAMA_READY!"=="0" (
        echo [ERROR] Ollama did not become ready.
        goto FAIL
    )
)
echo [OK] Ollama is ready.
echo.

echo [7/10] Checking Ollama model %OLLAMA_MODEL%...
"%OLLAMA%" list | findstr /i /c:"%OLLAMA_MODEL%" >nul
if errorlevel 1 (
    echo %OLLAMA_MODEL% is missing. Downloading it now...
    "%OLLAMA%" pull %OLLAMA_MODEL%
    if errorlevel 1 (
        echo [ERROR] Could not pull %OLLAMA_MODEL%.
        goto FAIL
    )
)
echo [OK] %OLLAMA_MODEL% is installed.
echo.

echo [8/10] Checking Docker Desktop...
where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI was not found.
    echo Install Docker Desktop and try again.
    goto FAIL
)

docker info >nul 2>&1
if errorlevel 1 (
    if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
        echo Docker Desktop is not running. Starting it...
        start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"

        set "DOCKER_READY=0"
        for /l %%I in (1,1,90) do (
            docker info >nul 2>&1
            if not errorlevel 1 (
                set "DOCKER_READY=1"
                goto DOCKER_READY
            )
            timeout /t 2 /nobreak >nul
        )
        :DOCKER_READY
        if "!DOCKER_READY!"=="0" (
            echo [ERROR] Docker Desktop did not become ready.
            goto FAIL
        )
    ) else (
        echo [ERROR] Docker Desktop executable was not found.
        goto FAIL
    )
)
echo [OK] Docker Desktop is ready.
echo.

echo [9/10] Starting application...
if exist "%ROOT%\docker-compose.yml" goto START_DOCKER
if exist "%ROOT%\docker-compose.yaml" goto START_DOCKER
if exist "%ROOT%\compose.yml" goto START_DOCKER
if exist "%ROOT%\compose.yaml" goto START_DOCKER
goto START_LOCAL

:START_DOCKER
echo Docker Compose detected.
docker compose config >nul
if errorlevel 1 (
    echo [ERROR] docker compose config failed.
    goto FAIL
)

docker compose up -d
if errorlevel 1 (
    echo [ERROR] docker compose up failed.
    docker compose logs --tail 100
    goto FAIL
)
echo [OK] Docker Compose services started.
goto WAIT_APP

:START_LOCAL
echo No Compose file found. Starting backend/frontend directly...

if exist "%BACKEND%\main.py" (
    start "Ollama Video Studio - Backend" cmd /k ^
      "cd /d ""%BACKEND%"" && ""%PYTHON%"" -m uvicorn main:app --host 0.0.0.0 --port 8000"
) else (
    echo [WARN] backend\main.py not found.
)

if exist "%FRONTEND%\package.json" (
    start "Ollama Video Studio - Frontend" cmd /k ^
      "cd /d ""%FRONTEND%"" && npm run dev -- --host 0.0.0.0"
) else (
    echo [WARN] frontend\package.json not found.
)

:WAIT_APP
echo.
echo [10/10] Waiting for frontend...
set "WEB_READY=0"
for /l %%I in (1,1,60) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "try {$r=Invoke-WebRequest -UseBasicParsing '%FRONTEND_URL%' -TimeoutSec 3; if($r.StatusCode -ge 200){exit 0}else{exit 1}} catch {exit 1}" >nul 2>&1
    if not errorlevel 1 (
        set "WEB_READY=1"
        goto WEB_READY
    )
    timeout /t 2 /nobreak >nul
)

:WEB_READY
if "!WEB_READY!"=="1" (
    echo [OK] Frontend is ready:
    echo %FRONTEND_URL%
    echo.
    echo ============================================================
    echo                EVERYTHING IS READY
    echo ============================================================
    echo Python requirements : OK
    echo Frontend packages    : OK
    echo Ollama               : OK
    echo %OLLAMA_MODEL%       : OK
    echo Docker               : OK
    echo Application          : STARTED
    echo ============================================================
    start "" "%FRONTEND_URL%"
    exit /b 0
)

echo [WARN] Services started, but frontend did not answer at %FRONTEND_URL%.
echo.
echo Docker status:
docker compose ps 2>nul
echo.
echo Check the service logs if your frontend uses a different port.
pause
exit /b 0

:FAIL
echo.
echo ============================================================
echo STARTUP STOPPED
echo A required dependency/check failed.
echo Nothing else will be started until this is fixed.
echo ============================================================
echo.
pause
exit /b 1
