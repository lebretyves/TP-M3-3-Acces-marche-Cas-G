param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
$simRoot=$PSScriptRoot
$application=Join-Path (Split-Path -Parent $simRoot) 'application'
$compose=Join-Path $application 'infra/compose.yaml'
$overlay=Join-Path $simRoot 'compose.yaml'
$python=Join-Path $application '.venv/Scripts/python.exe'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop est requis.' }
$services=@(docker compose -f $compose ps --status running --services)
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop doit etre demarre.' }
if ('app' -notin $services -or 'worker' -notin $services -or 'broker' -notin $services) {
    & (Join-Path $application 'scripts/start_application.ps1') -NoBrowser
}
$activeState=$null
try { $activeState=(Invoke-RestMethod 'http://127.0.0.1:8774/api/state' -TimeoutSec 2).state.status } catch { }
if ($activeState -in @('preparing','running','paused','stopping')) {
    Write-Host 'Une simulation est deja active ; ouverture sans interruption.'
    if (-not $NoBrowser) { Start-Process 'https://localhost:8443/simulateur/' }
    return
}
& $python (Join-Path $simRoot 'prepare_transport.py')
if ($LASTEXITCODE -ne 0) { throw 'Preparation du simulateur refusee. Les droits et calibrations ne sont pas modifies.' }
docker compose -f $compose -f $overlay --profile simulator up -d --no-deps --force-recreate simulator
if ($LASTEXITCODE -ne 0) { throw 'Le simulateur ne peut pas demarrer.' }
$ready=$false
for ($attempt=0;$attempt -lt 40;$attempt++) {
    try { $health=Invoke-RestMethod 'http://127.0.0.1:8774/api/health' -TimeoutSec 1; if ($health.ok) { $ready=$true; break } } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw 'Le simulateur ne repond pas encore sur le port 8774.' }
Write-Host 'Simulateur : https://localhost:8443/simulateur/'
if (-not $NoBrowser) { Start-Process 'https://localhost:8443/simulateur/' }
