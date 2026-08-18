@echo off
REM scripts/backup-db.bat
REM Daily database backup for IBCP-SCADA PostGIS.
REM Usage: scripts\backup-db.bat [backup_dir]
REM Default backup dir: .\backups

setlocal enabledelayedexpansion

set BACKUP_DIR=%~1
if "%BACKUP_DIR%"=="" set BACKUP_DIR=%~dp0..\backups
set TIMESTAMP=%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%
set TIMESTAMP=%TIMESTAMP: =0%
set FILENAME=ibcp_scada_%TIMESTAMP%.sql.gz

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR"

echo [%date% %time%] Starting backup: %FILENAME%

set PGPASSWORD=1234
pg_dump -h localhost -p 5433 -U postgres -d ibcp_scada --no-owner --no-privileges | gzip > "%BACKUP_DIR%\%FILENAME%"

if %ERRORLEVEL% equ 0 (
    echo [%date% %time%] Backup successful: %BACKUP_DIR%\%FILENAME%
    REM Keep only last 30 backups
    for /f "skip=30 tokens=*" %%f in ('dir /b /o-d "%BACKUP_DIR%\ibcp_scada_*.sql.gz" 2^>nul') do (
        del "%BACKUP_DIR%\%%f" 2>nul
        echo [%date% %time%] Cleaned old backup: %%f
    )
) else (
    echo [%date% %time%] BACKUP FAILED with exit code %ERRORLEVEL%
    exit /b 1
)

endlocal
