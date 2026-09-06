@echo off
setlocal
cd /d "%~dp0"
set FAIL=0

echo === Docker Compose validation ===
docker compose config >nul || set FAIL=1

echo === Backend unit tests ===
docker compose run --rm backend pytest -q || set FAIL=1

echo === Frontend TypeScript/build ===
docker compose --profile test run --rm frontend-build || set FAIL=1

echo === Core services ===
docker compose up -d || set FAIL=1

echo === Live backend health ===
powershell -NoProfile -Command "Invoke-RestMethod http://localhost:5173/api/health | Out-Null" || set FAIL=1

echo === Ollama and qwen3:8b ===
ollama list | findstr /i "qwen3:8b" >nul || set FAIL=1

echo === Chatterbox profiles/health ===
powershell -NoProfile -Command "Invoke-RestMethod http://localhost:8001/health | Out-Null; $p=Invoke-RestMethod http://localhost:8001/profiles; if(-not $p.dramatic -or -not $p.sermon){exit 1}" || set FAIL=1

echo === Provider + structured + FFmpeg checks ===
docker compose exec -T backend python scripts/validation_probe.py || set FAIL=1

echo === Emotion synthesis test ===
docker compose exec -T backend python scripts/emotion_test.py || set FAIL=1

echo === Microsoft Playwright ===
docker compose --profile test run --rm e2e || set FAIL=1

if "%FAIL%"=="0" (
  echo All executed gates succeeded.
  exit /b 0
)
echo One or more gates failed.
exit /b 1
