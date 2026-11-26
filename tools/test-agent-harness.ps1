param(
    [switch]$WithAccounts,
    [string]$JavaHome = $env:JAVA_HOME
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $project 'python-ai/.venv/Scripts/python.exe'
$verification = Join-Path $project ('web-prototype/.verification/harness-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $verification
$oldPythonPath = $env:PYTHONPATH
$oldAdapter = $env:AI_WEB_DATA_DIR
$oldData = $env:AI_DATA_DIR
$oldJava = $env:JAVA_HOME
$oldUtf8 = $env:PYTHONUTF8
Push-Location $project
try {
    if ($JavaHome) { $env:JAVA_HOME = $JavaHome }
    $env:PYTHONUTF8 = '1'
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency baseline failed' }
    npm.cmd --prefix web-prototype run build
    if ($LASTEXITCODE -ne 0) { throw 'Web build failed' }
    $archive = Join-Path $verification 'backend.zip'
    & ./web-prototype/deploy/prepare.ps1 -PythonProject (Join-Path $project 'python-ai') -OutputZip $archive
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $verification 'package')
    $env:PYTHONPATH = Join-Path $verification 'package/server'
    $env:AI_WEB_DATA_DIR = Join-Path $verification 'adapter'
    $env:AI_DATA_DIR = Join-Path $verification 'android-ai'
    $report = Join-Path $verification 'pytest.xml'
    # Keep source-only tests in a separate process: Windows spawn inherits
    # pytest's sys.path, so collecting python-ai here can shadow the package.
    & $python -m pytest -q web-prototype/deploy/test_web_trial.py web-prototype/deploy/test_harness_boundary.py web-prototype/deploy/test_study_tools.py "--junitxml=$report"
    if ($LASTEXITCODE -ne 0) { throw 'Harness baseline failed; inspect pytest.xml' }
    $env:PYTHONPATH = $oldPythonPath
    $unitReport = Join-Path $verification 'unit.xml'
    & $python -m pytest -q python-ai/test_harness_baseline.py python-ai/test_account_space.py python-ai/test_agent_api.py python-ai/test_practice_coverage.py python-ai/test_web_question_review.py python-ai/evaluation/test_zh06.py "--junitxml=$unitReport"
    if ($LASTEXITCODE -ne 0) { throw 'Harness unit baseline failed; inspect unit.xml' }
    if ($WithAccounts) {
        & ./tools/test-web-account.ps1
    }
    Write-Output "Harness verification: $verification"
} finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:AI_WEB_DATA_DIR = $oldAdapter
    $env:AI_DATA_DIR = $oldData
    $env:JAVA_HOME = $oldJava
    $env:PYTHONUTF8 = $oldUtf8
    Pop-Location
}
