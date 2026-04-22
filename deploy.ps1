#Requires -Version 7.0

<#
.SYNOPSIS
    Deploie ou met a jour le kit memoire dans chaque CLI IA detectee sur le poste.

.DESCRIPTION
    Detecte les CLI IA installees (Claude Code, Gemini CLI, Codex, Mistral Vibe)
    et deploie l'adapter correspondant pour chacune. Ne plante pas si une CLI
    est absente : elle est simplement skippee.

    Premiere installation : le vault est cree a {racine du kit}/memory sauf si
    -VaultPath est fourni.

    Mise a jour : si une installation precedente est detectee (via les
    memory-kit.json presents dans les dossiers de config des CLI), son vault
    est reutilise automatiquement. Le script peut donc etre relance depuis
    n'importe quel repertoire de travail sans avoir a reprecise le chemin.

    Utiliser -VaultPath pour forcer un autre vault (migration).

.PARAMETER VaultPath
    Chemin absolu du vault memoire. Si omis : auto-detection depuis l'install
    existante, puis fallback sur {racine du kit}/memory.

.PARAMETER Force
    Ecrase memory-kit.json meme s'il existe deja.

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
# Detection d'une installation SecondBrain existante
# ============================================================

function Get-ExistingVaultPath {
    <#
    Parcourt les emplacements ou un memory-kit.json a pu etre ecrit par une
    installation precedente. Retourne une liste d'objets { Source, ConfigFile,
    Vault } pour chaque fichier trouve et parsable.

    Mistral Vibe n'a pas de memory-kit.json (son vault est injecte en clair
    dans instructions.md), il n'est pas scanne ici.
    #>
    $sources = @(
        @{
            Source     = 'Claude Code'
            ConfigFile = if ($env:CLAUDE_CONFIG_DIR) {
                Join-Path $env:CLAUDE_CONFIG_DIR 'memory-kit.json'
            } else {
                Join-Path $HOME '.claude\memory-kit.json'
            }
        },
        @{
            Source     = 'Gemini CLI'
            ConfigFile = Join-Path $HOME '.gemini\memory-kit.json'
        },
        @{
            Source     = 'Codex'
            ConfigFile = Join-Path $HOME '.codex\memory-kit.json'
        }
    )

    $found = @()
    foreach ($s in $sources) {
        if (-not (Test-Path $s.ConfigFile)) { continue }
        try {
            $config = Get-Content -Path $s.ConfigFile -Raw | ConvertFrom-Json
            if ($config.vault) {
                $found += [PSCustomObject]@{
                    Source     = $s.Source
                    ConfigFile = $s.ConfigFile
                    Vault      = $config.vault
                }
            }
        } catch {
            Write-Warn2 "$($s.ConfigFile) illisible ($_). Ignore."
        }
    }
    return $found
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
        $settingsChanged = $false

        if (-not $settings.Contains('permissions')) {
            $settings['permissions'] = [ordered]@{}
        }

        # additionalDirectories : ajout du vault (idempotent)
        if (-not $settings['permissions'].Contains('additionalDirectories')) {
            $settings['permissions']['additionalDirectories'] = @()
        }
        $dirs = @($settings['permissions']['additionalDirectories'])
        if ($dirs -notcontains $VaultPath) {
            $settings['permissions']['additionalDirectories'] = $dirs + $VaultPath
            $settingsChanged = $true
            Write-Ok "settings.json : additionalDirectories += $VaultPath"
        } else {
            Write-Skip "settings.json : additionalDirectories deja present"
        }

        # allow : patterns pour les operations vault des skills mem-*
        # Les procedures mem-rename-project, mem-merge-projects et mem-rollback-archive
        # appellent Rename-Item / Remove-Item / Move-Item via pwsh. On autorise les deux
        # chemins d'invocation : outil PowerShell direct, et Bash + pwsh -Command.
        if (-not $settings['permissions'].Contains('allow')) {
            $settings['permissions']['allow'] = @()
        }
        $memPatterns = @(
            'PowerShell(Rename-Item:*)',
            'PowerShell(Remove-Item:*)',
            'PowerShell(Move-Item:*)',
            'Bash(pwsh -Command Rename-Item:*)',
            'Bash(pwsh -Command Remove-Item:*)',
            'Bash(pwsh -Command Move-Item:*)'
        )
        $allow = @($settings['permissions']['allow'])
        $added = @()
        foreach ($pat in $memPatterns) {
            if ($allow -notcontains $pat) {
                $allow += $pat
                $added += $pat
            }
        }
        if ($added.Count -gt 0) {
            $settings['permissions']['allow'] = $allow
            $settingsChanged = $true
            Write-Ok "settings.json : allow += $($added.Count) pattern(s) mem-* (Rename/Remove/Move-Item)"
        } else {
            Write-Skip "settings.json : patterns allow mem-* deja presents"
        }

        if ($settingsChanged) {
            $json = $settings | ConvertTo-Json -Depth 100
            Set-Content -Path $settingsFile -Value $json -Encoding UTF8 -NoNewline
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
        [switch]$Force
    )

    Write-Host ''
    Write-Step "> Deploiement : Mistral Vibe"

    if (-not (Test-Path $ConfigDir)) {
        Write-Warn2 "Dossier Vibe introuvable ($ConfigDir). Lance 'vibe' au moins une fois."
        return $false
    }

    $adapterDir = Join-Path $KitRoot 'adapters\mistral-vibe'
    $startMarker = '<!-- MEMORY-KIT:START -->'
    $endMarker   = '<!-- MEMORY-KIT:END -->'
    $pattern = [regex]::Escape($startMarker) + '[\s\S]*?' + [regex]::Escape($endMarker)

    # --- Migration : cleanup de l'ancien bloc dans instructions.md ---
    # L'adapter visait initialement ~/.vibe/instructions.md en assumant que Vibe
    # le chargerait comme un system prompt, ce qui etait faux. On retire le
    # bloc pour que l'utilisateur ne se retrouve pas avec deux copies.
    $legacyFile = Join-Path $ConfigDir 'instructions.md'
    if (Test-Path $legacyFile) {
        $legacyContent = (Get-Content -Path $legacyFile -Raw) ?? ''
        if ($legacyContent -match [regex]::Escape($startMarker)) {
            $cleaned = [regex]::Replace($legacyContent, $pattern, '').TrimEnd()
            if ([string]::IsNullOrWhiteSpace($cleaned)) {
                Remove-Item -Path $legacyFile -Force
                Write-Info "instructions.md : fichier legacy supprime (ne contenait que le bloc MEMORY-KIT)"
            } else {
                Set-Content -Path $legacyFile -Value $cleaned -Encoding UTF8 -NoNewline
                Write-Info "instructions.md : bloc MEMORY-KIT retire (reste du contenu preserve)"
            }
        }
    }

    # --- Injection du bloc dans ~/.vibe/AGENTS.md (vrai fichier charge par Vibe) ---
    # Source : vibe/core/system_prompt.py charge ~/.vibe/AGENTS.md comme
    # user-level instructions a chaque session.
    $blockPath = Join-Path $adapterDir 'instructions-block.md'
    if (-not (Test-Path $blockPath)) {
        Write-Warn2 "instructions-block.md manquant : $blockPath"
        return $false
    }
    $blockContent = Get-Content -Path $blockPath -Raw
    $blockContent = $blockContent -replace '\{\{VAULT_PATH\}\}', ($VaultPath -replace '\\', '/')

    $agentsFile = Join-Path $ConfigDir 'AGENTS.md'
    $existing = if (Test-Path $agentsFile) { (Get-Content -Path $agentsFile -Raw) ?? '' } else { '' }
    $cleaned = [regex]::Replace($existing, $pattern, '').TrimEnd()
    $final = if ($cleaned) { $cleaned + "`n`n" + $blockContent } else { $blockContent }
    Set-Content -Path $agentsFile -Value $final -Encoding UTF8 -NoNewline
    Write-Ok "AGENTS.md : bloc MEMORY-KIT injecte"

    # --- Skills (format ~/.vibe/skills/{nom}/SKILL.md) ---
    $skillsTarget = Join-Path $ConfigDir 'skills'
    if (-not (Test-Path $skillsTarget)) {
        New-Item -ItemType Directory -Path $skillsTarget -Force | Out-Null
    }
    $skillsSource = Join-Path $adapterDir 'skills'
    $coreSource   = Join-Path $KitRoot 'core\procedures'
    $configFileRef = '`~/.vibe/AGENTS.md` (bloc MEMORY-KIT)'
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

    return $true
}

# ============================================================
# 1. Resolution des chemins
# ============================================================

$kitRoot = $PSScriptRoot
Write-Step "Racine du kit : $kitRoot"

# Resolution du VaultPath avec priorites :
#   1. -VaultPath explicite             (override utilisateur)
#   2. Installation precedente detectee (mise a jour)
#   3. Fallback : {kitRoot}/memory      (premiere install en local)

if ($VaultPath) {
    Write-Info "Vault force via -VaultPath : $VaultPath"
} else {
    $existing = Get-ExistingVaultPath
    if ($existing.Count -eq 0) {
        $VaultPath = Join-Path $kitRoot 'memory'
        Write-Info "Aucune installation existante detectee. Premiere install : $VaultPath"
    } else {
        $distinctVaults = @($existing.Vault | Select-Object -Unique)
        if ($distinctVaults.Count -eq 1) {
            $VaultPath = $distinctVaults[0]
            $sources = ($existing.Source -join ', ')
            Write-Info "Installation existante detectee ($sources) : reprise du vault $VaultPath"
        } else {
            Write-Host ''
            Write-Host 'Des vaults differents sont enregistres dans les CLIs :' -ForegroundColor Yellow
            foreach ($e in $existing) {
                Write-Host ("  - {0,-12} : {1}" -f $e.Source, $e.Vault)
            }
            Write-Host ''
            Write-Error "Impossible de choisir automatiquement. Relance avec -VaultPath <chemin>."
            exit 1
        }
    }
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
if ($deployed.Count -gt 0) {
    Write-Host 'Test :' -ForegroundColor Cyan
    foreach ($cli in $deployed) {
        switch ($cli) {
            'Claude Code'    { Write-Host "  [Claude Code]  /mem-recall (dans une nouvelle session)" -ForegroundColor Cyan }
            'Gemini CLI'     { Write-Host "  [Gemini CLI]   /mem-recall (dans une nouvelle session)" -ForegroundColor Cyan }
            'Codex (OpenAI)' { Write-Host "  [Codex]        /mem-recall (dans une nouvelle session)" -ForegroundColor Cyan }
            'Mistral Vibe'   { Write-Host "  [Mistral Vibe] dis 'charge mon contexte memoire' (Vibe n'expose pas de slash commands)" -ForegroundColor Cyan }
        }
    }
}
