param(
    [ValidateRange(1024, 65535)][int]$Port = 18122,
    [string]$BindAddress = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$pythonRoot = Join-Path $project 'python-ai'
$python = Join-Path $pythonRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw "Python virtual environment missing: $python" }
$previousTrialData = $env:ZHIXUE_AGENT_TRIAL_DATA
if ([string]::IsNullOrWhiteSpace($previousTrialData)) {
    $env:ZHIXUE_AGENT_TRIAL_DATA = Join-Path $project 'web-prototype/.verification/study-local/data'
}
Write-Host "Agent API Web data directory: $env:ZHIXUE_AGENT_TRIAL_DATA"
Push-Location $pythonRoot
try {
    & $python -B -m uvicorn backend.agent_api:from_environment --factory --host $BindAddress --port $Port --no-proxy-headers --no-access-log
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
    $env:ZHIXUE_AGENT_TRIAL_DATA = $previousTrialData
}
