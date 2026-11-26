param()

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$verification = Join-Path $project ('web-prototype/.verification/web-account-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $verification
$archive = Join-Path $verification 'backend.zip'
$python = Join-Path $project 'python-ai/.venv/Scripts/python.exe'
$java = (Get-Command java.exe -ErrorAction Stop).Source
$javaLibraries = Join-Path $project 'auth-server/build/install/auth-server/lib/*'
$log = Join-Path $verification 'auth.log'
$oldPythonPath = $env:PYTHONPATH
$oldAuthUrl = $env:ZHIXUE_TEST_AUTH_URL
$server = $null

Push-Location $project
try {
    .\gradlew.bat :auth-server:test :auth-server:installDist --offline --no-daemon
    if ($LASTEXITCODE -ne 0) { throw 'Spring Boot build or tests failed' }
    & ./web-prototype/deploy/prepare.ps1 -PythonProject (Join-Path $project 'python-ai') -OutputZip $archive
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $verification 'package')
    $env:PYTHONPATH = Join-Path $verification 'package/server'
    $serverArguments = @(
        '-classpath', ('"' + $javaLibraries + '"'), 'com.zhixue.auth.AuthServer',
        '--server.port=0', '--server.address=127.0.0.1',
        '--spring.datasource.url=jdbc:h2:mem:web-account-tests;DB_CLOSE_DELAY=-1',
        '--spring.datasource.username=sa', '--spring.datasource.password=',
        '--spring.sql.init.mode=always',
        '--spring.sql.init.schema-locations=classpath:schema.sql,classpath:migrations/V001__account_learning_space.sql',
        '--auth.learning-space.enabled=true', '--auth.session-seconds=60'
    )
    $server = Start-Process -FilePath $java -ArgumentList $serverArguments -WorkingDirectory $verification -RedirectStandardOutput $log -RedirectStandardError (Join-Path $verification 'auth-error.log') -WindowStyle Hidden -PassThru
    $deadline = (Get-Date).AddSeconds(35)
    do {
        if ($server.HasExited) { throw "Test auth service exited. See $log" }
        $started = Select-String -LiteralPath $log -Pattern 'Tomcat started on port (\d+)' | Select-Object -First 1
        if ($started) { break }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
    if (-not $started) { throw "Test auth service did not start. See $log" }
    $env:ZHIXUE_TEST_AUTH_URL = 'http://127.0.0.1:' + $started.Matches[0].Groups[1].Value

    & $python -m pytest -q web-prototype/deploy/test_account_web.py web-prototype/deploy/test_web_trial.py
    if ($LASTEXITCODE -ne 0) { throw 'Web account or trial regression tests failed' }
    $env:PYTHONPATH = $oldPythonPath
    & $python -m pytest -q python-ai/test_account_space.py python-ai/test_agent_api.py
    if ($LASTEXITCODE -ne 0) { throw 'Account resolver or Agent regression tests failed' }
} finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id }
    $env:PYTHONPATH = $oldPythonPath
    $env:ZHIXUE_TEST_AUTH_URL = $oldAuthUrl
    Pop-Location
}
