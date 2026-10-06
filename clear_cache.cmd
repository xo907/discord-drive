@echo off
setlocal

title DiscordDrive - Clear Local Cache

echo ============================================================
echo            DiscordDrive - Clear Local Disk Cache
echo ============================================================
echo.
echo Evicting cached chunks from local disk...
echo Your files in Discord remain 100%% safe and stream on demand.
echo.

set "EXTRA_ARGS="
if not "%~1"=="--no-pause" set "EXTRA_ARGS=%*"

call "%~dp0DiscordDrive.cmd" clear-cache %EXTRA_ARGS%

if "%~1"=="--no-pause" goto :done

echo.
echo ============================================================
echo Local storage freed! Window will close in 5s or press a key.
echo ============================================================
timeout /t 5 >nul 2>nul || pause >nul

:done
endlocal
