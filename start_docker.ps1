[CmdletBinding()]
param(
    [string]$DataDirectory = (Join-Path $PSScriptRoot "data"),
    [string]$Image = "ghcr.io/fewnfds/deepagent-shell:latest"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$data = [System.IO.Path]::GetFullPath($DataDirectory)
$settings = Join-Path $data "config\agent-shell.env"
New-Item -ItemType Directory -Force -Path $data | Out-Null

$mount = "type=bind,source=$data,target=/app/data"
& docker.exe run --rm -it `
    --user "10001:10001" `
    --mount $mount `
    $Image `
    python -I -B -m agent_shell `
    --home /app `
    --data-dir /app/data `
    --initialize-docker-settings
if ($LASTEXITCODE -ne 0) {
    throw "Agent Shell Docker settings could not be prepared."
}

$previousDataDirectory = $env:COMPOSE_DATA_DIR
$previousImage = $env:AGENT_SHELL_IMAGE
try {
    $env:COMPOSE_DATA_DIR = $data
    $env:AGENT_SHELL_IMAGE = $Image
    & docker.exe compose `
        --project-directory $project `
        --env-file $settings `
        -f (Join-Path $project "compose.yaml") `
        up -d --wait --wait-timeout 60
    if ($LASTEXITCODE -ne 0) {
        throw "Agent Shell Docker service did not become healthy."
    }
}
finally {
    $env:COMPOSE_DATA_DIR = $previousDataDirectory
    $env:AGENT_SHELL_IMAGE = $previousImage
}

$hostPort = 19100
foreach ($line in Get-Content -LiteralPath $settings) {
    if ($line -match '^\s*AGENT_SHELL_PORT\s*=\s*([0-9]+)\s*$') {
        $hostPort = [int]$Matches[1]
    }
}
Write-Host "Agent Shell is ready: http://127.0.0.1:$hostPort/admin"
Write-Host "Persistent data: $data"
