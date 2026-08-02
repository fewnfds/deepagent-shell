[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PortableRoot,

    [int]$Port = 19100,

    [switch]$Cleanup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$homePath = [System.IO.Path]::GetFullPath($PortableRoot)
$runtimeManifestPath = Join-Path $homePath "runtime\app\runtime-manifest.json"
$releaseManifestPath = Join-Path $homePath "release-manifest.json"
if (
    -not (Test-Path -LiteralPath $runtimeManifestPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $releaseManifestPath -PathType Leaf)
) {
    throw "PortableRoot is not a generated Agent Shell release directory."
}
$runtimeManifest = Get-Content -LiteralPath $runtimeManifestPath -Raw | ConvertFrom-Json
if ($runtimeManifest.application -ne "agent-shell" -or $runtimeManifest.platform -ne "windows-x64") {
    throw "PortableRoot has an unexpected runtime manifest."
}

$pythonHome = (Get-Content -LiteralPath (Join-Path $homePath "runtime\app\python-home.txt") -Raw).Trim()
$python = Join-Path (Join-Path $homePath "runtime\app") (Join-Path $pythonHome "python.exe")
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "The portable Python executable is missing."
}
$launcher = Join-Path $homePath "start_server.bat"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "The one-click launcher is missing."
}

$settingsPath = Join-Path $homePath "data\config\agent-shell.env"
$databasePath = Join-Path $homePath "data\state\agent-shell.sqlite3"
$stdoutPath = Join-Path $homePath "runtime\tmp\portable-smoke.stdout.log"
$stderrPath = Join-Path $homePath "runtime\tmp\portable-smoke.stderr.log"
$logsRoot = Join-Path $homePath "data\logs"
$createdPaths = @($settingsPath, $databasePath, "$databasePath-wal", "$databasePath-shm", $stdoutPath, $stderrPath)
$existingLogFiles = @{}
if (Test-Path -LiteralPath $logsRoot -PathType Container) {
    foreach ($file in Get-ChildItem -LiteralPath $logsRoot -File -Recurse) {
        $existingLogFiles[$file.FullName] = $true
    }
}
if (
    (Test-Path -LiteralPath $settingsPath) -or
    (Test-Path -LiteralPath $databasePath)
) {
    throw "Portable smoke requires a fresh disposable release directory."
}

$environmentNames = @(
    "AGENT_SHELL_HOST",
    "AGENT_SHELL_UNKNOWN"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [System.Environment]::GetEnvironmentVariable($name, "Process")
}
$process = $null
try {
    & $python -I -B -X utf8 -c `
        "from pathlib import Path; from agent_shell.__main__ import initialize_local_settings; import sys; raise SystemExit(initialize_local_settings(application_home=Path(sys.argv[1]), password_reader=lambda _: 'portable-smoke-password'))" `
        $homePath
    if ($LASTEXITCODE -ne 0) {
        throw "Portable first-run initialization failed."
    }
    & $python -I -B -X utf8 -c `
        "from pathlib import Path; from agent_shell.storage.permissions import secure_file; import re, sys; path = Path(sys.argv[1]); text = path.read_text(encoding='utf-8'); text, count = re.subn(r'(?m)^AGENT_SHELL_PORT=.*$', 'AGENT_SHELL_PORT=' + sys.argv[2], text); assert count == 1; path.write_text(text, encoding='utf-8'); assert secure_file(path).enforced" `
        $settingsPath `
        ([string]$Port)
    if ($LASTEXITCODE -ne 0) {
        throw "Portable smoke could not select its isolated port."
    }

    $env:AGENT_SHELL_HOST = "0.0.0.0"
    $env:AGENT_SHELL_UNKNOWN = "must-be-ignored"
    $quotedLauncher = '"' + $launcher + '"'
    $process = Start-Process -FilePath $env:ComSpec `
        -ArgumentList @("/d", "/c", $quotedLauncher) `
        -WorkingDirectory $homePath `
        -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:${Port}/api/health" -TimeoutSec 2
            if ($response.status -eq "ok") {
                $healthy = $true
                break
            }
        }
        catch {
        }
        if ($process.HasExited) {
            break
        }
    }
    if (-not $healthy) {
        Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue
        Get-Content -LiteralPath $stderrPath -ErrorAction SilentlyContinue
        throw "Moved portable runtime did not become healthy."
    }
    if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
        throw "Portable mode did not create its database under the moved application home."
    }
    $modulePath = & $python -I -B -X utf8 -c "import agent_shell, pathlib; print(pathlib.Path(agent_shell.__file__).resolve())"
    if ($LASTEXITCODE -ne 0 -or -not ([string]$modulePath).StartsWith($homePath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Agent Shell imported code from outside the moved portable release."
    }
    Write-Host "Portable smoke passed: health=ok, home=$homePath"
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F *> $null
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
        $process.WaitForExit(5000) | Out-Null
    }
    foreach ($name in $environmentNames) {
        [System.Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], "Process")
    }
    if ($Cleanup) {
        foreach ($path in $createdPaths) {
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                Remove-Item -LiteralPath $path -Force
            }
        }
        if (Test-Path -LiteralPath $logsRoot -PathType Container) {
            foreach ($file in Get-ChildItem -LiteralPath $logsRoot -File -Recurse) {
                if (-not $existingLogFiles.ContainsKey($file.FullName)) {
                    Remove-Item -LiteralPath $file.FullName -Force
                }
            }
        }
    }
}
