@echo off
setlocal

title DiscordDrive - Status

call "%~dp0DiscordDrive.cmd" status

if "%~1"=="--no-pause" goto :done

echo.
echo ============================================================
echo Press any key to close this window...
echo ============================================================
pause >nul

:done
endlocal
