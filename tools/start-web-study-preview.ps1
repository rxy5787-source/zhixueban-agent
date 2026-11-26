param(
    [string]$PythonProject = (Join-Path $PSScriptRoot '../python-ai'),
    [ValidateRange(1024, 65535)][int]$Port = 8095,
    [string]$PublicOrigin,
    [string]$LandingOrigin
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$project = Split-Path -Parent $PSScriptRoot
$web = Join-Path $project 'web-prototype'
$public = [bool]$PublicOrigin
if ($public) {
    if (!$LandingOrigin -or $env:TRIAL_ACCESS_CODE.Length -lt 12 -or $env:TRIAL_ACCESS_CODE.Length -gt 128) {
        throw 'Set LandingOrigin and a new TRIAL_ACCESS_CODE (12 to 128 characters) for public study.'
    }
    foreach ($origin in $PublicOrigin, $LandingOrigin) {
        $uri = [uri]$origin
        if (!$uri.IsAbsoluteUri -or $uri.Scheme -ne 'https' -or $uri.UserInfo -or $origin -ne $uri.GetLeftPart([System.UriPartial]::Authority)) {
            throw 'Use HTTPS origins without a trailing slash, path or credentials.'
        }
    }
} elseif ($LandingOrigin) {
    throw 'LandingOrigin requires PublicOrigin.'
}
$python = Join-Path (Resolve-Path -LiteralPath $PythonProject) '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw "Python virtual environment missing: $python" }
$work = Join-Path $web $(if ($public) { '.verification/study-public' } else { '.verification/study-local' })
$build = Join-Path $work ('builds/' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Force -Path $build

& (Join-Path $web 'deploy/prepare.ps1') -PythonProject $PythonProject -OutputZip (Join-Path $build 'source.zip')
Expand-Archive -LiteralPath (Join-Path $build 'source.zip') -DestinationPath $build
# Keep mobile uploads resumable for the public trial.
$env:VITE_ONLINE_TRIAL = if ($public) { 'true' } else { 'false' }
npm.cmd --prefix $web run build -- --outDir (Join-Path $build 'public')
if ($LASTEXITCODE -ne 0) { throw 'Web build failed.' }

$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:AI_WEB_DATA_DIR = Join-Path $work 'adapter'
$env:TRIAL_DATA_DIR = Join-Path $work 'data'
$env:TRIAL_FRONTEND_DIR = Join-Path $build 'public'
$env:TRIAL_PUBLIC_ORIGIN = if ($public) { $PublicOrigin } else { "http://127.0.0.1:$Port" }
$env:TRIAL_LANDING_ORIGIN = if ($public) { $LandingOrigin } else { $null }
if (!$public) { $env:TRIAL_ACCESS_CODE = $null }
$env:TRIAL_CLOUDFLARE_PROXY = '0'
$env:TRIAL_LOCAL_PREVIEW = if ($public) { '0' } else { '1' }
$keyFile = Join-Path $work 'session.key'
if (!(Test-Path -LiteralPath $keyFile)) {
    [IO.File]::WriteAllText($keyFile, (([guid]::NewGuid().ToString('N')) + ([guid]::NewGuid().ToString('N'))))
}
$env:TRIAL_SECRET = [IO.File]::ReadAllText($keyFile)
Write-Host "知学伴学习对话预览  $env:TRIAL_PUBLIC_ORIGIN/#home"
Write-Host '资料生成需要本机 Ollama 的 qwen3:1.7b。'
Push-Location (Join-Path $build 'server')
try {
    & $python -m uvicorn backend.web_trial:from_environment --factory --host 127.0.0.1 --port $Port --no-proxy-headers --no-access-log
} finally {
    Pop-Location
}
