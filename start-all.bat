@echo off
REM =====================================================================
REM  IBCP-SCADA - Build & Launch All Services
REM  Starts database (PostGIS), backend (AquaVision), and frontend (Next.js).
REM  Requirements: Docker Engine running (for DB), Python 3, Node + npm.
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

echo.
echo ============================================================
echo   IBCP-SCADA Startup
echo   Root: %ROOT%
echo ============================================================
echo.

REM ---- 1. Database (Docker PostGIS) -------------------------------
echo [1/3] Checking PostGIS database container "%DB_NAME%"...
docker info >nul 2>&1
if errorlevel 1 (
    echo   ^! Docker is not running. The database needs Docker Desktop.
    echo     Start Docker Desktop, then re-run this script.
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
echo.

REM ---- 2. Backend (AquaVision) -------------------------------------
echo [2/3] Starting AquaVision backend on port %BACKEND_PORT%...
if not exist "%BACKEND_DIR%\main.py" (
    echo   [x] Backend entrypoint missing: %BACKEND_DIR%\main.py
    echo
    goto :frontend
)
start "IBCP-SCADA-Backend" cmd /c "cd /d \"%BACKEND_DIR%\" && %PYTHON_CMD% -m uvicorn main:app --host %BACKEND_HOST% --port %BACKEND_PORT%" >nul 2>&1

echo   Waiting for backend at http://%BACKEND_HOST%:%BACKEND_PORT%/health ...
set /a TIMEOUTS=0
:backend-wait
set /a TIMEOUTS+=1
curl -s -o nul -w "%%{http_code}" "http://%BACKEND_HOST%:%BACKEND_PORT%/health" 2>nul | findstr "200" >nul 2>&1
if not errorlevel 1 goto :backend-up
if %TIMEOUTS% GTR 40 (
    echo   [x] Backend not ready after 40s. Check the backend window for errors.
    goto :frontend
)
timeout /t 1 /nobreak >nul
goto :backend-wait
:backend-up
echo   ^+ Backend is UP  -  http://%BACKEND_HOST%:%BACKEND_PORT%/docs

REM ---- 3. Frontend (Next.js) ----------------------------------------
:frontend
echo.
echo [3/3] Starting Frontend (Next.js) on port %FRONTEND_PORT%...

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
echo    - Database     : Docker container %DB_NAME%  (port 5433)
echo    - Backend      : http://%BACKEND_HOST%:%BACKEND_PORT%  (Swagger /docs)
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