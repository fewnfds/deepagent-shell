[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [switch]$SkipFrontend,
    [switch]$RebuildRuntime
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$project = [System.IO.Path]::GetFullPath($ProjectRoot)
$frontend = Join-Path $project "frontend"
$serverRoot = Join-Path $project "server"
$bootstrap = Join-Path $project "packaging\windows\bootstrap_runtime.ps1"
$releaseRoot = Join-Path $project "release"
$stageRoot = Join-Path $releaseRoot "agent-shell-windows-x64"
$archivePath = Join-Path $releaseRoot "agent-shell-windows-x64.zip"
$metadataGenerator = Join-Path $project "packaging\release\generate_release_metadata.py"
$manifestGenerator = Join-Path $project "packaging\release\generate_release_manifest.py"
$surfaceChecker = Join-Path $project "packaging\release\check_release_surface.py"

function Install-CurrentApplication {
    param(
        [Parameter(Mandatory = $true)][string]$PortablePython,
        [Parameter(Mandatory = $true)][string]$PythonHome
    )

    $uvExe = Join-Path $project "runtime\bootstrap\uv.exe"
    if (-not (Test-Path -LiteralPath $uvExe -PathType Leaf)) {
        throw "The verified uv bootstrap executable is missing."
    }
    $runtimeRoot = [System.IO.Path]::GetFullPath((Join-Path $project "runtime"))
    $buildRoot = [System.IO.Path]::GetFullPath((Join-Path $runtimeRoot "tmp\release-app-$PID"))
    $runtimePrefix = $runtimeRoot.TrimEnd("\") + "\"
    if (-not $buildRoot.StartsWith($runtimePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to use an application build path outside runtime."
    }
    if (Test-Path -LiteralPath $buildRoot) {
        Remove-Item -LiteralPath $buildRoot -Recurse -Force
    }
    $wheelRoot = Join-Path $buildRoot "wheel"
    $extractRoot = Join-Path $buildRoot "extract"
    New-Item -ItemType Directory -Force -Path $wheelRoot, $extractRoot | Out-Null

    try {
        & $uvExe build --project $serverRoot --wheel --out-dir $wheelRoot
        if ($LASTEXITCODE -ne 0) {
            throw "The Agent Shell application wheel build failed."
        }
        $wheels = @(Get-ChildItem -LiteralPath $wheelRoot -Filter "agent_shell_server-*.whl" -File)
        if ($wheels.Count -ne 1) {
            throw "Expected exactly one Agent Shell wheel, found $($wheels.Count)."
        }
        if ($wheels[0].BaseName -notmatch '^agent_shell_server-(?<version>.+?)-py3-none-any$') {
            throw "The Agent Shell wheel filename does not expose the application version."
        }
        $applicationVersion = $Matches.version
        & $PortablePython -I -B -m zipfile -e $wheels[0].FullName $extractRoot
        if ($LASTEXITCODE -ne 0) {
            throw "The Agent Shell application wheel could not be extracted."
        }

        $applicationPackage = Join-Path $extractRoot "agent_shell"
        $applicationMetadata = @(
            Get-ChildItem -LiteralPath $extractRoot -Directory -Filter "agent_shell_server-*.dist-info"
        )
        if (
            -not (Test-Path -LiteralPath (Join-Path $applicationPackage "frontend_dist\index.html") -PathType Leaf) -or
            $applicationMetadata.Count -ne 1
        ) {
            throw "The Agent Shell wheel does not contain the current production application."
        }

        $sitePackages = Join-Path (Join-Path $project "runtime\app") (Join-Path $PythonHome "Lib\site-packages")
        $installedPackage = Join-Path $sitePackages "agent_shell"
        if (Test-Path -LiteralPath $installedPackage) {
            Remove-Item -LiteralPath $installedPackage -Recurse -Force
        }
        Get-ChildItem -LiteralPath $sitePackages -Directory -Filter "agent_shell_server-*.dist-info" |
            Remove-Item -Recurse -Force
        Copy-Item -LiteralPath $applicationPackage -Destination $installedPackage -Recurse
        Copy-Item -LiteralPath $applicationMetadata[0].FullName -Destination $sitePackages -Recurse

        $installedModule = & $PortablePython -I -B -c "import agent_shell; print(agent_shell.__file__)"
        if ($LASTEXITCODE -ne 0) {
            throw "The portable Python cannot import the current Agent Shell application."
        }
        $installedModulePath = [System.IO.Path]::GetFullPath([string]$installedModule)
        $applicationPrefix = ([System.IO.Path]::GetFullPath((Join-Path $project "runtime\app"))).TrimEnd("\") + "\"
        if (-not $installedModulePath.StartsWith($applicationPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Agent Shell was imported from outside the portable runtime."
        }

        $manifestPath = Join-Path $project "runtime\app\runtime-manifest.json"
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $manifest | Add-Member -NotePropertyName version -NotePropertyValue $applicationVersion -Force
        $manifest | Add-Member -NotePropertyName application_sha256 `
            -NotePropertyValue ((Get-FileHash -LiteralPath $wheels[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()) `
            -Force
        $manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8
    }
    finally {
        if (Test-Path -LiteralPath $buildRoot) {
            Remove-Item -LiteralPath $buildRoot -Recurse -Force
        }
    }
}

function Copy-TrackedTree {
    param([Parameter(Mandatory = $true)][string]$Prefix)
    $trackedFiles = @(
        & git.exe -C $project -c core.quotepath=false ls-files -- $Prefix
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Could not enumerate tracked files under $Prefix."
    }
    foreach ($relativePath in $trackedFiles) {
        $source = Join-Path $project $relativePath
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "A tracked release file is missing: $relativePath"
        }
        $destination = Join-Path $stageRoot $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }
}

if (-not $SkipFrontend) {
    Push-Location $frontend
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "The frontend production build failed." }
    }
    finally {
        Pop-Location
    }
}

$windowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$bootstrapArguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", $bootstrap,
    "-ProjectRoot", $project
)
if ($RebuildRuntime) {
    $bootstrapArguments += "-Force"
}
& $windowsPowerShell @bootstrapArguments
if ($LASTEXITCODE -ne 0) {
    throw "The portable runtime build failed."
}

$portablePythonHome = (Get-Content -LiteralPath (Join-Path $project "runtime\app\python-home.txt") -Raw).Trim()
$portablePython = Join-Path (Join-Path $project "runtime\app") (Join-Path $portablePythonHome "python.exe")
Install-CurrentApplication -PortablePython $portablePython -PythonHome $portablePythonHome
& $portablePython -I -B $surfaceChecker
if ($LASTEXITCODE -ne 0) {
    throw "The release surface check failed."
}

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
$releasePrefix = $releaseRoot.TrimEnd("\") + "\"
$stageFullPath = [System.IO.Path]::GetFullPath($stageRoot)
if (-not $stageFullPath.StartsWith($releasePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to replace a staging path outside the release directory."
}
if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

foreach ($file in @("start_server.bat", ".env.example", "README.md", "LICENSE")) {
    Copy-Item -LiteralPath (Join-Path $project $file) -Destination (Join-Path $stageRoot $file)
}
Copy-TrackedTree "docs"
New-Item -ItemType Directory -Force -Path (Join-Path $stageRoot "runtime") | Out-Null
Copy-Item -LiteralPath (Join-Path $project "runtime\app") -Destination (Join-Path $stageRoot "runtime\app") -Recurse
New-Item -ItemType Directory -Force -Path @(
    (Join-Path $stageRoot "data\config"),
    (Join-Path $stageRoot "data\state"),
    (Join-Path $stageRoot "data\files"),
    (Join-Path $stageRoot "data\resources\skills"),
    (Join-Path $stageRoot "data\resources\custom_tools"),
    (Join-Path $stageRoot "data\resources\custom_middlewares"),
    (Join-Path $stageRoot "data\logs"),
    (Join-Path $stageRoot "runtime\cache"),
    (Join-Path $stageRoot "runtime\tmp"),
    (Join-Path $stageRoot "runtime\home")
) | Out-Null

$runtimeManifest = Get-Content -LiteralPath (Join-Path $stageRoot "runtime\app\runtime-manifest.json") -Raw |
    ConvertFrom-Json
$version = [string]$runtimeManifest.version
& $portablePython -I -B $metadataGenerator `
    --runtime-root (Join-Path $stageRoot "runtime\app") `
    --frontend-root $frontend `
    --version $version `
    --notices (Join-Path $stageRoot "THIRD_PARTY_NOTICES.md") `
    --sbom (Join-Path $stageRoot "SBOM.spdx.json") `
    --licenses (Join-Path $stageRoot "THIRD_PARTY_LICENSES")
if ($LASTEXITCODE -ne 0) {
    throw "Release license and SBOM generation failed."
}
$repositoryNotices = Join-Path $project "THIRD_PARTY_NOTICES.md"
$generatedNotices = Join-Path $stageRoot "THIRD_PARTY_NOTICES.md"
$repositoryNoticesText = if (Test-Path -LiteralPath $repositoryNotices -PathType Leaf) {
    (Get-Content -LiteralPath $repositoryNotices -Raw).Replace("`r`n", "`n")
} else {
    ""
}
$generatedNoticesText = (Get-Content -LiteralPath $generatedNotices -Raw).Replace("`r`n", "`n")
if (
    -not $repositoryNoticesText -or
    $repositoryNoticesText -ne $generatedNoticesText
) {
    throw "THIRD_PARTY_NOTICES.md is stale. Regenerate it with generate_release_metadata.py."
}
& $portablePython -I -B $manifestGenerator `
    --root $stageRoot `
    --version $version `
    --output (Join-Path $stageRoot "release-manifest.json")
if ($LASTEXITCODE -ne 0) {
    throw "Release manifest generation failed."
}
& $portablePython -I -B $surfaceChecker --portable-root $stageRoot
if ($LASTEXITCODE -ne 0) {
    throw "The portable release surface check failed."
}

if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
$tarExe = Join-Path $env:SystemRoot "System32\tar.exe"
if (-not (Test-Path -LiteralPath $tarExe -PathType Leaf)) {
    throw "Windows tar.exe is required to create the portable ZIP."
}
& $tarExe -a -cf $archivePath -C $releaseRoot (Split-Path $stageRoot -Leaf)
if ($LASTEXITCODE -ne 0) {
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    throw "The portable ZIP creation failed with exit code $LASTEXITCODE."
}
$hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$archivePath.sha256" -Value "$hash *$(Split-Path $archivePath -Leaf)" -Encoding ascii
Write-Host "Portable release created: $archivePath"
Write-Host "SHA-256: $hash"
