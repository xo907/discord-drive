@echo off
setlocal

:: Run from this folder so "python -m discorddrive" finds the package.
cd /d "%~dp0"

:: Find Python: prefer the py launcher, then python on PATH.
set "PYTHON_EXE="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=py -3"
if not defined PYTHON_EXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo [ERROR] Python 3 was not found. Install it from https://www.python.org/downloads/
    exit /b 1
)

:: No arguments = mount in the foreground.
if "%~1"=="" (
    %PYTHON_EXE% -m discorddrive mount
) else (
    %PYTHON_EXE% -m discorddrive %*
)
exit /b %ERRORLEVEL%
