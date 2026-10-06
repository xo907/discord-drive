@echo off
setlocal

title DiscordDrive - Stopping Daemon

echo ============================================================
echo             Stopping DiscordDrive Daemon
echo ============================================================
echo.

call "%~dp0DiscordDrive.cmd" stop

if "%~1"=="--no-pause" goto :done

echo.
echo ============================================================
echo Window will close in 5s or press any key to close now.
echo ============================================================
timeout /t 5 >nul 2>nul || pause >nul

:done
endlocal
