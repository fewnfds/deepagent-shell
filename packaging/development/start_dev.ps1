[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$PythonExe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$project = [System.IO.Path]::GetFullPath($ProjectRoot)
$python = [System.IO.Path]::GetFullPath($PythonExe)
$frontend = Join-Path $project "frontend"
$source = Join-Path $project "server\src"
$vite = Join-Path $frontend "node_modules\.bin\vite.cmd"
$backend = $null
$dataRoot = $null
$createdDataRoot = $false

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "The bundled development Python is missing."
}
if (-not (Test-Path -LiteralPath (Join-Path $source "agent_shell\__main__.py") -PathType Leaf)) {
    throw "The Agent Shell Python source tree is missing."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "package.json") -PathType Leaf)) {
    throw "The Agent Shell frontend source tree is missing."
}
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npm) {
    throw "Explicit frontend Debug requires Node.js 22 with npm."
}

function Get-FreeLoopbackPort {
    param([int[]]$ExcludedPorts = @())

    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Loopback,
            0
        )
        try {
            $listener.Start()
            $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
        }
        finally {
            $listener.Stop()
        }
        if ($port -notin $ExcludedPorts) {
            return $port
        }
    }
    throw "Windows did not provide two distinct loopback ports for Debug."
}

function New-TemporaryBearerToken {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

$frontendPort = Get-FreeLoopbackPort
$backendPort = Get-FreeLoopbackPort -ExcludedPorts @($frontendPort)
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$temporaryPrefix = $temporaryRoot.TrimEnd("\") + "\"
$dataRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $temporaryRoot ("agent-shell-debug-" + [guid]::NewGuid().ToString("N")))
)
if (-not $dataRoot.StartsWith($temporaryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create Debug data outside the system temporary directory."
}
$existingAgentShellNames = @()
$managedEnvironmentNames = @()
$previousEnvironment = @{}

try {
    New-Item -ItemType Directory -Path $dataRoot | Out-Null
    $createdDataRoot = $true

    $existingAgentShellNames = @(
        [System.Environment]::GetEnvironmentVariables("Process").Keys |
            Where-Object { [string]$_ -like "AGENT_SHELL_*" }
    )
    $managedEnvironmentNames = @(
        $existingAgentShellNames
        "AGENT_SHELL_HOST"
        "AGENT_SHELL_PORT"
        "AGENT_SHELL_ALLOW_REMOTE"
        "AGENT_SHELL_MANAGEMENT_TOKEN"
        "PYTHONHOME"
        "PYTHONPATH"
        "PYTHONNOUSERSITE"
        "VITE_API_PROXY_TARGET"
    ) | Select-Object -Unique
    foreach ($name in $managedEnvironmentNames) {
        $previousEnvironment[$name] = [System.Environment]::GetEnvironmentVariable(
            $name,
            "Process"
        )
    }
    foreach ($name in $existingAgentShellNames) {
        [System.Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
    $temporaryManagementPassword = New-TemporaryBearerToken
    $temporaryApiKey = New-TemporaryBearerToken
    $env:AGENT_SHELL_HOST = "127.0.0.1"
    $env:AGENT_SHELL_PORT = [string]$backendPort
    $env:AGENT_SHELL_ALLOW_REMOTE = "false"
    $env:AGENT_SHELL_MANAGEMENT_TOKEN = $temporaryManagementPassword
    $env:PYTHONHOME = $null
    $env:PYTHONPATH = $source
    $env:PYTHONNOUSERSITE = "1"
    $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$backendPort"

    if (-not (Test-Path -LiteralPath $vite -PathType Leaf)) {
        Write-Host "Preparing frontend Debug dependencies..."
        & $npm.Source --prefix $frontend ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed with exit code $LASTEXITCODE."
        }
    }

    $backendArguments = @(
        "-s", "-P", "-B", "-X", "utf8",
        "-m", "agent_shell",
        "--home", ".",
        "--data-dir", ('"{0}"' -f $dataRoot),
        "--mode", "environment",
        "--no-frontend"
    )
    $backend = Start-Process -FilePath $python `
        -ArgumentList $backendArguments `
        -WorkingDirectory $project `
        -PassThru `
        -NoNewWindow

    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($backend.HasExited) {
            throw "The isolated Python Debug backend exited with code $($backend.ExitCode)."
        }
        try {
            $response = Invoke-RestMethod `
                -Uri "http://127.0.0.1:$backendPort/api/health" `
                -TimeoutSec 1
            if ($response.status -eq "ok") {
                $healthy = $true
                break
            }
        }
        catch {
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $healthy) {
        throw "The isolated Python Debug backend did not become healthy."
    }

    $apiKeyBody = @{
        api_key = @{
            operation = "replace"
            value = $temporaryApiKey
        }
    } | ConvertTo-Json -Depth 3 -Compress
    Invoke-RestMethod `
        -Uri "http://127.0.0.1:$backendPort/api/api-server" `
        -Method Put `
        -Headers @{ Authorization = "Bearer $temporaryManagementPassword" } `
        -ContentType "application/json" `
        -Body $apiKeyBody | Out-Null

    Write-Host ""
    Write-Host "Agent Shell explicit frontend Debug"
    Write-Host "  URL: http://127.0.0.1:$frontendPort/admin/"
    Write-Host "  Temporary management password: $temporaryManagementPassword"
    Write-Host "  Temporary API Key: $temporaryApiKey"
    Write-Host "  Temporary data: $dataRoot"
    Write-Host "  Vite hot reload is active. Press Ctrl+C to stop and clean up."
    Write-Host ""

    & $npm.Source --prefix $frontend run dev -- `
        --host 127.0.0.1 `
        --port $frontendPort `
        --strictPort
    $viteExitCode = $LASTEXITCODE
    if ($viteExitCode -notin @(0, -1, -1073741510, 130)) {
        throw "The Vite Debug server exited with code $viteExitCode."
    }
}
finally {
    if ($null -ne $backend) {
        if (-not $backend.HasExited) {
            Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
            $backend.WaitForExit(5000) | Out-Null
        }
        $backend.Dispose()
    }
    foreach ($name in $managedEnvironmentNames) {
        [System.Environment]::SetEnvironmentVariable(
            $name,
            $previousEnvironment[$name],
            "Process"
        )
    }
    if (
        $createdDataRoot -and
        $null -ne $dataRoot -and
        $dataRoot.StartsWith($temporaryPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $dataRoot)
    ) {
        Remove-Item -LiteralPath $dataRoot -Recurse -Force
    }
}
