#requires -Version 5.1
<#
.SYNOPSIS
  End-to-end Rolls-Royce build pipeline for the SecondBrain Desktop
  installer on Windows.

.DESCRIPTION
  Produces a single ``dist\SecondBrainDesktop-{version}-setup.exe``
  that contains every artifact needed to install SecondBrain on a
  fresh Windows machine WITHOUT requiring Python or pipx on the host:

    1. PyInstaller bundle for the tray app (``SecondBrainTray.exe``
       and its ``_internal/`` deps).
    2. Embedded Python runtime (downloaded from python.org, cached).
    3. ``memory-kit-mcp`` wheel + every transitive dependency wheel
       (built/downloaded into ``build\release-kit\engine\wheels``).
    4. ``get-pip.py`` for bootstrapping pip inside the embedded Python
       at install time.
    5. Kit resources (``core/``, ``adapters/``, ``i18n/``) shipped as
       a clean release tree — NOT a copy of the dev checkout.

  The first launch of ``SecondBrainTray.exe`` runs the in-app setup
  wizard, which uses these artifacts to install the engine and wire
  MCP into every detected LLM CLI — pure Python, no ``deploy.ps1``.

.PARAMETER Clean
  Wipe ``build/.venv-build/``, ``dist/``, and
  ``build/release-kit/`` before starting.

.PARAMETER IsccPath
  Override the path to ``ISCC.exe``. Defaults to the standard
  ``%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe``.

.PARAMETER PythonVersion
  Embedded Python version to bundle. Default: 3.12.7.

.EXAMPLE
  .\build\build_windows.ps1 -Clean
#>

[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$IsccPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [string]$PythonVersion = '3.12.7'
)

$ErrorActionPreference = 'Stop'

$RepoRoot   = (Resolve-Path "$PSScriptRoot\..").Path
$BuildDir   = Join-Path $RepoRoot 'build'
$DistDir    = Join-Path $RepoRoot 'dist'
$ReleaseKit = Join-Path $BuildDir 'release-kit'
$WheelsDir  = Join-Path $ReleaseKit 'engine\wheels'
$EnginePyDir = Join-Path $ReleaseKit 'engine\python'
$EngineDir  = Join-Path $ReleaseKit 'engine'
$ResourcesDir = Join-Path $ReleaseKit 'resources'
$VenvDir    = Join-Path $BuildDir '.venv-build'
$CacheDir   = Join-Path $BuildDir '.cache'
$IconsDir   = Join-Path $BuildDir 'generated-icons'
$Spec       = Join-Path $BuildDir 'sb-desktop.spec'
$IssFile    = Join-Path $BuildDir 'installer.iss'
$McpServerDir = Join-Path (Split-Path $RepoRoot -Parent) 'mcp-server'
$KitRoot    = Split-Path $RepoRoot -Parent

if ($Clean) {
    foreach ($d in @($VenvDir, $DistDir, $ReleaseKit, $IconsDir)) {
        if (Test-Path $d) { Remove-Item -Recurse -Force $d }
    }
}

Write-Host "==> Repository:   $RepoRoot"
Write-Host "==> Release kit:  $ReleaseKit"
Write-Host "==> Python embed: $PythonVersion"

# ---------------------------------------------------------------------------
# 0. Set up the build venv used for PyInstaller + wheel building.
# ---------------------------------------------------------------------------
if (-not (Test-Path $VenvDir)) {
    Write-Host '==> Creating build venv'
    python -m venv $VenvDir
}

$Py  = Join-Path $VenvDir 'Scripts\python.exe'

Write-Host '==> Installing build venv deps'
& $Py -m pip install --upgrade pip wheel build

# Install the engine in editable mode so PyInstaller can sweep
# ``memory_kit_mcp`` and its transitive deps for the in-process bundled
# desktop copy. (Distinct from the wheels we ship — see below.)
if (-not (Test-Path $McpServerDir)) {
    throw "memory-kit-mcp source not found at $McpServerDir"
}
& $Py -m pip install -e $McpServerDir
& $Py -m pip install -e "$RepoRoot[windows,build]"

# ---------------------------------------------------------------------------
# 1. Download the Python embeddable runtime (cached).
# ---------------------------------------------------------------------------
New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
$arch = if ([Environment]::Is64BitOperatingSystem) { 'amd64' } else { 'win32' }
$EmbedZipName = "python-$PythonVersion-embed-$arch.zip"
$EmbedZip = Join-Path $CacheDir $EmbedZipName
$EmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/$EmbedZipName"

if (-not (Test-Path $EmbedZip)) {
    Write-Host "==> Downloading Python embeddable $PythonVersion ($arch)"
    Invoke-WebRequest -Uri $EmbedUrl -OutFile $EmbedZip
}

if (Test-Path $EnginePyDir) { Remove-Item -Recurse -Force $EnginePyDir }
New-Item -ItemType Directory -Path $EnginePyDir -Force | Out-Null
Expand-Archive -Path $EmbedZip -DestinationPath $EnginePyDir -Force

# ---------------------------------------------------------------------------
# 2. Download get-pip.py (cached).
# ---------------------------------------------------------------------------
$GetPip = Join-Path $CacheDir 'get-pip.py'
if (-not (Test-Path $GetPip)) {
    Write-Host '==> Downloading get-pip.py'
    Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $GetPip
}
Copy-Item -Path $GetPip -Destination (Join-Path $EngineDir 'get-pip.py') -Force

# ---------------------------------------------------------------------------
# 3. Build memory-kit-mcp wheel + pull every transitive dep wheel.
# ---------------------------------------------------------------------------
New-Item -ItemType Directory -Path $WheelsDir -Force | Out-Null

Write-Host '==> Building memory-kit-mcp wheel'
$McpDist = Join-Path $McpServerDir 'dist'
if (Test-Path $McpDist) { Remove-Item -Recurse -Force $McpDist }
& $Py -m build --wheel --outdir $McpDist $McpServerDir

# Copy the built wheel into the release-kit's wheels dir.
Get-ChildItem -Path $McpDist -Filter '*.whl' | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $WheelsDir -Force
}

Write-Host '==> Resolving transitive deps as wheels (offline-installable bundle)'
# Pin to the embedded Python version so we don't fetch wheels for the
# wrong ABI tag.
$PyTag = ($PythonVersion -split '\.')[0..1] -join ''  # e.g. 312
& $Py -m pip download `
    --dest $WheelsDir `
    --no-deps `
    "$($(Get-ChildItem -Path $WheelsDir -Filter 'memory_kit_mcp*.whl' | Select-Object -First 1).FullName)" | Out-Null

# Resolve all deps with pip wheel into the bundle.
& $Py -m pip wheel `
    --wheel-dir $WheelsDir `
    --no-deps `
    "$($(Get-ChildItem -Path $WheelsDir -Filter 'memory_kit_mcp*.whl' | Select-Object -First 1).FullName)" | Out-Null

# Now resolve runtime deps recursively. Use the engine wheel's
# Requires-Dist by pip-downloading it with deps enabled.
& $Py -m pip download `
    --dest $WheelsDir `
    --only-binary :all: `
    --python-version $PythonVersion `
    --platform win_amd64 `
    --implementation cp `
    --abi "cp$PyTag" `
    "$($(Get-ChildItem -Path $WheelsDir -Filter 'memory_kit_mcp*.whl' | Select-Object -First 1).FullName)"

# ---------------------------------------------------------------------------
# 4. Stage kit resources (NOT a copy of the dev tree — only what the kit
#    needs at runtime: procedures, adapter templates, i18n strings).
# ---------------------------------------------------------------------------
if (Test-Path $ResourcesDir) { Remove-Item -Recurse -Force $ResourcesDir }
New-Item -ItemType Directory -Path $ResourcesDir -Force | Out-Null

foreach ($sub in @('core', 'adapters')) {
    $src = Join-Path $KitRoot $sub
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $ResourcesDir -Recurse -Force
    }
}

# Optional i18n directory if it lives outside core/.
$i18nDir = Join-Path $KitRoot 'core\i18n'
if (Test-Path $i18nDir) {
    $i18nDest = Join-Path $ResourcesDir 'i18n'
    if (-not (Test-Path $i18nDest)) {
        Copy-Item -Path $i18nDir -Destination $i18nDest -Recurse -Force
    }
}

# Drop dev cruft from the resources tree.
Get-ChildItem -Path $ResourcesDir -Recurse -Force -Directory `
    -Include '__pycache__','.venv','.pytest_cache','node_modules' `
    | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $ResourcesDir -Recurse -Force -Filter '*.pyc' `
    | Remove-Item -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------------------
# 5. Generate desktop icons.
# ---------------------------------------------------------------------------
Write-Host '==> Generating desktop icons'
& $Py -m sb_desktop.icons --export $IconsDir | Out-Null

# ---------------------------------------------------------------------------
# 6. PyInstaller bundle (the tray app itself).
# ---------------------------------------------------------------------------
Write-Host '==> Running PyInstaller'
Push-Location $RepoRoot
try {
    & $Py -m PyInstaller --noconfirm --clean $Spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 7. Inno Setup — assemble everything into a single installer .exe.
# ---------------------------------------------------------------------------
if (-not (Test-Path $IsccPath)) {
    Write-Warning "ISCC.exe not found at $IsccPath — installer step skipped."
    Write-Host "Install Inno Setup 6 from https://jrsoftware.org/isinfo.php"
    return
}

Write-Host '==> Compiling installer'
& $IsccPath /Q $IssFile
if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed with exit code $LASTEXITCODE"
}

Write-Host '==> Done.'
Get-ChildItem $DistDir -Filter 'SecondBrain*Setup*.exe', 'SecondBrainDesktop*setup.exe' -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Artifact: $($_.FullName)"
}
