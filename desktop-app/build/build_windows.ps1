#requires -Version 5.1
<#
.SYNOPSIS
  End-to-end build pipeline for the Windows installer.

.DESCRIPTION
  1. Creates / refreshes a build virtualenv with pyinstaller + the desktop app
     in editable mode + the optional ``windows`` extras.
  2. Generates the static icon assets (PNG + ICO) under ``build/generated-icons/``.
  3. Runs PyInstaller against ``build/sb-desktop.spec`` to produce
     ``dist/SecondBrainTray/``.
  4. Invokes Inno Setup (must be on PATH or pointed at via ``-IsccPath``)
     against ``build/installer.iss`` to assemble ``dist/SecondBrainSetup.exe``.

  Run from any CWD; paths are resolved relative to the repo, not the caller.

.PARAMETER Clean
  If specified, deletes ``build/.venv`` and ``dist/`` before starting so
  the build is fully reproducible.

.PARAMETER IsccPath
  Override the path to ``ISCC.exe``. Defaults to the standard
  ``%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe`` location.

.EXAMPLE
  .\build\build_windows.ps1 -Clean
#>

[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$IsccPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$VenvDir  = Join-Path $RepoRoot '.venv-build'
$DistDir  = Join-Path $RepoRoot 'dist'
$Spec     = Join-Path $RepoRoot 'build\sb-desktop.spec'
$IconsDir = Join-Path $RepoRoot 'build\generated-icons'
$IssFile  = Join-Path $RepoRoot 'build\installer.iss'

if ($Clean) {
    if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
    if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
    if (Test-Path $IconsDir) { Remove-Item -Recurse -Force $IconsDir }
}

Write-Host "==> Repository: $RepoRoot"

if (-not (Test-Path $VenvDir)) {
    Write-Host '==> Creating build venv'
    python -m venv $VenvDir
}

$Py  = Join-Path $VenvDir 'Scripts\python.exe'
$Pip = Join-Path $VenvDir 'Scripts\pip.exe'

Write-Host '==> Installing build deps'
& $Py -m pip install --upgrade pip wheel
& $Pip install -e "$RepoRoot[windows,build]"

Write-Host '==> Generating static icons'
& $Py -m sb_desktop.icons --export $IconsDir | Out-Null

Write-Host '==> Running PyInstaller'
$Spec = $Spec.Trim()
& $Py -m PyInstaller --noconfirm --clean $Spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $IsccPath)) {
    Write-Warning "ISCC.exe not found at $IsccPath — installer step skipped."
    Write-Host 'Pass -IsccPath to point at your Inno Setup install, or'
    Write-Host 'install Inno Setup 6 from https://jrsoftware.org/isinfo.php.'
    return
}

Write-Host '==> Compiling installer'
& $IsccPath /Q $IssFile
if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed with exit code $LASTEXITCODE"
}

Write-Host '==> Done.'
Get-ChildItem $DistDir -Filter 'SecondBrain*Setup*.exe' | ForEach-Object {
    Write-Host "Artifact: $($_.FullName)"
}
