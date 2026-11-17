@echo off
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0application\scripts\show_test_access.ps1"
if errorlevel 1 pause
