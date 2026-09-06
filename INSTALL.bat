@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title Ollama Video Studio - Install
set "LOGDIR=%~dp0logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
set "LOGFILE=%LOGDIR%\install.log"

cls
echo ============================================================
echo             OLLAMA VIDEO STUDIO - INSTALL
echo ============================================================
echo.
echo This installer checks what you already have first.
echo It only builds what is missing.
echo.
>"%LOGFILE%" echo Ollama Video Studio install log - %DATE% %TIME%

REM ------------------------------------------------------------
REM 1. Docker CLI
REM ------------------------------------------------------------
echo [1/9] Checking Docker...
where docker >nul 2>&1
if errorlevel 1 goto :docker_missing
docker --version
docker --version >>"%LOGFILE%" 2>&1

REM ------------------------------------------------------------
REM 2. Docker engine
REM ------------------------------------------------------------
echo.
echo [2/9] Checking Docker Desktop engine...
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ready

set "DOCKERDESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if exist "%DOCKERDESKTOP%" (
    echo Docker Desktop is installed but not running. Starting it...
    start "" "%DOCKERDESKTOP%"
    echo Waiting for Docker Desktop...
    for /L %%I in (1,1,60) do (
        timeout /t 2 /nobreak >nul
        docker info >nul 2>&1
        if not errorlevel 1 goto :docker_ready
    )
)
goto :docker_engine_fail

:docker_ready
echo Docker Desktop is ready.

REM ------------------------------------------------------------
REM 3. Ollama
REM ------------------------------------------------------------
echo.
echo [3/9] Checking Ollama...
set "OLLAMA_EXE=ollama"
where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    ) else (
        goto :ollama_missing
    )
)
"%OLLAMA_EXE%" --version

REM ------------------------------------------------------------
REM 4. qwen3:8b
REM ------------------------------------------------------------
echo.
echo [4/9] Checking qwen3:8b...
"%OLLAMA_EXE%" list | findstr /I /C:"qwen3:8b" >nul 2>&1
if errorlevel 1 (
    echo qwen3:8b is missing. Pulling it now...
    "%OLLAMA_EXE%" pull qwen3:8b
    if errorlevel 1 goto :qwen_fail
) else (
    echo qwen3:8b is already installed.
)

REM ------------------------------------------------------------
REM 5. FFmpeg / FFprobe
REM ------------------------------------------------------------
echo.
echo [5/9] Checking FFmpeg and FFprobe...
where ffmpeg >nul 2>&1
if errorlevel 1 goto :ffmpeg_missing
where ffprobe >nul 2>&1
if errorlevel 1 goto :ffprobe_missing
echo FFmpeg and FFprobe are ready.

REM ------------------------------------------------------------
REM 6. Project files / env
REM ------------------------------------------------------------
echo.
echo [6/9] Checking project files...
set "MISSING=0"
for %%F in (
    "docker-compose.yml"
    "frontend\Dockerfile"
    "frontend\package.json"
    "frontend\src\main.tsx"
    "frontend\src\styles.css"
    "frontend\src\vite-env.d.ts"
    "backend\Dockerfile"
    "chatterbox_service\Dockerfile"
) do (
    if not exist %%F (
        echo MISSING: %%~F
        set "MISSING=1"
    )
)
if "!MISSING!"=="1" goto :project_missing

if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo Created .env from .env.example.
    ) else (
        goto :env_missing
    )
) else (
    echo Existing .env kept unchanged.
)
if not exist "storage" mkdir "storage" >nul 2>&1
if not exist "logs" mkdir "logs" >nul 2>&1
echo Project files are ready.

REM ------------------------------------------------------------
REM 7. Compose validation
REM ------------------------------------------------------------
echo.
echo [7/9] Validating Docker Compose...
docker compose config >nul 2>>"%LOGFILE%"
if errorlevel 1 goto :compose_fail
echo Docker Compose configuration is valid.

REM ------------------------------------------------------------
REM 8. Build only if an image is missing
REM ------------------------------------------------------------
echo.
echo [8/9] Checking Docker images...
set "NEEDBUILD=0"
for %%S in (frontend backend chatterbox) do (
    for /f "delims=" %%I in ('docker compose images -q %%S 2^>nul') do set "FOUNDIMAGE=%%I"
    if not defined FOUNDIMAGE set "NEEDBUILD=1"
    set "FOUNDIMAGE="
)

if "!NEEDBUILD!"=="1" (
    echo One or more images are missing. Building now...
    echo This can take a while the first time. Docker output will stay visible.
    echo.
    docker compose build
    if errorlevel 1 goto :build_fail
) else (
    echo Required Docker images already exist. Skipping build.
)

REM ------------------------------------------------------------
REM 9. Start services - NO fragile health-loop
REM ------------------------------------------------------------
echo.
echo [9/9] Starting services...
docker compose up -d
if errorlevel 1 goto :start_fail

echo.
echo Waiting 8 seconds for services to settle...
timeout /t 8 /nobreak >nul

echo.
echo Current Docker status:
docker compose ps

echo.
echo Checking the web app...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:5173/' -TimeoutSec 10; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo WARNING: Containers started, but the frontend is not answering yet.
    echo This is NOT treated as an installation failure.
    echo Run START.bat in a few seconds or open Docker Desktop to check status.
) else (
    echo Frontend responded successfully.
)

echo.
echo ============================================================
echo INSTALLATION FINISHED
echo ============================================================
echo.
echo App:        http://localhost:5173
echo Chatterbox: http://localhost:8001/health
echo.
echo The containers have been started.
echo If Docker Desktop shows green/running containers, the app is ready.
echo.
start "" http://localhost:5173 >nul 2>&1
pause
exit /b 0

:docker_missing
echo.
echo ERROR: Docker CLI was not found.
goto :fail

:docker_engine_fail
echo.
echo ERROR: Docker Desktop could not be started or is not ready.
goto :fail

:ollama_missing
echo.
echo ERROR: Ollama was not found.
goto :fail

:qwen_fail
echo.
echo ERROR: qwen3:8b could not be downloaded.
goto :fail

:ffmpeg_missing
echo.
echo ERROR: FFmpeg was not found on PATH.
goto :fail

:ffprobe_missing
echo.
echo ERROR: FFprobe was not found on PATH.
goto :fail

:project_missing
echo.
echo ERROR: Required project files are missing.
goto :fail

:env_missing
echo.
echo ERROR: .env.example is missing.
goto :fail

:compose_fail
echo.
echo ERROR: docker-compose.yml is invalid.
goto :fail

:build_fail
echo.
echo ERROR: Docker image build failed.
goto :fail

:start_fail
echo.
echo ERROR: Docker could not start the services.
goto :fail

:fail
echo.
echo ============================================================
echo INSTALLATION STOPPED
echo ============================================================
echo.
echo Log file: "%LOGFILE%"
echo.
pause
exit /b 1
