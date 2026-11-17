@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0simulateur\start_simulator.ps1"
if errorlevel 1 pause
