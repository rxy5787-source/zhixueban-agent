param(
    [string]$PythonProject = 'E:\GraduationProject\AdaptiveQuestionAI',
    [ValidateRange(1024, 65535)][int]$Port = 8095
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$project = Split-Path -Parent $PSScriptRoot
$web = Join-Path $project 'web-prototype'
$python = Join-Path (Resolve-Path -LiteralPath $PythonProject) '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw "Python virtual environment missing: $python" }
$work = Join-Path $web '.verification/study-local'
$build = Join-Path $work ('builds/' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Force -Path $build

& (Join-Path $web 'deploy/prepare.ps1') -PythonProject $PythonProject -OutputZip (Join-Path $build 'source.zip')
Expand-Archive -LiteralPath (Join-Path $build 'source.zip') -DestinationPath $build
# The Vite development configuration is unnecessary when the backend serves the built assets.
$env:VITE_ONLINE_TRIAL = 'false'
npm.cmd --prefix $web run build -- --outDir (Join-Path $build 'public')
if ($LASTEXITCODE -ne 0) { throw 'Web build failed.' }

$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:AI_WEB_DATA_DIR = Join-Path $work 'adapter'
$env:TRIAL_DATA_DIR = Join-Path $work 'data'
$env:TRIAL_FRONTEND_DIR = Join-Path $build 'public'
$env:TRIAL_PUBLIC_ORIGIN = "http://127.0.0.1:$Port"
# No invitation gate is needed on this loopback-only preview.
$env:TRIAL_ACCESS_CODE = $null
$env:TRIAL_CLOUDFLARE_PROXY = '0'
$env:TRIAL_LOCAL_PREVIEW = '1'
$keyFile = Join-Path $work 'session.key'
if (!(Test-Path -LiteralPath $keyFile)) {
    [IO.File]::WriteAllText($keyFile, (([guid]::NewGuid().ToString('N')) + ([guid]::NewGuid().ToString('N'))))
}
$env:TRIAL_SECRET = [IO.File]::ReadAllText($keyFile)
Write-Host "知学伴学习对话预览  $env:TRIAL_PUBLIC_ORIGIN/#home"
Write-Host '资料生成需要本机 Ollama 的 qwen3:1.7b。'
Push-Location (Join-Path $build 'server')
try {
    & $python -m uvicorn backend.web_trial:from_environment --factory --host 127.0.0.1 --port $Port --no-proxy-headers
} finally {
    Pop-Location
}
