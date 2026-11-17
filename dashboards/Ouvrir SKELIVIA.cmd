@echo off
where node >nul 2>&1
if errorlevel 1 (
  echo Node.js est necessaire pour ouvrir le serveur local SKELIVIA.
  echo Vous pouvez aussi ouvrir maquette\index.html dans votre navigateur.
  pause
  exit /b 1
)
node "%~dp0verification\ouvrir-maquette.cjs" %*
if errorlevel 1 pause
