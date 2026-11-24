# Shared by start.ps1, stop.ps1, reset.ps1, status.ps1 and uninstall.ps1 (Windows PowerShell 5.1 or later).
# Needs only Docker Desktop. The .cmd files next to this run these scripts without changing the execution policy.
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
Set-Location $Here
$Version = if (Test-Path "$Here\VERSION") { (Get-Content "$Here\VERSION" -Raw).Trim() } else { 'dev' }
$Images = @('circularity-trial-api', 'circularity-trial-web', 'circularity-trial-source-sim')

function Stop-WithError([string]$msg) { Write-Host "ERROR  $msg" -ForegroundColor Red; exit 1 }
function Write-Step([string]$msg) { Write-Host "==  $msg" }

function Test-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Stop-WithError 'Docker is not installed. Install Docker Desktop, start it, then run this again.'
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'Docker Desktop is not running. Start it, wait until it says it is running, then run this again.' }
    docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { Stop-WithError "Docker Compose v2 is missing ('docker compose'). Update Docker Desktop." }
}

function Import-Images {
    $missing = $false
    foreach ($img in $Images) { docker image inspect "${img}:$Version" *> $null; if ($LASTEXITCODE -ne 0) { $missing = $true } }
    docker image inspect postgres:16-alpine *> $null; if ($LASTEXITCODE -ne 0) { $missing = $true }
    if (-not $missing) { return }
    if (-not (Test-Path "$Here\images.tar.gz")) { Stop-WithError "images.tar.gz is missing from $Here. Unpack the whole trial package again." }
    Write-Step "Loading the app's images (first start only, about a minute)"
    docker load -i "$Here\images.tar.gz" | Out-Null
    if ($LASTEXITCODE -ne 0) { Stop-WithError 'docker load failed. Is there enough free disk space (about 3 GB)?' }
}

function New-Secret([int]$bytes, [switch]$KeepPadding) {
    $b = New-Object byte[] $bytes
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    $s = [Convert]::ToBase64String($b).Replace('+', '-').Replace('/', '_')
    if ($KeepPadding) { $s } else { $s.TrimEnd('=') }
}

function Write-EnvFile {
    if (Test-Path "$Here\.env") { return }
    $port = if ($env:TRIAL_PORT) { $env:TRIAL_PORT } else { '5173' }
    $lines = @(
        '# Written by the start script on first start. Keep it private: it holds this installation''s secrets.',
        '# TRIAL_PORT: the port the app opens on (http://localhost:TRIAL_PORT). Change it if 5173 is taken, then start again.',
        "TRIAL_PORT=$port",
        'BIND_ADDR=127.0.0.1',
        "POSTGRES_PASSWORD=$(New-Secret 24)",
        "DI_JWT_SECRET=$(New-Secret 48)",
        "DI_WEBHOOK_SECRET=$(New-Secret 48)",
        "DI_SECRET_KEY=$(New-Secret 32 -KeepPadding)",
        '# Optional: a free key from console.groq.com makes Ask Circularity answer with a language model.',
        'GROQ_API_KEY='
    )
    # UTF-8 without a byte-order mark and LF endings: Docker Compose reads the first key wrongly after a BOM
    [IO.File]::WriteAllText("$Here\.env", (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    Write-Step 'Wrote .env with new secrets for this installation'
}

function Get-Port {
    $line = Get-Content "$Here\.env" -ErrorAction SilentlyContinue | Where-Object { $_ -match '^TRIAL_PORT=(\d+)' } | Select-Object -First 1
    if ($line -match '^TRIAL_PORT=(\d+)') { $Matches[1] } else { '5173' }
}

function Invoke-Compose {
    docker compose --project-directory "$Here" -f "$Here\compose.yml" @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose $args failed" }
}

function Wait-Ready {
    Write-Step 'Starting (the first start takes 1 to 3 minutes while the demo data is loaded)'
    docker compose --project-directory "$Here" -f "$Here\compose.yml" up -d --wait --wait-timeout 900
    if ($LASTEXITCODE -ne 0) {
        docker compose --project-directory "$Here" -f "$Here\compose.yml" ps -a
        Stop-WithError 'The app did not become ready. See the logs with: docker compose -f compose.yml logs --tail=80'
    }
    $url = "http://localhost:$(Get-Port)"
    Write-Host ''
    Write-Host "Circularity is running:  $url" -ForegroundColor Green
    Write-Host 'Sign in with any of: admin, exec, planner.a, planner.b, planner.c, approver, engineer, finance, developer,'
    Write-Host 'warehouse1, warehouse2 (any password). START-HERE.md has a short tour.'
    if ($env:TRIAL_NO_BROWSER -ne '1') { Start-Process $url }
}
