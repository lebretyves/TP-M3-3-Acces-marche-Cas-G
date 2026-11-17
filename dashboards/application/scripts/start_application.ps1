param([switch]$Build, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $appRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop est requis pour ouvrir cette application.' }
    if (-not (Test-Path -LiteralPath '.runtime/infra/secrets/app_database_url')) { throw 'Infrastructure non preparee. Suivre application/INFRA.md avant le premier demarrage.' }
    docker compose -f infra/compose.yaml config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Configuration Docker invalide.' }
    if ($Build) {
        docker compose -f infra/compose.yaml build app
        if ($LASTEXITCODE -ne 0) { throw 'Construction interrompue.' }
    }
    docker compose -f infra/compose.yaml up -d db broker keycloak
    if ($LASTEXITCODE -ne 0) { throw 'Docker indisponible ou services prives non demarres.' }
    docker compose -f infra/compose.yaml run --rm --no-deps -T migrate
    if ($LASTEXITCODE -ne 0) { throw 'Migration interrompue ; aucune suppression de volume effectuee.' }
    docker compose -f infra/compose.yaml up -d app worker push proxy
    if ($LASTEXITCODE -ne 0) { throw 'Demarrage applicatif incomplet ; consulter INFRA.md.' }
    docker compose -f infra/compose.yaml restart proxy
    if ($LASTEXITCODE -ne 0) { throw 'Actualisation du proxy interrompue.' }
    Write-Host 'Application : https://localhost:8443'
    Write-Host 'Certificat local : voir application/README.md. Aucun ajout automatique de confiance.'
    if (-not $NoBrowser) { Start-Process 'https://localhost:8443' }
} finally { Pop-Location }
