param(
    [string]$PythonProject = (Join-Path $PSScriptRoot '../../python-ai'),
    [string]$OutputZip = (Join-Path $PSScriptRoot '..\..\artifacts\zhixueban-cloud-trial.zip')
)

$ErrorActionPreference = 'Stop'
$frontend = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonRoot = (Resolve-Path -LiteralPath $PythonProject).Path
$zip = [IO.Path]::GetFullPath($OutputZip)
if (Test-Path -LiteralPath $zip) { throw "Output already exists. Choose another -OutputZip path. $zip" }
$tempRoot = (Resolve-Path ([IO.Path]::GetTempPath())).Path
$stage = Join-Path $tempRoot ('zhixue-cloud-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path (Join-Path $stage 'server/backend'), (Join-Path $stage 'frontend')

try {
    foreach ($name in 'Dockerfile', 'compose.yaml', 'Caddyfile', '.env.example', '.dockerignore', 'README.md') {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $stage
    }
    foreach ($name in 'package.json', 'package-lock.json', 'index.html', 'tsconfig.json', 'vite.config.ts') {
        Copy-Item -LiteralPath (Join-Path $frontend $name) -Destination (Join-Path $stage 'frontend')
    }
    foreach ($folder in 'src', 'public') {
        $files = Get-ChildItem -LiteralPath (Join-Path $frontend $folder) -File -Recurse
        foreach ($file in $files) {
            if ($file.Extension -notin '.ts', '.tsx', '.css', '.svg', '.webp', '.png', '.jpg', '.woff2') {
                throw "Unexpected front-end file type in deployment input: $($file.FullName)"
            }
            $relative = $file.FullName.Substring($frontend.Length + 1)
            $destination = Join-Path (Join-Path $stage 'frontend') $relative
            $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination)
            Copy-Item -LiteralPath $file.FullName -Destination $destination
        }
    }
    foreach ($name in 'requirements.txt', 'generate_from_file.py', 'multimodal_reader.py', 'automatic_question_validator.py') {
        Copy-Item -LiteralPath (Join-Path $pythonRoot $name) -Destination (Join-Path $stage 'server')
    }
    $backendFiles = '__init__.py', 'account_space.py', 'account_web.py', 'agent_api.py', 'agent_journal.py', 'agent_loop.py', 'config.py', 'content_exporter.py', 'exam_practice.py', 'file_storage.py',
        'job_store.py', 'job_timing.py', 'observability.py', 'knowledge_extractor.py', 'literal_evidence.py', 'model_status.py', 'practice_coverage.py', 'practice_quality.py', 'practice_variety.py',
        'schemas.py', 'study_tools.py', 'tool_registry.py', 'web_api.py', 'web_content.py', 'web_practice.py', 'web_question_review.py', 'worker.py'
    foreach ($name in $backendFiles) {
        $source = Join-Path $pythonRoot "backend/$name"
        $destination = Join-Path $stage "server/backend/$name"
        if ($name -in 'web_api.py', 'web_content.py', 'worker.py') {
            [IO.File]::WriteAllText($destination, [IO.File]::ReadAllText($source).Replace("`r`n", "`n"))
        } else {
            Copy-Item -LiteralPath $source -Destination $destination
        }
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'web_trial.py') -Destination (Join-Path $stage 'server/backend')
    foreach ($name in 'trial_body_limit.py', 'trial_access.html', 'web_submissions.py', 'resumable_uploads.py', 'study_chat.py', 'study_mnemonics.py') {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $stage 'server/backend')
    }
    git -C (Join-Path $stage 'server') apply (Join-Path $PSScriptRoot 'backend.patch')
    if ($LASTEXITCODE -ne 0) { throw 'The Python sources have changed. Refresh backend.patch and verify the trial before exporting.' }
    git -C (Join-Path $stage 'server') apply (Join-Path $PSScriptRoot 'study_backend.patch')
    if ($LASTEXITCODE -ne 0) { throw 'Could not apply the Web study chat integration.' }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $zip)
    [IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip)
    Get-Item -LiteralPath $zip | Select-Object FullName, Length
} finally {
    if (Test-Path -LiteralPath $stage) {
        $resolvedStage = Get-Item -LiteralPath $stage
        if ($resolvedStage.Parent.FullName -eq $tempRoot -and $resolvedStage.Name -match '^zhixue-cloud-[0-9a-f]{32}$') {
            Remove-Item -LiteralPath $resolvedStage.FullName -Recurse -Force
        }
    }
}
