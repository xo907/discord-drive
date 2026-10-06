@echo off
setlocal

title DiscordDrive - Starting

echo ============================================================
echo           Starting DiscordDrive in the background
echo ============================================================
echo.

:: Look up the configured drive letter (default Z:)
set "MP=Z:"
for /f "usebackq delims=" %%m in (`call "%~dp0DiscordDrive.cmd" mountpoint 2^>nul`) do set "MP=%%m"

if exist "%MP%\" (
    echo [INFO] DiscordDrive is already running on %MP%
    goto :show_status
)

:: Launch hidden via the VBScript wrapper
wscript.exe "%~dp0mount_silent.vbs"

:: Wait up to 15 seconds for the drive to appear
for /L %%i in (1,1,15) do (
    if exist "%MP%\" goto :mount_ok
    ping 127.0.0.1 -n 2 >nul
)

:mount_ok
if exist "%MP%\" (
    echo [SUCCESS] DiscordDrive is running on %MP%
) else (
    echo [INFO] Still starting up. Check the log in %%LOCALAPPDATA%%\DiscordDrive\discorddrive.log
)

:show_status
echo.
call "%~dp0DiscordDrive.cmd" status

if "%~1"=="--no-pause" goto :done

echo.
echo Window will close in 5s or press any key to close now.
timeout /t 5 >nul 2>nul || pause >nul

:done
endlocal
