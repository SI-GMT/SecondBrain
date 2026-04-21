#Requires -Version 7.0

<#
.SYNOPSIS
    Deploie le kit memoire dans chaque CLI IA detectee sur le poste.

.DESCRIPTION
    Detecte les CLI IA installees (Claude Code, Gemini CLI, Codex, Mistral Vibe)
    et deploie l'adapter correspondant pour chacune. Ne plante pas si une CLI
    est absente : elle est simplement skippee. Si aucune CLI n'est trouvee,
    un message amical explique quoi installer.

.PARAMETER VaultPath
    Chemin absolu du vault memoire. Par defaut : {racine du kit}/memory.

.PARAMETER Force
    Ecrase memory-kit.json meme s'il existe deja (Claude Code uniquement
    pour l'instant).

.EXAMPLE
    .\deploy.ps1
    .\deploy.ps1 -VaultPath "D:\mes-notes\cerveau"
    .\deploy.ps1 -Force
#>

[CmdletBinding()]
param(
    [string]$VaultPath,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ============================================================
# Helpers d'affichage
# ============================================================

function Write-Step([string]$msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn2([string]$msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Skip([string]$msg) { Write-Host "  [--] $msg" -ForegroundColor DarkGray }
function Write-Info([string]$msg) { Write-Host "  [i]  $msg" -ForegroundColor DarkCyan }

# ============================================================
# Detection des CLI IA
# ============================================================

function Test-CliInstalled {
    param([string]$Binary, [string]$ConfigDir)
    # CLI consideree installee si le binaire est sur le PATH OU si le dossier
    # de config existe (= elle a deja tourne sur ce poste).
    $hasBinary = $null -ne (Get-Command $Binary -ErrorAction SilentlyContinue)
    $hasConfig = $ConfigDir -and (Test-Path $ConfigDir)
    return $hasBinary -or $hasConfig
}

# ============================================================
# Adapter : Claude Code
# ============================================================

function Deploy-ClaudeCode {
    param(
        [string]$KitRoot,
        [string]$ConfigDir,
        [string]$VaultPath,
        [switch]$Force
    )

    Write-Host ''
    Write-Step "> Deploiement : Claude Code"

    if (-not (Test-Path $ConfigDir)) {
        Write-Warn2 "Dossier Claude Code introuvable ($ConfigDir). Lance Claude Code au moins une fois."
        return $false
    }

    # Sous-dossiers cibles
    $commandsTarget = Join-Path $ConfigDir 'commands'
    $skillsTarget   = Join-Path $ConfigDir 'skills'
    foreach ($d in @($commandsTarget, $skillsTarget)) {
        if (-not (Test-Path $d)) {
            New-Item -ItemType Directory -Path $d -Force | Out-Null
        }
    }

    # Commands (copie directe)
    $commandsSource = Join-Path $KitRoot 'adapters\claude-code\commands'
    Get-ChildItem -Path $commandsSource -Filter '*.md' | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination (Join-Path $commandsTarget $_.Name) -Force
        Write-Ok "Command : $($_.Name)"
    }

    # Skills (template + procedure core + substitution CONFIG_FILE)
    $skillsSource = Join-Path $KitRoot 'adapters\claude-code\skills'
    $coreSource   = Join-Path $KitRoot 'core\procedures'
    $configFileRef = '`~/.claude/memory-kit.json` (ou `$CLAUDE_CONFIG_DIR/memory-kit.json` si defini)'
    Get-ChildItem -Path $skillsSource -Filter '*.template.md' | ForEach-Object {
        $skillName = $_.Name -replace '\.template\.md$', ''
        $templateContent = Get-Content -Path $_.FullName -Raw
        $procedurePath = Join-Path $coreSource "$skillName.md"
        if (-not (Test-Path $procedurePath)) {
            Write-Warn2 "Procedure core manquante pour $skillName (ignore)"
            return
        }
        $procedureContent = Get-Content -Path $procedurePath -Raw
        $procedureContent = $procedureContent -replace '\{\{CONFIG_FILE\}\}', $configFileRef
        $assembled = $templateContent -replace '\{\{PROCEDURE\}\}', $procedureContent
        Set-Content -Path (Join-Path $skillsTarget "$skillName.md") -Value $assembled -Encoding UTF8 -NoNewline
        Write-Ok "Skill   : $skillName.md"
    }

    # memory-kit.json
    $configFile = Join-Path $ConfigDir 'memory-kit.json'
    $configData = [ordered]@{ vault = $VaultPath } | ConvertTo-Json
    if ((Test-Path $configFile) -and -not $Force) {
        Write-Skip "memory-kit.json preserve (utiliser -Force pour ecraser)"
    } else {
        Set-Content -Path $configFile -Value $configData -Encoding UTF8 -NoNewline
        Write-Ok "memory-kit.json -> vault = $VaultPath"
    }

    # Bloc MEMORY-KIT dans CLAUDE.md utilisateur (idempotent)
    $claudeMdTarget = Join-Path $ConfigDir 'CLAUDE.md'
    $blockPath = Join-Path $KitRoot 'adapters\claude-code\claude-md-block.md'
    $blockContent = Get-Content -Path $blockPath -Raw
    $startMarker = '<!-- MEMORY-KIT:START -->'
    $endMarker   = '<!-- MEMORY-KIT:END -->'
    $existing = if (Test-Path $claudeMdTarget) { (Get-Content -Path $claudeMdTarget -Raw) ?? '' } else { '' }
    $pattern = [regex]::Escape($startMarker) + '[\s\S]*?' + [regex]::Escape($endMarker)
    $cleaned = [regex]::Replace($existing, $pattern, '').TrimEnd()
    $final = if ($cleaned) { $cleaned + "`n`n" + $blockContent } else { $blockContent }
    Set-Content -Path $claudeMdTarget -Value $final -Encoding UTF8 -NoNewline
    Write-Ok "CLAUDE.md utilisateur : bloc MEMORY-KIT injecte"

    # Permissions : additionalDirectories dans settings.json (idempotent)
    $settingsFile = Join-Path $ConfigDir 'settings.json'
    $settings = $null
    if (Test-Path $settingsFile) {
        try {
            $settings = Get-Content $settingsFile -Raw | ConvertFrom-Json -AsHashtable
        } catch {
            Write-Warn2 "settings.json illisible ($_). Permission non modifiee."
        }
    } else {
        $settings = [ordered]@{}
    }
    if ($null -ne $settings) {
        if (-not $settings.Contains('permissions')) {
            $settings['permissions'] = [ordered]@{}
        }
        if (-not $settings['permissions'].Contains('additionalDirectories')) {
            $settings['permissions']['additionalDirectories'] = @()
        }
        $dirs = @($settings['permissions']['additionalDirectories'])
        if ($dirs -notcontains $VaultPath) {
            $settings['permissions']['additionalDirectories'] = $dirs + $VaultPath
            $json = $settings | ConvertTo-Json -Depth 100
            Set-Content -Path $settingsFile -Value $json -Encoding UTF8 -NoNewline
            Write-Ok "settings.json : additionalDirectories += $VaultPath"
        } else {
            Write-Skip "settings.json : permission deja presente"
        }
    }

    return $true
}

# ============================================================
# Adapter : Gemini CLI
# ============================================================

function Deploy-GeminiCli {
    param(
        [string]$KitRoot,
        [string]$ConfigDir,
        [string]$VaultPath,
        [switch]$Force
    )

    Write-Host ''
    Write-Step "> Deploiement : Gemini CLI"

    if (-not (Test-Path $ConfigDir)) {
        Write-Warn2 "Dossier Gemini introuvable ($ConfigDir). Lance 'gemini' au moins une fois."
        return $false
    }

    # ~/.gemini/extensions/memory-kit/{commands}
    $extensionsDir = Join-Path $ConfigDir 'extensions'
    $extDir = Join-Path $extensionsDir 'memory-kit'
    $cmdDir = Join-Path $extDir 'commands'
    foreach ($d in @($extensionsDir, $extDir, $cmdDir)) {
        if (-not (Test-Path $d)) {
            New-Item -ItemType Directory -Path $d -Force | Out-Null
        }
    }

    $adapterDir = Join-Path $KitRoot 'adapters\gemini-cli'

    # Manifest + GEMINI.md (copie directe, ce sont des fichiers statiques)
    Copy-Item -Path (Join-Path $adapterDir 'gemini-extension.json') -Destination $extDir -Force
    Write-Ok "gemini-extension.json"
    Copy-Item -Path (Join-Path $adapterDir 'GEMINI.md') -Destination $extDir -Force
    Write-Ok "GEMINI.md"

    # Commands (template + procedure core + substitution CONFIG_FILE)
    $coreSource = Join-Path $KitRoot 'core\procedures'
    $configFileRef = '`~/.gemini/memory-kit.json`'
    Get-ChildItem -Path (Join-Path $adapterDir 'commands') -Filter '*.template.toml' | ForEach-Object {
        $commandName = $_.Name -replace '\.template\.toml$', ''
        $templateContent = Get-Content -Path $_.FullName -Raw
        $procedurePath = Join-Path $coreSource "$commandName.md"
        if (-not (Test-Path $procedurePath)) {
            Write-Warn2 "Procedure core manquante pour $commandName (ignore)"
            return
        }
        $procedureContent = Get-Content -Path $procedurePath -Raw
        $procedureContent = $procedureContent -replace '\{\{CONFIG_FILE\}\}', $configFileRef
        $assembled = $templateContent -replace '\{\{PROCEDURE\}\}', $procedureContent
        Set-Content -Path (Join-Path $cmdDir "$commandName.toml") -Value $assembled -Encoding UTF8 -NoNewline
        Write-Ok "Command : $commandName.toml"
    }

    # memory-kit.json au niveau utilisateur
    $configFile = Join-Path $ConfigDir 'memory-kit.json'
    $configData = [ordered]@{ vault = $VaultPath } | ConvertTo-Json
    if ((Test-Path $configFile) -and -not $Force) {
        Write-Skip "memory-kit.json preserve (utiliser -Force pour ecraser)"
    } else {
        Set-Content -Path $configFile -Value $configData -Encoding UTF8 -NoNewline
        Write-Ok "memory-kit.json -> vault = $VaultPath"
    }

    # Activer l'extension dans extension-enablement.json (idempotent)
    $enablementFile = Join-Path $extensionsDir 'extension-enablement.json'
    $enablement = $null
    if (Test-Path $enablementFile) {
        try {
            $enablement = Get-Content $enablementFile -Raw | ConvertFrom-Json -AsHashtable
        } catch {
            Write-Warn2 "extension-enablement.json illisible ($_). Activation manuelle requise."
        }
    } else {
        $enablement = [ordered]@{}
    }
    if ($null -ne $enablement) {
        if (-not $enablement.Contains('memory-kit')) {
            # Pattern large couvrant le home user, coherent avec les autres extensions existantes
            # Format Gemini : /C:/Users/xxx/* (slash initial + separateurs forward, colon preserve)
            $homePattern = '/' + ($HOME -replace '\\', '/') + '/*'
            $enablement['memory-kit'] = [ordered]@{ overrides = @($homePattern) }
            $json = $enablement | ConvertTo-Json -Depth 100
            Set-Content -Path $enablementFile -Value $json -Encoding UTF8 -NoNewline
            Write-Ok "extension-enablement.json : memory-kit active ($homePattern)"
        } else {
            Write-Skip "extension-enablement.json : memory-kit deja active"
        }
    }

    return $true
}

# ============================================================
# Adapter : Codex (OpenAI)
# ============================================================

function Deploy-Codex {
    param(
        [string]$KitRoot,
        [string]$ConfigDir,
        [string]$VaultPath,
        [switch]$Force
    )

    Write-Host ''
    Write-Step "> Deploiement : Codex (OpenAI)"

    if (-not (Test-Path $ConfigDir)) {
        Write-Warn2 "Dossier Codex introuvable ($ConfigDir). Lance 'codex' au moins une fois."
        return $false
    }

    $promptsTarget = Join-Path $ConfigDir 'prompts'
    $skillsTarget  = Join-Path $ConfigDir 'skills'
    foreach ($d in @($promptsTarget, $skillsTarget)) {
        if (-not (Test-Path $d)) {
            New-Item -ItemType Directory -Path $d -Force | Out-Null
        }
    }

    $adapterDir = Join-Path $KitRoot 'adapters\codex'
    $coreSource = Join-Path $KitRoot 'core\procedures'
    $configFileRef = '`~/.codex/memory-kit.json`'

    # Prompts (slash commands user-level, format markdown + frontmatter YAML)
    $promptsSource = Join-Path $adapterDir 'prompts'
    if (Test-Path $promptsSource) {
        Get-ChildItem -Path $promptsSource -Filter '*.template.md' | ForEach-Object {
            $name = $_.Name -replace '\.template\.md$', ''
            $tpl = Get-Content -Path $_.FullName -Raw
            $procPath = Join-Path $coreSource "$name.md"
            if (-not (Test-Path $procPath)) {
                Write-Warn2 "Procedure core manquante pour prompt $name (ignore)"
                return
            }
            $proc = Get-Content -Path $procPath -Raw
            $proc = $proc -replace '\{\{CONFIG_FILE\}\}', $configFileRef
            $assembled = $tpl -replace '\{\{PROCEDURE\}\}', $proc
            Set-Content -Path (Join-Path $promptsTarget "$name.md") -Value $assembled -Encoding UTF8 -NoNewline
            Write-Ok "Prompt  : $name.md"
        }
    }

    # Skills (format Anthropic : skills/{nom}/SKILL.md)
    $skillsSource = Join-Path $adapterDir 'skills'
    if (Test-Path $skillsSource) {
        Get-ChildItem -Path $skillsSource -Directory | ForEach-Object {
            $name = $_.Name
            $tplFile = Join-Path $_.FullName 'SKILL.md.template'
            if (-not (Test-Path $tplFile)) {
                Write-Warn2 "SKILL.md.template manquant pour $name (ignore)"
                return
            }
            $tpl = Get-Content -Path $tplFile -Raw
            $procPath = Join-Path $coreSource "$name.md"
            if (-not (Test-Path $procPath)) {
                Write-Warn2 "Procedure core manquante pour skill $name (ignore)"
                return
            }
            $proc = Get-Content -Path $procPath -Raw
            $proc = $proc -replace '\{\{CONFIG_FILE\}\}', $configFileRef
            $assembled = $tpl -replace '\{\{PROCEDURE\}\}', $proc
            $destDir = Join-Path $skillsTarget $name
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Set-Content -Path (Join-Path $destDir 'SKILL.md') -Value $assembled -Encoding UTF8 -NoNewline
            Write-Ok "Skill   : $name/SKILL.md"
        }
    }

    # memory-kit.json au niveau utilisateur
    $configFile = Join-Path $ConfigDir 'memory-kit.json'
    $configData = [ordered]@{ vault = $VaultPath } | ConvertTo-Json
    if ((Test-Path $configFile) -and -not $Force) {
        Write-Skip "memory-kit.json preserve (utiliser -Force pour ecraser)"
    } else {
        Set-Content -Path $configFile -Value $configData -Encoding UTF8 -NoNewline
        Write-Ok "memory-kit.json -> vault = $VaultPath"
    }

    return $true
}

# ============================================================
# Adapter : Mistral Vibe
# ============================================================

function Deploy-MistralVibe {
    param(
        [string]$KitRoot,
        [string]$ConfigDir,
        [string]$VaultPath,
        [switch]$Force   # non utilise, garde pour signature uniforme
    )

    Write-Host ''
    Write-Step "> Deploiement : Mistral Vibe"

    if (-not (Test-Path $ConfigDir)) {
        Write-Warn2 "Dossier Vibe introuvable ($ConfigDir). Lance 'vibe' au moins une fois."
        return $false
    }

    $adapterDir = Join-Path $KitRoot 'adapters\mistral-vibe'
    $blockPath = Join-Path $adapterDir 'instructions-block.md'
    if (-not (Test-Path $blockPath)) {
        Write-Warn2 "instructions-block.md manquant : $blockPath"
        return $false
    }

    # Charger le bloc, substituer VAULT_PATH (chemin absolu direct, Vibe n'a pas
    # de mecanisme clair de config runtime)
    $blockContent = Get-Content -Path $blockPath -Raw
    $blockContent = $blockContent -replace '\{\{VAULT_PATH\}\}', ($VaultPath -replace '\\', '/')

    # Merger dans ~/.vibe/instructions.md avec markers idempotents
    $instructionsFile = Join-Path $ConfigDir 'instructions.md'
    $existing = if (Test-Path $instructionsFile) {
        (Get-Content -Path $instructionsFile -Raw) ?? ''
    } else {
        ''
    }
    $startMarker = '<!-- MEMORY-KIT:START -->'
    $endMarker   = '<!-- MEMORY-KIT:END -->'
    $pattern = [regex]::Escape($startMarker) + '[\s\S]*?' + [regex]::Escape($endMarker)
    $cleaned = [regex]::Replace($existing, $pattern, '').TrimEnd()
    $final = if ($cleaned) { $cleaned + "`n`n" + $blockContent } else { $blockContent }
    Set-Content -Path $instructionsFile -Value $final -Encoding UTF8 -NoNewline
    Write-Ok "instructions.md : bloc MEMORY-KIT injecte"

    return $true
}

# ============================================================
# 1. Resolution des chemins
# ============================================================

$kitRoot = $PSScriptRoot
Write-Step "Racine du kit : $kitRoot"

if (-not $VaultPath) {
    $VaultPath = Join-Path $kitRoot 'memory'
}
$VaultPath = [System.IO.Path]::GetFullPath($VaultPath)

if (-not (Test-Path $VaultPath)) {
    Write-Error "Vault introuvable : $VaultPath`n`nCree le dossier ou passe -VaultPath <chemin>."
    exit 1
}

Write-Step "Vault memoire : $VaultPath"

# ============================================================
# 2. Detection des CLI IA
# ============================================================

Write-Host ''
Write-Step 'Detection des CLI IA...'
Write-Host ''

$platforms = @(
    [ordered]@{
        Name        = 'claude-code'
        DisplayName = 'Claude Code'
        Binary      = 'claude'
        ConfigDir   = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME '.claude' }
        DeployFunc  = 'Deploy-ClaudeCode'
    },
    [ordered]@{
        Name        = 'gemini-cli'
        DisplayName = 'Gemini CLI'
        Binary      = 'gemini'
        ConfigDir   = Join-Path $HOME '.gemini'
        DeployFunc  = 'Deploy-GeminiCli'
    },
    [ordered]@{
        Name        = 'codex'
        DisplayName = 'Codex (OpenAI)'
        Binary      = 'codex'
        ConfigDir   = Join-Path $HOME '.codex'
        DeployFunc  = 'Deploy-Codex'
    },
    [ordered]@{
        Name        = 'mistral-vibe'
        DisplayName = 'Mistral Vibe'
        Binary      = 'vibe'
        ConfigDir   = Join-Path $HOME '.vibe'
        DeployFunc  = 'Deploy-MistralVibe'
    }
)

$detected = @()
foreach ($p in $platforms) {
    if (Test-CliInstalled -Binary $p.Binary -ConfigDir $p.ConfigDir) {
        Write-Ok "$($p.DisplayName)"
        $detected += $p
    } else {
        Write-Skip "$($p.DisplayName)"
    }
}

# ============================================================
# 3. Cas : aucune CLI detectee (message amical)
# ============================================================

if ($detected.Count -eq 0) {
    Write-Host ''
    Write-Host 'Aucune CLI IA detectee sur ce poste.' -ForegroundColor Yellow
    Write-Host ''
    Write-Host 'Sans CLI IA, un second cerveau pour IA va etre... plutot theorique (haha).' -ForegroundColor Gray
    Write-Host ''
    Write-Host 'Installe au moins une des CLI suivantes, puis relance ce script :' -ForegroundColor White
    Write-Info 'Claude Code  : https://claude.com/claude-code'
    Write-Info 'Gemini CLI   : https://github.com/google-gemini/gemini-cli'
    Write-Info 'Codex        : https://github.com/openai/codex'
    Write-Info 'Mistral Vibe : (voir documentation Mistral AI)'
    Write-Host ''
    exit 0
}

# ============================================================
# 4. Deploiement par plateforme detectee
# ============================================================

$deployed = @()
$pending  = @()

foreach ($p in $detected) {
    $adapterDir = Join-Path $kitRoot "adapters\$($p.Name)"
    if (-not (Test-Path $adapterDir)) {
        Write-Host ''
        Write-Warn2 "$($p.DisplayName) : dossier adapter manquant ($adapterDir)"
        $pending += $p.DisplayName
        continue
    }

    try {
        $ok = & $p.DeployFunc `
            -KitRoot $kitRoot `
            -ConfigDir $p.ConfigDir `
            -VaultPath $VaultPath `
            -Force:$Force
        if ($ok) {
            $deployed += $p.DisplayName
        } else {
            $pending += $p.DisplayName
        }
    } catch {
        Write-Warn2 "$($p.DisplayName) : erreur de deploiement ($_)"
        $pending += $p.DisplayName
    }
}

# ============================================================
# 5. Resume final
# ============================================================

Write-Host ''
Write-Host '=== Deploiement termine ===' -ForegroundColor Magenta
Write-Host "Vault : $VaultPath"
if ($deployed.Count -gt 0) {
    Write-Host ("Deploye    : {0}" -f ($deployed -join ', ')) -ForegroundColor Green
}
if ($pending.Count -gt 0) {
    Write-Host ("En attente : {0} (adapter a implementer)" -f ($pending -join ', ')) -ForegroundColor Yellow
}
Write-Host ''
if ($deployed -contains 'Claude Code') {
    Write-Host 'Teste avec : /recall (dans une nouvelle session Claude Code)' -ForegroundColor Cyan
}
