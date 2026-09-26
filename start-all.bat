@echo off
REM =====================================================================
REM  IBCP-SCADA - Build & Launch All Services
REM  Loads DATABASE_URL from the repo-root .env (Neon is the primary DB),
REM  then starts the backend (AquaVision) and frontend (Next.js).
REM  A local PostGIS container is only started when DATABASE_URL points
REM  at localhost. Requirements: Python 3, Node + npm, Docker (optional).
REM  Place at repo root and run / double-click.
REM =====================================================================
setlocal enabledelayedexpansion

REM ---- Paths (relative to this script's location) ----------------------
set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%services\aquavision-service"
set "FRONTEND_DIR=%ROOT%packages\dashboard"

REM ---- Config (edit as needed) -----------------------------------------
set "DB_NAME=ibcp-postgis"
set "BACKEND_PORT=8100"
set "FRONTEND_PORT=3000"
set "BACKEND_HOST=127.0.0.1"
set "PYTHON_CMD=python"
REM Prefer the project virtualenv if it exists (created by: python -m venv .venv)
if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" set "PYTHON_CMD=%BACKEND_DIR%\.venv\Scripts\python.exe"
REM The app reads DATABASE_URL from the process environment (nothing loads
REM .env), so source it from the repo-root .env (Neon connection string).
set "DATABASE_URL="
if exist "%ROOT%.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ROOT%.env") do (
        if /I "%%A"=="DATABASE_URL" set "DATABASE_URL=%%B"
    )
)
if not defined DATABASE_URL (
    echo   [x] DATABASE_URL not found in %ROOT%.env
    echo       Copy .env.example to .env at the repo root, paste your Neon
    echo       connection string as DATABASE_URL, then re-run this script.
    exit /b 1
)

echo.
echo ============================================================
echo   IBCP-SCADA Startup
echo   Root: %ROOT%
echo ============================================================
echo.

REM ---- 1. Database (remote Neon, or local container) -----------------
echo [1/4] Checking database...
echo %DATABASE_URL% | findstr /i /c:"localhost" >nul
if not errorlevel 1 (
    echo   Local DATABASE_URL detected - checking container "%DB_NAME%"...
    docker info >nul 2>&1
    if errorlevel 1 (
        echo   ^! Docker is not running. The local database needs Docker Desktop.
        echo     Start Docker Desktop, or point DATABASE_URL at Neon in .env.
    ) else (
        docker start %DB_NAME% >nul 2>&1 && (
            echo   ^+ Container "%DB_NAME%" started.
        ) || (
            docker ps -a --filter "name=%DB_NAME%" --format "{{.Names}}" | findstr /i "%DB_NAME%" >nul 2>&1
            if errorlevel 1 (
                echo   ^! No container named "%DB_NAME%" exists. Create it first, e.g.:
                echo     docker run -d --name %DB_NAME% -p 5433:5432 ^
                  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=1234 -e POSTGRES_DB=ibcp_scada ^
                    postgis/postgis:16-3.4
            )
        )
    )
) else (
    echo   ^+ Using remote Neon database (DATABASE_URL from .env).
    echo     No local DB container needed.
)
echo.

REM ---- 2. Backend (AquaVision) -------------------------------------
echo [2/4] Starting AquaVision backend on port %BACKEND_PORT%...
if not exist "%BACKEND_DIR%\main.py" (
    echo   [x] Backend entrypoint missing: %BACKEND_DIR%\main.py
    echo
    goto :frontend
)
start "IBCP-SCADA-Backend" cmd /c "cd /d \"%BACKEND_DIR%\" && set DATABASE_URL=%DATABASE_URL% && \"%PYTHON_CMD%\" -m uvicorn main:app --host %BACKEND_HOST% --port %BACKEND_PORT%" >nul 2>&1

echo   Waiting for backend at http://%BACKEND_HOST%:%BACKEND_PORT%/health/live ...
set /a TIMEOUTS=0
:backend-wait
set /a TIMEOUTS+=1
curl -s -o nul -w "%%{http_code}" "http://%BACKEND_HOST%:%BACKEND_PORT%/health/live" 2>nul | findstr "200" >nul 2>&1
if not errorlevel 1 goto :backend-up
if %TIMEOUTS% GTR 40 (
    echo   [x] Backend not ready after 40s. Check the backend window for errors.
    goto :frontend
)
timeout /t 1 /nobreak >nul
goto :backend-wait
:backend-up
echo   ^+ Backend is UP  -  http://%BACKEND_HOST%:%BACKEND_PORT%/docs

REM ---- 3. Scheduler ---------------------------------------------------
echo.
echo [3/4] Scheduler runs via docker compose (service "scheduler").
echo        Start the full stack with:  docker compose up -d --build
echo        (the legacy standalone scheduler container is gone).

REM ---- 4. Frontend (Next.js) ----------------------------------------
:frontend
echo.
echo [4/4] Starting Frontend (Next.js) on port %FRONTEND_PORT%...

cd /d "%FRONTEND_DIR%" 2>nul || goto :frontend-fail

if not exist "%FRONTEND_DIR%\package.json" (
    echo   [x] Frontend package.json missing. Expected: %FRONTEND_DIR%
    goto :done
)
if not exist "%FRONTEND_DIR%\node_modules" (
    echo   Installing frontend dependencies ^(npm install^)... this may take a while.
    call npm install 2>nul
    if errorlevel 1 (
        echo   [x] npm install failed. Run it manually in %FRONTEND_DIR%.
        goto :done
    )
)
start "" /b cmd /c "cd /d \"%FRONTEND_DIR%\" && npm run dev -- -p %FRONTEND_PORT%"
echo   ^Frontend launched ^(npm run dev, port %FRONTEND_PORT%).

echo.
echo ============================================================
echo   All services started.
echo    - Database     : DATABASE_URL from repo-root .env (Neon primary)
echo    - Backend      : http://%BACKEND_HOST%:%BACKEND_PORT%  (Swagger /docs)
echo    - Scheduler    : docker compose service "scheduler"
echo    - Frontend     : http://localhost:%FRONTEND_PORT%
echo   This window will close now; the services keep running
echo   in their own terminal windows.
echo ============================================================
echo.
exit /b

:frontend-fail
echo   [x] Cannot find the frontend directory: %FRONTEND_DIR%
goto :done

:done
echo.
echo Finished with errors. See messages above.
pause >nul
exit /b