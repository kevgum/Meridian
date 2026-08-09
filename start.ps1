# =============================================================================
# start.ps1 - Meridian Sentinel full-stack bootstrap (Windows / PowerShell)
# =============================================================================
# Run once after cloning to bring the entire stack up and verify it works.
# Subsequent runs restart any stopped services and re-run smoke tests.
#
# Requirements: Docker Desktop 4.x+ running (no local Python needed)
#
# Usage (run from project root in PowerShell):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # once, if needed
#   .\start.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

# Colour helpers
function Step  { param($msg) Write-Host "`n$([char]0x25B6) $msg" -ForegroundColor Green }
function Info  { param($msg) Write-Host "  -> $msg" -ForegroundColor Cyan }
function Warn  { param($msg) Write-Host "  ! $msg"  -ForegroundColor Yellow }
function Ok    { param($msg) Write-Host "  OK $msg" -ForegroundColor Green }
function Fail  { param($msg) Write-Host "`nError: $msg" -ForegroundColor Red; exit 1 }

# =============================================================================
# 1. Pre-flight checks
# =============================================================================
Step "Checking prerequisites"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed. Download from https://www.docker.com/products/docker-desktop"
}

try {
    docker info 2>$null | Out-Null
} catch {
    Fail "Docker daemon is not running. Start Docker Desktop and try again."
}

try {
    docker compose version 2>$null | Out-Null
} catch {
    Fail "Docker Compose plugin not found. Update Docker Desktop to 4.x or later."
}

$dockerVersion = (docker --version) -replace "Docker version ", "" -replace ",.*", ""
Ok "Docker $dockerVersion"
Ok "Docker Compose $(docker compose version --short)"

# =============================================================================
# 2. Bootstrap environment
# =============================================================================
Step "Setting up environment"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Ok "Created .env from .env.example"
    Fail @"
Set ELASTIC_PASSWORD in .env before starting the stack.

.env.example ships a placeholder, and Elasticsearch seeds the elastic
superuser from this value on first boot - so an unedited placeholder
silently becomes the live cluster password.

Edit .env, set a real ELASTIC_PASSWORD, then re-run .\start.ps1
"@
} else {
    Ok ".env already exists - skipping"
}

# Read ELASTIC_PASSWORD from .env for health-check polling.
# No fallback default: an unset or placeholder password must fail loudly
# rather than seeding the cluster with a guessable credential.
$envContent = Get-Content ".env" | Where-Object { $_ -match "^ELASTIC_PASSWORD=" }
if ($envContent) {
    $elasticPassword = ($envContent -split "=", 2)[1].Trim()
} else {
    $elasticPassword = ""
}

if (-not $elasticPassword -or $elasticPassword -eq "change_me_before_running") {
    Fail "ELASTIC_PASSWORD is unset or still the placeholder in .env. Set a real value and re-run."
}

# The lstm-serving container writes its ONNX output into this directory.
# Docker will not create it automatically.
New-Item -ItemType Directory -Force -Path "models\serving\lstm_v1" | Out-Null
Ok "models\serving\lstm_v1\ directory ready"

# =============================================================================
# 3. Build Docker images
# =============================================================================
Step "Building Docker images"
Info "First build downloads PyTorch CPU (~550 MB) and dev tools - takes 3-5 minutes."
Info "Subsequent builds use the layer cache and are near-instant."

docker compose --profile dev build
Ok "Images built"

# =============================================================================
# 4. Start infrastructure services
# =============================================================================
Step "Starting services"
docker compose up -d elasticsearch kibana logstash lstm-serving
Ok "Containers started in background"

# =============================================================================
# 5. Wait for Elasticsearch
# =============================================================================
Step "Waiting for Elasticsearch"
$esMax = 24   # 24 x 5 s = 120 s maximum wait
$esReady = $false
for ($i = 1; $i -le $esMax; $i++) {
    try {
        $base64Auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("elastic:$elasticPassword"))
        $response = Invoke-WebRequest `
            -Uri "http://localhost:9200/_cluster/health" `
            -Headers @{ Authorization = "Basic $base64Auth" } `
            -UseBasicParsing `
            -TimeoutSec 5 `
            -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Ok "Elasticsearch is healthy"
            $esReady = $true
            break
        }
    } catch {
        # Not ready yet
    }
    if ($i -eq $esMax) {
        Fail "Elasticsearch did not become healthy after 120 s.`nDiagnose with: docker compose logs elasticsearch --tail 40"
    }
    Info "Attempt $i/$esMax - retrying in 5 s..."
    Start-Sleep -Seconds 5
}

# =============================================================================
# 6. Wait for LSTM Inference API
# =============================================================================
Step "Waiting for LSTM Inference API"
Info "First start converts lstm_checkpoint_best.pt to ONNX (~15 s extra)."
$lstmMax = 36   # 36 x 5 s = 180 s maximum wait
$lstmReady = $false
for ($i = 1; $i -le $lstmMax; $i++) {
    try {
        $response = Invoke-WebRequest `
            -Uri "http://localhost:8080/v1/models/lstm" `
            -UseBasicParsing `
            -TimeoutSec 5 `
            -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Ok "LSTM API is healthy"
            $lstmReady = $true
            break
        }
    } catch {
        # Not ready yet
    }
    if ($i -eq $lstmMax) {
        Fail "LSTM API did not become healthy after 180 s.`nDiagnose with: docker compose logs lstm-serving --tail 40"
    }
    Info "Attempt $i/$lstmMax - retrying in 5 s..."
    Start-Sleep -Seconds 5
}

# =============================================================================
# 7. Run full test suite inside the dev container
# =============================================================================
Step "Running test suite inside Docker"
Info "SIEM unit tests run immediately. LSTM API tests call http://lstm-serving:8080."

docker compose --profile dev run --rm dev pytest tests/ -v
$testExit = $LASTEXITCODE

Write-Host ""
if ($testExit -ne 0) {
    Warn "Some tests failed (exit $testExit). Review the output above."
    Warn "Integration tests (AT-1/AT-6) can fail on first boot if Logstash or RBAC"
    Warn "are not ready yet - re-run:  docker compose --profile dev run --rm dev pytest tests/ -v"
} else {
    Ok "All tests passed"
}

# =============================================================================
# 8. Print service summary
# =============================================================================
Step "Stack is up"
Write-Host ""
Write-Host "  LSTM Inference API  ->  http://localhost:8080/v1/models/lstm" -ForegroundColor Cyan
Write-Host "  Kibana              ->  http://localhost:5601  (sign in as elastic)" -ForegroundColor Cyan
Write-Host "  Elasticsearch       ->  http://localhost:9200" -ForegroundColor Cyan
Write-Host "  Logstash TCP        ->  localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Re-run tests:       docker compose --profile dev run --rm dev pytest tests/ -v" -ForegroundColor Yellow
Write-Host "  Latency benchmark:  docker compose --profile dev run --rm dev python -m src.benchmark" -ForegroundColor Yellow
Write-Host "  Type check:         docker compose --profile dev run --rm dev mypy src/" -ForegroundColor Yellow
Write-Host "  Stop the stack:     docker compose down" -ForegroundColor Yellow
Write-Host ""
