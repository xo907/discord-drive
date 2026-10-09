# Builds dist\DiscordDrive.exe, a single program that needs neither Python nor git.
# Usage (PowerShell, from the repository folder):  packaging\build_exe.ps1
# WinFsp still has to be installed separately (https://winfsp.dev/rel/): it is a driver.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m pip install --upgrade pyinstaller pillow
python -m PyInstaller --noconfirm --clean --onefile --console `
    --name DiscordDrive `
    --icon docs\images\logo-128.png `
    --add-data "discorddrive\web;discorddrive\web" `
    --add-data "CHANGELOG.md;." `
    --collect-submodules discorddrive `
    packaging\entry.py
Write-Host "Built dist\DiscordDrive.exe"
