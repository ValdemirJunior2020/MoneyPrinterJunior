@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Ollama Video Studio - Start

if not exist logs mkdir logs >nul 2>&1
set "LOG=%CD%\logs\start.log"
>"%LOG%" echo Ollama Video Studio start log - %date% %time%

cls
echo ============================================================
echo              OLLAMA VIDEO STUDIO - START
echo ============================================================
echo.
echo If startup fails, this window will stay open.
echo Detailed log: "%LOG%"
echo.

call :find_docker
if errorlevel 1 goto :failed

call :ensure_ollama
if errorlevel 1 goto :failed

call :ensure_model
if errorlevel 1 goto :failed

call :ensure_docker
if errorlevel 1 goto :failed

if not exist ".env" (
    if not exist ".env.example" (
        set "FAILMSG=.env and .env.example are both missing. Run INSTALL.bat from the full project folder."
        goto :failed
    )
    copy /y ".env.example" ".env" >nul
    echo Created .env from .env.example.
)

echo Starting application containers...
"%DOCKER%" compose up -d >>"%LOG%" 2>&1
if errorlevel 1 (
    set "FAILMSG=Docker Compose could not start the application."
    goto :failed_with_docker_logs
)

echo Waiting for the web application...
for /l %%i in (1,1,120) do (
    powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://localhost:5173' -TimeoutSec 2; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 500){exit 0}else{exit 1} } catch { exit 1 }" >nul 2>&1 && goto :app_ready
    timeout /t 2 /nobreak >nul
)

set "FAILMSG=The containers started, but the web app never became healthy at http://localhost:5173."
goto :failed_with_docker_logs

:app_ready
echo.
echo ============================================================
echo Ollama Video Studio is running.
echo Opening http://localhost:5173
echo ============================================================
echo.
start "" "http://localhost:5173"
timeout /t 3 /nobreak >nul
exit /b 0

:find_docker
set "DOCKER=docker"
where docker >nul 2>&1
if errorlevel 1 (
    if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" (
        set "DOCKER=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
    ) else (
        set "FAILMSG=Docker CLI was not found. Install Docker Desktop first."
        exit /b 1
    )
)
"%DOCKER%" --version >nul 2>&1
if errorlevel 1 (
    set "FAILMSG=Docker CLI was found but could not run."
    exit /b 1
)
exit /b 0

:ensure_ollama
set "OLLAMA=ollama"
where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    ) else (
        set "FAILMSG=Ollama was not found. Install Ollama for Windows first."
        exit /b 1
    )
)

"%OLLAMA%" list >nul 2>&1
if errorlevel 1 (
    echo Ollama is installed but not responding. Starting it...
    start "" /min "%OLLAMA%" serve
    for /l %%i in (1,1,30) do (
        "%OLLAMA%" list >nul 2>&1 && (
            echo Ollama is ready.
            exit /b 0
        )
        timeout /t 2 /nobreak >nul
    )
    set "FAILMSG=Ollama did not become ready."
    exit /b 1
)
echo Ollama is ready.
exit /b 0

:ensure_model
"%OLLAMA%" list | findstr /i /c:"qwen3:8b" >nul
if errorlevel 1 (
    echo qwen3:8b is missing. Pulling it now...
    "%OLLAMA%" pull qwen3:8b
    if errorlevel 1 (
        set "FAILMSG=Could not pull qwen3:8b."
        exit /b 1
    )
)
echo qwen3:8b is ready.
exit /b 0

:ensure_docker
"%DOCKER%" info >nul 2>&1
if not errorlevel 1 (
    echo Docker Desktop is ready.
    exit /b 0
)

set "DOCKER_DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKER_DESKTOP%" (
    set "FAILMSG=Docker Desktop executable was not found."
    exit /b 1
)

echo Docker Desktop is not running. Starting it...
start "" "%DOCKER_DESKTOP%"
echo Waiting for Docker Desktop...
for /l %%i in (1,1,90) do (
    "%DOCKER%" info >nul 2>&1 && (
        echo Docker Desktop is ready.
        exit /b 0
    )
    timeout /t 2 /nobreak >nul
)
set "FAILMSG=Docker Desktop did not become ready. Open Docker Desktop manually and check for an engine error."
exit /b 1

:failed_with_docker_logs
echo.>>"%LOG%"
echo ===== docker compose ps =====>>"%LOG%"
"%DOCKER%" compose ps >>"%LOG%" 2>&1
echo.>>"%LOG%"
echo ===== recent docker compose logs =====>>"%LOG%"
"%DOCKER%" compose logs --tail 120 >>"%LOG%" 2>&1

echo.
echo ---------------- RECENT LOG OUTPUT ----------------
powershell -NoProfile -Command "if (Test-Path '%LOG%') { Get-Content -Path '%LOG%' -Tail 40 }"
echo ---------------------------------------------------
goto :failed

:failed
echo.
echo ============================================================
echo STARTUP FAILED
echo %FAILMSG%
echo.
echo The window is staying open so you can read the error.
echo Log file: "%LOG%"
echo ============================================================
echo.
pause
exit /b 1
