<#
.SYNOPSIS
    Build the offline engine wheelhouse asset for a SecondBrain engine release.

.DESCRIPTION
    Produces `memory_kit_mcp-<version>-wheelhouse-win_amd64.zip` — a flat zip of
    `memory_kit_mcp` plus every transitive dependency as cp312 / win_amd64
    wheels. The SecondBrain Desktop app downloads this asset and runs
    `pip install --no-index --find-links <extracted>` against its embedded
    Python (3.12, win_amd64) to upgrade the engine in place, fully offline and
    version-pinned (no PyPI at update time — corporate-network safe).

    Steps:
      1. Build the engine wheel (`uv build` in mcp-server) so the local
         memory-kit-mcp wheel is available to the resolver.
      2. `pip download` memory-kit-mcp + deps, pinned to cp312 / win_amd64,
         binary-only, into a wheelhouse directory.
      3. Zip it next to the engine wheel (mcp-server/dist by default).

    Run this for EVERY engine release and attach the resulting zip — see the
    release discipline (scripts up to date, setup regenerated, ALL concerned
    assets attached, systematically).

.PARAMETER Version
    Engine version (e.g. 0.14.0). Defaults to the version in
    mcp-server/pyproject.toml.

.PARAMETER OutDir
    Where to write the wheelhouse dir + zip. Defaults to mcp-server/dist.
#>
[CmdletBinding()]
param(
    [string]$Version,
    [string]$OutDir
)

$ErrorActionPreference = "Stop"

$repoRoot   = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$engineDir  = Join-Path $repoRoot "mcp-server"
$distDir    = Join-Path $engineDir "dist"
if (-not $OutDir) { $OutDir = $distDir }

if (-not $Version) {
    $pyproject = Get-Content (Join-Path $engineDir "pyproject.toml") -Raw
    if ($pyproject -match '(?m)^version\s*=\s*"([^"]+)"') {
        $Version = $Matches[1]
    } else {
        throw "Could not resolve engine version from pyproject.toml; pass -Version."
    }
}

Write-Host "Building engine wheelhouse for memory-kit-mcp $Version" -ForegroundColor Cyan

# 1. Build the engine wheel so the resolver can find memory-kit-mcp locally.
Push-Location $engineDir
try {
    uv build
} finally {
    Pop-Location
}

$wheel = Get-ChildItem (Join-Path $distDir "memory_kit_mcp-$Version-*.whl") -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $wheel) {
    throw "Engine wheel memory_kit_mcp-$Version-*.whl not found in $distDir after build."
}

# 2. Download memory-kit-mcp + all deps as cp312 / win_amd64 binary wheels.
$wheelhouse = Join-Path $OutDir "wheelhouse-$Version"
if (Test-Path $wheelhouse) { Remove-Item $wheelhouse -Recurse -Force }
New-Item -ItemType Directory -Force $wheelhouse | Out-Null

python -m pip download "memory-kit-mcp==$Version" `
    --find-links $distDir `
    --dest $wheelhouse `
    --only-binary=:all: `
    --implementation cp `
    --python-version 3.12 `
    --abi cp312 `
    --platform win_amd64
if ($LASTEXITCODE -ne 0) {
    throw "pip download failed (exit $LASTEXITCODE). A dependency may lack a cp312/win_amd64 wheel."
}

$wheelCount = (Get-ChildItem (Join-Path $wheelhouse "*.whl")).Count
Write-Host "Collected $wheelCount wheel(s) into $wheelhouse" -ForegroundColor Green

# 3. Zip the wheelhouse (flat: *.whl at the zip root).
$zip = Join-Path $OutDir "memory_kit_mcp-$Version-wheelhouse-win_amd64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $wheelhouse "*.whl") -DestinationPath $zip -Force

$sizeMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Wheelhouse asset: $zip ($sizeMB MB)" -ForegroundColor Green
Write-Host "Attach it to the engine release v${Version}:" -ForegroundColor Yellow
Write-Host "  gh release upload v$Version `"$zip`"" -ForegroundColor Yellow
