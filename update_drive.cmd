@echo off
:: Updates DiscordDrive: stop the drive, download the latest version, start it again.
:: Works from Command Prompt, PowerShell, or a double-click.

:: Run from a temporary copy: git pull may replace this very file while it runs.
if /i not "%~1"=="--from-temp" (
    copy /y "%~f0" "%TEMP%\DiscordDrive-update.cmd" >nul
    "%TEMP%\DiscordDrive-update.cmd" --from-temp "%~dp0." %1
    exit /b
)

setlocal
set "REPO=%~f2"
set "NOPAUSE=%~3"
title DiscordDrive - Update
cd /d "%REPO%"

echo ============================================================
echo                   Updating DiscordDrive
echo ============================================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] git was not found. Install it with:
    echo     winget install -e --id Git.Git --source winget
    goto :end
)

call "%REPO%\stop_drive.cmd" --no-pause
echo.
echo Downloading the latest version...
git pull --ff-only
if errorlevel 1 (
    echo.
    echo [WARNING] Could not update ^(see the message above^). Starting the current version again.
)
echo.
call "%REPO%\start_drive.cmd" --no-pause

:end
if /i "%NOPAUSE%"=="--no-pause" goto :done
echo.
echo ============================================================
echo Window will close in 10s or press any key to close now.
echo ============================================================
timeout /t 10 >nul 2>nul || pause >nul

:done
endlocal
