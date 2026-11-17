@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0application\scripts\start_application.ps1"
if errorlevel 1 pause
