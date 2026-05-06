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

.PARAMETER Language
    Langue conversationnelle du LLM (en, fr, es, de, ru). Si omise : detection
    systeme puis prompt interactif.

.PARAMETER Force
    Ecrase memory-kit.json meme s'il existe deja.

.PARAMETER SkipObsidianStyle
    Ne deploie pas les configs canoniques Obsidian (graph palette).

.PARAMETER ForceObsidianStyle
    Force le deploy Obsidian style meme si Obsidian semble ouvert.

.PARAMETER SkipMcpServer
    Ne deploie pas le serveur MCP Python (CLI restent en mode skills fallback).

.PARAMETER RepairMcp
    Desinstalle proprement le package pipx memory-kit-mcp avant de reinstaller.
    Utile quand l'install pipx est dans un etat incoherent (shim recent + venv
    ancien, ModuleNotFoundError sur un module recent, etc.). Kill aussi les
    process memory-kit-mcp actifs pour eviter les locks Windows lors de
    l'uninstall. Tolere l'absence du package (uninstall silencieux).

.PARAMETER AutoUpdate
    Avant de deployer, verifie le repo git distant (origin/main) et fait un
    git pull --ff-only si origin est en avance sur HEAD. Refuse silencieusement
    si : (a) pas dans un git repo, (b) branche != main, (c) working tree dirty.
    Si un pull a effectivement eu lieu, le script se relance depuis la source
    a jour pour deployer la nouvelle version. Combinable avec -RepairMcp.

.PARAMETER Help
    Affiche cette aide et quitte. Alias : -h, -?, --help, --?.

.EXAMPLE
    .\deploy.ps1
    .\deploy.ps1 -VaultPath "D:\mes-notes\cerveau"
    .\deploy.ps1 -Language fr
    .\deploy.ps1 -Force
    .\deploy.ps1 -RepairMcp
    .\deploy.ps1 -AutoUpdate
    .\deploy.ps1 -AutoUpdate -RepairMcp
    .\deploy.ps1 -h
#>

[CmdletBinding()]
param(
    [string]$VaultPath,
    [ValidateSet('en','fr','es','de','ru','')]
    [string]$Language = '',
    [switch]$Force,
    [switch]$SkipObsidianStyle,
    [switch]$ForceObsidianStyle,
    [switch]$SkipMcpServer,
    [switch]$RepairMcp,
    [switch]$AutoUpdate,
    [Alias('h')]
    [switch]$Help
)

# Aide via -?, -h, -Help, --help. Note : -? est intercepte par PowerShell
# avant que le script demarre (Get-Help auto). PowerShell 7+ traduit aussi
# --param en -param, donc --help => -Help via l'alias ci-dessus.
if ($Help) {
    Get-Help $PSCommandPath -Full
    exit 0
}

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
# Ecriture / mise a jour de memory-kit.json
# ============================================================
# Le fichier porte le chemin du vault et la valeur par defaut du scope (perso|pro).
# Comportement :
#   - Fichier absent => creation avec vault + default_scope (defaut: pro)
#   - Fichier present + -Force => recreation complete
#   - Fichier present sans -Force => preservation, mais patch silencieux si
#     default_scope est absent (cas migration v0.4 -> v0.5).

function Write-MemoryKitJson {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Vault,
        [Parameter(Mandatory=$true)][string]$KitRepo,
        [string]$DefaultScope = 'work',
        [string]$Language = 'en',
        [switch]$Force
    )
    $exists = Test-Path $Path
    if ($exists -and -not $Force) {
        # Patch silencieux : ajoute les champs manquants (default_scope, language, kit_repo) sans toucher au reste.
        try {
            $existing = Get-Content -Path $Path -Raw | ConvertFrom-Json -AsHashtable
        } catch {
            Write-Warn2 "memory-kit.json existant illisible ($Path) : $_"
            return
        }
        $patched = $false
        if (-not $existing.ContainsKey('default_scope')) {
            $existing['default_scope'] = $DefaultScope
            $patched = $true
        }
        if (-not $existing.ContainsKey('language')) {
            $existing['language'] = $Language
            $patched = $true
        }
        if (-not $existing.ContainsKey('kit_repo')) {
            $existing['kit_repo'] = $KitRepo
            $patched = $true
        }
        if ($patched) {
            $merged = [ordered]@{
                vault         = $existing['vault']
                default_scope = $existing['default_scope']
                language      = $existing['language']
                kit_repo      = $existing['kit_repo']
            } | ConvertTo-Json
            Set-Content -Path $Path -Value $merged -Encoding utf8NoBOM -NoNewline
            Write-Ok "memory-kit.json patche : default_scope=$($existing['default_scope']), language=$($existing['language']), kit_repo=$($existing['kit_repo'])"
        } else {
            Write-Skip "memory-kit.json preserve (utiliser -Force pour ecraser)"
        }
        return
    }
    # Creation ou ecrasement complet.
    $configData = [ordered]@{
        vault         = $Vault
        default_scope = $DefaultScope
        language      = $Language
        kit_repo      = $KitRepo
    } | ConvertTo-Json
    Set-Content -Path $Path -Value $configData -Encoding utf8NoBOM -NoNewline
    Write-Ok "memory-kit.json -> vault = $Vault, default_scope = $DefaultScope, language = $Language, kit_repo = $KitRepo"
}

# ============================================================
# Resolution de la langue conversationnelle
# ============================================================
# Priorite :
#   1. -Language explicite (validee dans param block)
#   2. Detection depuis $PSCulture (ex: "fr-FR" -> "fr")
#   3. Prompt interactif si shell interactif et premiere install
#   4. Fallback : "en"

function Resolve-Language {
    param([string]$Explicit)

    $supported = @('en','fr','es','de','ru')

    if ($Explicit) {
        return $Explicit
    }

    # Auto-detection depuis culture systeme
    $cultureCode = ($PSCulture -split '-')[0].ToLowerInvariant()
    $detected = if ($supported -contains $cultureCode) { $cultureCode } else { 'en' }

    # Si shell interactif (Host.UI present + pas redirige), proposer choix
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        Write-Host ''
        Write-Step "Conversational language for the LLM (the vault structure stays English)"
        Write-Host "  Supported: $($supported -join ', ')" -ForegroundColor DarkGray
        $prompt = Read-Host "  Choose language [$detected]"
        if ($prompt) {
            $prompt = $prompt.Trim().ToLowerInvariant()
            if ($supported -contains $prompt) {
                return $prompt
            } else {
                Write-Warn2 "Unknown language '$prompt', falling back to '$detected'"
            }
        }
    }
    return $detected
}

# ============================================================
# Bridge Deploy-ObsidianStyle (v0.7.2)
# ============================================================
# Copie les configs canoniques de adapters/obsidian-style/ vers
# {vault}/.obsidian/ avec backup horodate avant ecrasement. Refuse si
# Obsidian est ouvert (sauf -ForceObsidianStyle). Idempotent : skip si
# contenu identique. Respecte le marker "_secondbrain_canonical" pour
# distinguer fichier kit vs personnalisation utilisateur.

function Test-ObsidianRunning {
    param([Parameter(Mandatory=$true)][string]$VaultPath)
    # Detection 1 : processus Obsidian
    $procs = Get-Process -Name 'Obsidian' -ErrorAction SilentlyContinue
    if ($procs) { return $true }
    # Detection 2 : workspace.json modifie dans les 60 dernieres secondes
    $workspaceFile = Join-Path $VaultPath '.obsidian\workspace.json'
    if (Test-Path $workspaceFile) {
        $mtime = (Get-Item $workspaceFile).LastWriteTime
        if ((Get-Date) - $mtime -lt [TimeSpan]::FromSeconds(60)) {
            return $true
        }
    }
    return $false
}

function Test-CanonicalMarker {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    try {
        $content = Get-Content -Path $Path -Raw -Encoding utf8
        return ($content -match '"_secondbrain_canonical"\s*:')
    } catch {
        return $false
    }
}

function Deploy-ObsidianStyle {
    param(
        [Parameter(Mandatory=$true)][string]$KitRoot,
        [Parameter(Mandatory=$true)][string]$VaultPath,
        [switch]$Force
    )
    $sourceDir = Join-Path $KitRoot 'adapters\obsidian-style'
    if (-not (Test-Path $sourceDir)) {
        Write-Skip "Adapter obsidian-style absent du kit (skip silencieux)"
        return
    }

    Write-Step "> Deploiement : Obsidian style (graph palette + assets canoniques)"

    $obsidianDir = Join-Path $VaultPath '.obsidian'
    if (-not (Test-Path $obsidianDir)) {
        Write-Skip "$obsidianDir absent — Obsidian n'a pas encore ouvert ce vault. Skip."
        return
    }

    if ((Test-ObsidianRunning -VaultPath $VaultPath) -and -not $Force) {
        Write-Warn2 "Obsidian semble ouvert ou actif sur $VaultPath. Skip pour eviter une corruption."
        Write-Info "Fermer Obsidian puis relancer, ou passer -ForceObsidianStyle pour bypass."
        return
    }

    $stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
    # v0.7.3 : recurse dans les sous-dossiers (ex: plugins/obsidian-front-matter-title-plugin/data.json)
    # pour pouvoir patcher les configs des plugins community sans casser la convention "miroir".
    Get-ChildItem -Path $sourceDir -Filter '*.json' -Recurse -File | ForEach-Object {
        $srcContent = Get-Content -Path $_.FullName -Raw -Encoding utf8
        $relPath = [System.IO.Path]::GetRelativePath($sourceDir, $_.FullName)
        $targetPath = Join-Path $obsidianDir $relPath
        $targetParent = Split-Path -Parent $targetPath

        if (-not (Test-Path $targetParent)) {
            New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
        }

        $relDisplay = $relPath -replace '\\', '/'

        if (-not (Test-Path $targetPath)) {
            Set-Content -Path $targetPath -Value $srcContent -Encoding utf8NoBOM -NoNewline
            Write-Ok "Ecrit (nouveau) : .obsidian/$relDisplay"
            return
        }

        $targetContent = Get-Content -Path $targetPath -Raw -Encoding utf8
        if ($srcContent -eq $targetContent) {
            Write-Skip ".obsidian/$relDisplay — identique a la version canonique"
            return
        }

        # Cible existe et differe : backup si elle porte le marker canonique,
        # sinon on respecte la personnalisation utilisateur (skip).
        if (Test-CanonicalMarker -Path $targetPath) {
            $backupPath = "$targetPath.bak-pre-style-$stamp"
            Copy-Item -Path $targetPath -Destination $backupPath
            Set-Content -Path $targetPath -Value $srcContent -Encoding utf8NoBOM -NoNewline
            Write-Ok "Mis a jour : .obsidian/$relDisplay (backup -> $($_.Name).bak-pre-style-$stamp)"
        } else {
            Write-Skip ".obsidian/$relDisplay — personnalise par l'utilisateur (pas de marker canonique). Pas touche."
            Write-Info "  Pour reapppliquer la version canonique, supprimer manuellement la cible et relancer."
        }
    }
}

# ============================================================
# Resolution des directives {{INCLUDE _bloc}}
# ============================================================
# Une procedure core peut inclure des blocs reutilisables (encoding, concurrence,
# router, frontmatter-universel...) via {{INCLUDE _nom}}. Resolution recursive
# avec profondeur max 5 pour eviter les cycles.

function Resolve-IncludeDirectives {
    param(
        [Parameter(Mandatory=$true)][string]$Content,
        [Parameter(Mandatory=$true)][string]$BlocsRoot,
        [int]$Depth = 0
    )
    if ($Depth -gt 5) {
        throw "Profondeur maximale d'inclusion depassee (5). Cycle d'inclusion suspecte."
    }

    $pattern = '\{\{INCLUDE\s+(_\w+)\}\}'
    $allMatches = [regex]::Matches($Content, $pattern)

    if ($allMatches.Count -eq 0) {
        return $Content
    }

    # Traiter du dernier au premier pour preserver les indices apres remplacement.
    $result = $Content
    $sortedMatches = @($allMatches) | Sort-Object -Property Index -Descending
    foreach ($match in $sortedMatches) {
        $blocName = $match.Groups[1].Value
        $blocPath = Join-Path $BlocsRoot "$blocName.md"
        if (-not (Test-Path $blocPath)) {
            throw "Bloc d'inclusion introuvable : {{INCLUDE $blocName}} -> $blocPath manquant."
        }
        $blocContent = Get-Content -Path $blocPath -Raw
        # Resolution recursive (un bloc peut en inclure d'autres).
        $blocContent = Resolve-IncludeDirectives -Content $blocContent -BlocsRoot $BlocsRoot -Depth ($Depth + 1)
        # Remplacement litteral (pas regex) : evite les soucis d'echappement
        # avec les caracteres speciaux du contenu inclus.
        $result = $result.Substring(0, $match.Index) + $blocContent + $result.Substring($match.Index + $match.Length)
    }

    return $result
}

# ============================================================
# Composition MCP-first : prepend du bloc _mcp-first.md (v0.8.0)
# ============================================================
# Pattern : chaque procedure resolue par deploy.ps1 gagne automatiquement
# un bloc d'introduction qui dit au LLM "si l'outil mcp__memory-kit__mem_X
# est disponible, l'invoquer ; sinon executer la procedure ci-dessous".
# Le {{TOOL_NAME}} dans le bloc est substitue par le nom MCP correspondant
# au skill (ex: mem-recall -> mem_recall).

function Get-McpToolName {
    param([Parameter(Mandatory=$true)][string]$SkillName)
    # Convention : kebab-case dans les skills (mem-recall) ↔ snake_case dans
    # les outils MCP (mem_recall). Cf. doc d'archi v0.8.0 §5.
    return $SkillName -replace '-', '_'
}

function Add-McpFirstBlock {
    param(
        [Parameter(Mandatory=$true)][string]$ProcedureContent,
        [Parameter(Mandatory=$true)][string]$SkillName,
        [Parameter(Mandatory=$true)][string]$BlocsRoot
    )
    $blockPath = Join-Path $BlocsRoot '_mcp-first.md'
    if (-not (Test-Path $blockPath)) {
        # Si le bloc n'existe pas (cas core/ sans v0.8.0), retourner inchange.
        return $ProcedureContent
    }
    $block = Get-Content -Path $blockPath -Raw
    # Resolution des sous-includes du bloc (au cas ou).
    $block = Resolve-IncludeDirectives -Content $block -BlocsRoot $BlocsRoot
    # Substitution du nom de l'outil MCP correspondant.
    $toolName = Get-McpToolName -SkillName $SkillName
    $block = $block -replace '\{\{TOOL_NAME\}\}', $toolName
    # Prepend : le bloc s'inserre au-dessus de la procedure complete.
    return $block + $ProcedureContent
}

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
        },
        @{
            Source     = 'Copilot CLI'
            ConfigFile = if ($env:COPILOT_HOME) {
                Join-Path $env:COPILOT_HOME 'memory-kit.json'
            } else {
                Join-Path $HOME '.copilot\memory-kit.json'
            }
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
# Cleanup migration v0.4 -> v0.5
# ============================================================
# Supprime les skills/commandes/templates obsoletes apres renommages :
#   recall             -> mem-recall            (pre-v0.4)
#   archive            -> mem-archive           (pre-v0.4)
#   mem-list-projects  -> mem-list              (v0.5)
#   mem-rename-project -> mem-rename            (v0.5)
#   mem-merge-projects -> mem-merge             (v0.5)
# Idempotent : si les fichiers ont deja ete supprimes, ne fait rien.

function Remove-DeprecatedV04Files {
    param([Parameter(Mandatory=$true)][hashtable]$ConfigDirs)
    $obsolete = @('recall', 'archive', 'mem-list-projects', 'mem-rename-project', 'mem-merge-projects')
    $patterns = @{
        Claude = @('skills\{name}.md', 'commands\{name}.md')
        Gemini = @('extensions\memory-kit\commands\{name}.toml')
        Codex  = @('prompts\{name}.md', 'skills\{name}')
        Vibe   = @('skills\{name}')
    }
    $count = 0
    foreach ($cli in $patterns.Keys) {
        $base = $ConfigDirs[$cli]
        if (-not $base -or -not (Test-Path $base)) { continue }
        foreach ($pattern in $patterns[$cli]) {
            foreach ($name in $obsolete) {
                $relPath = $pattern -replace '\{name\}', $name
                $full = Join-Path $base $relPath
                if (Test-Path $full) {
                    Remove-Item -Path $full -Recurse -Force
                    Write-Ok "Cleanup v0.4 : $cli/$relPath supprime"
                    $count++
                }
            }
        }
    }
    if ($count -eq 0) {
        Write-Skip "Cleanup v0.4 : rien a supprimer (deja a jour)"
    }
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
        $procedureContent = Resolve-IncludeDirectives -Content $procedureContent -BlocsRoot $coreSource
        $procedureContent = $procedureContent -replace '\{\{CONFIG_FILE\}\}', $configFileRef
        $procedureContent = Add-McpFirstBlock -ProcedureContent $procedureContent -SkillName $skillName -BlocsRoot $coreSource
        # .Replace() = literal string replace (pas regex). PowerShell -replace
        # interprete les sequences $1, $2, $&, $' du contenu de remplacement
        # comme des references regex — or les procedures contiennent du shell
        # avec '$' (ex: regex grep '...yml)$' qui declenche le bug ou $' est
        # remplace par "texte apres le match" → doublon en milieu de fichier).
        $assembled = $templateContent.Replace('{{PROCEDURE}}', $procedureContent)
        Set-Content -Path (Join-Path $skillsTarget "$skillName.md") -Value $assembled -Encoding utf8NoBOM -NoNewline
        Write-Ok "Skill   : $skillName.md"
    }

    # memory-kit.json
    Write-MemoryKitJson -Path (Join-Path $ConfigDir 'memory-kit.json') -Vault $VaultPath -KitRepo $KitRoot -Language $script:Language -Force:$Force

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
    Set-Content -Path $claudeMdTarget -Value $final -Encoding utf8NoBOM -NoNewline
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
            Set-Content -Path $settingsFile -Value $json -Encoding utf8NoBOM -NoNewline
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
        $procedureContent = Resolve-IncludeDirectives -Content $procedureContent -BlocsRoot $coreSource
        $procedureContent = $procedureContent -replace '\{\{CONFIG_FILE\}\}', $configFileRef
        $procedureContent = Add-McpFirstBlock -ProcedureContent $procedureContent -SkillName $commandName -BlocsRoot $coreSource
        # .Replace() = literal string replace (pas regex). PowerShell -replace
        # interprete les sequences $1, $2, $&, $' du contenu de remplacement
        # comme des references regex — or les procedures contiennent du shell
        # avec '$' (ex: regex grep '...yml)$' qui declenche le bug ou $' est
        # remplace par "texte apres le match" → doublon en milieu de fichier).
        $assembled = $templateContent.Replace('{{PROCEDURE}}', $procedureContent)
        Set-Content -Path (Join-Path $cmdDir "$commandName.toml") -Value $assembled -Encoding utf8NoBOM -NoNewline
        Write-Ok "Command : $commandName.toml"
    }

    # memory-kit.json au niveau utilisateur
    Write-MemoryKitJson -Path (Join-Path $ConfigDir 'memory-kit.json') -Vault $VaultPath -KitRepo $KitRoot -Language $script:Language -Force:$Force

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
            Set-Content -Path $enablementFile -Value $json -Encoding utf8NoBOM -NoNewline
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
            $proc = Resolve-IncludeDirectives -Content $proc -BlocsRoot $coreSource
            $proc = $proc -replace '\{\{CONFIG_FILE\}\}', $configFileRef
            $proc = Add-McpFirstBlock -ProcedureContent $proc -SkillName $name -BlocsRoot $coreSource
            $assembled = $tpl.Replace('{{PROCEDURE}}', $proc)
            Set-Content -Path (Join-Path $promptsTarget "$name.md") -Value $assembled -Encoding utf8NoBOM -NoNewline
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
            $proc = Resolve-IncludeDirectives -Content $proc -BlocsRoot $coreSource
            $proc = $proc -replace '\{\{CONFIG_FILE\}\}', $configFileRef
            $proc = Add-McpFirstBlock -ProcedureContent $proc -SkillName $name -BlocsRoot $coreSource
            $assembled = $tpl.Replace('{{PROCEDURE}}', $proc)
            $destDir = Join-Path $skillsTarget $name
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Set-Content -Path (Join-Path $destDir 'SKILL.md') -Value $assembled -Encoding utf8NoBOM -NoNewline
            Write-Ok "Skill   : $name/SKILL.md"
        }
    }

    # memory-kit.json au niveau utilisateur
    Write-MemoryKitJson -Path (Join-Path $ConfigDir 'memory-kit.json') -Vault $VaultPath -KitRepo $KitRoot -Language $script:Language -Force:$Force

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
                Set-Content -Path $legacyFile -Value $cleaned -Encoding utf8NoBOM -NoNewline
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
    Set-Content -Path $agentsFile -Value $final -Encoding utf8NoBOM -NoNewline
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
            $proc = Resolve-IncludeDirectives -Content $proc -BlocsRoot $coreSource
            $proc = $proc -replace '\{\{CONFIG_FILE\}\}', $configFileRef
            $proc = Add-McpFirstBlock -ProcedureContent $proc -SkillName $name -BlocsRoot $coreSource
            $assembled = $tpl.Replace('{{PROCEDURE}}', $proc)
            $destDir = Join-Path $skillsTarget $name
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Set-Content -Path (Join-Path $destDir 'SKILL.md') -Value $assembled -Encoding utf8NoBOM -NoNewline
            Write-Ok "Skill   : $name/SKILL.md"
        }
    }

    return $true
}

# ============================================================
# Adapter : GitHub Copilot CLI
# ============================================================
# Surface confirmee (mai 2026) :
#   - skills/{nom}/SKILL.md format Anthropic (frontmatter name + description),
#     auto-decouvert depuis ~/.copilot/skills/. Chaque skill expose nativement
#     son slash command /{name} (issue #1113 toujours OPEN cote slash commands
#     user-definis autonomes, mais les skills suffisent).
#   - Instructions user-level dans ~/.copilot/copilot-instructions.md
#     (equivalent CLAUDE.md / GEMINI.md / AGENTS.md cote user).
#   - Pas de couche prompts/ separee comme Codex : le skill EST le slash command.
#   - Override config dir via $env:COPILOT_HOME.

function Deploy-CopilotCli {
    param(
        [string]$KitRoot,
        [string]$ConfigDir,
        [string]$VaultPath,
        [switch]$Force
    )

    Write-Host ''
    Write-Step "> Deploiement : GitHub Copilot CLI"

    if (-not (Test-Path $ConfigDir)) {
        Write-Warn2 "Dossier Copilot CLI introuvable ($ConfigDir). Lance 'copilot' au moins une fois."
        return $false
    }

    $adapterDir = Join-Path $KitRoot 'adapters\copilot-cli'
    $coreSource = Join-Path $KitRoot 'core\procedures'

    # --- Skills (format Anthropic : skills/{nom}/SKILL.md) ---
    $skillsTarget = Join-Path $ConfigDir 'skills'
    if (-not (Test-Path $skillsTarget)) {
        New-Item -ItemType Directory -Path $skillsTarget -Force | Out-Null
    }
    $skillsSource = Join-Path $adapterDir 'skills'
    $configFileRef = '`~/.copilot/memory-kit.json` (ou `$COPILOT_HOME/memory-kit.json` si defini)'
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
            $proc = Resolve-IncludeDirectives -Content $proc -BlocsRoot $coreSource
            $proc = $proc -replace '\{\{CONFIG_FILE\}\}', $configFileRef
            $proc = Add-McpFirstBlock -ProcedureContent $proc -SkillName $name -BlocsRoot $coreSource
            $assembled = $tpl.Replace('{{PROCEDURE}}', $proc)
            $destDir = Join-Path $skillsTarget $name
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Set-Content -Path (Join-Path $destDir 'SKILL.md') -Value $assembled -Encoding utf8NoBOM -NoNewline
            Write-Ok "Skill   : $name/SKILL.md"
        }
    }

    # --- Bloc d'instructions dans ~/.copilot/copilot-instructions.md ---
    # Note : Copilot CLI accepte aussi AGENTS.md repo-level, mais cote user
    # c'est copilot-instructions.md qui est canonique (cf. doc officielle).
    $blockPath = Join-Path $adapterDir 'copilot-instructions-block.md'
    if (-not (Test-Path $blockPath)) {
        Write-Warn2 "copilot-instructions-block.md manquant : $blockPath"
        return $false
    }
    $blockContent = Get-Content -Path $blockPath -Raw
    $blockContent = $blockContent -replace '\{\{VAULT_PATH\}\}', ($VaultPath -replace '\\', '/')

    $instructionsFile = Join-Path $ConfigDir 'copilot-instructions.md'
    $startMarker = '<!-- MEMORY-KIT:START -->'
    $endMarker   = '<!-- MEMORY-KIT:END -->'
    $pattern = [regex]::Escape($startMarker) + '[\s\S]*?' + [regex]::Escape($endMarker)
    $existing = if (Test-Path $instructionsFile) { (Get-Content -Path $instructionsFile -Raw) ?? '' } else { '' }
    $cleaned = [regex]::Replace($existing, $pattern, '').TrimEnd()
    $final = if ($cleaned) { $cleaned + "`n`n" + $blockContent } else { $blockContent }
    Set-Content -Path $instructionsFile -Value $final -Encoding utf8NoBOM -NoNewline
    Write-Ok "copilot-instructions.md : bloc MEMORY-KIT injecte"

    # --- memory-kit.json au niveau utilisateur ---
    Write-MemoryKitJson -Path (Join-Path $ConfigDir 'memory-kit.json') -Vault $VaultPath -KitRepo $KitRoot -Language $script:Language -Force:$Force

    return $true
}

# ============================================================
# Deploy-McpServer (v0.8.0) — install pipx + sync configs MCP
# ============================================================
# Installe le serveur Python memory-kit-mcp via pipx (fallback pip --user),
# ecrit ~/.memory-kit/config.json, et inject la declaration MCP dans les
# configs des CLI compatibles (Claude Code, Codex, Copilot CLI).
#
# Mistral Vibe et Gemini CLI ne supportent pas MCP a ce jour : skips
# silencieux.

function Test-PipxAvailable {
    return $null -ne (Get-Command pipx -ErrorAction SilentlyContinue)
}

# Tente d'installer pipx automatiquement si absent. Strategie cascadee :
# 1. winget (gestionnaire de paquets natif Windows 10+).
# 2. scoop si dispo (frequent chez les devs Windows).
# 3. Fallback universel : `python -m pip install --user pipx` (avec
#    --break-system-packages si requis).
# Apres install, ajoute le scripts dir Python au PATH de la session courante
# si pipx n'est pas encore visible. Retour : $true si pipx dispo en sortie.
function Install-Pipx {
    if (Test-PipxAvailable) { return $true }
    Write-Step "Installation automatique de pipx..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $null = & winget install --id pypa.pipx -e --silent --accept-package-agreements --accept-source-agreements 2>&1
        Update-PipxOnPath
        if (Test-PipxAvailable) {
            Write-Ok "pipx installe via winget"
            return $true
        }
        Write-Warn2 "winget install pipx a echoue, tentative fallback pip --user..."
    }

    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        $null = & scoop install pipx 2>&1
        Update-PipxOnPath
        if (Test-PipxAvailable) {
            Write-Ok "pipx installe via scoop"
            return $true
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $python) {
        Write-Warn2 "python introuvable — impossible d'installer pipx automatiquement"
        return $false
    }

    & $python.Source -m pip install --user pipx 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $python.Source -m pip install --user --break-system-packages pipx 2>&1 | Out-Null
    }
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "pipx installe via pip --user"
        Update-PipxOnPath
        if (Test-PipxAvailable) { return $true }
        Write-Warn2 "pipx installe mais introuvable sur PATH apres ajout du scripts dir Python."
        return $false
    }
    Write-Warn2 "Echec install automatique de pipx."
    return $false
}

# pipx ensurepath ne touche que le profil utilisateur (registry) — pas le PATH
# de la session courante. On ajoute le scripts dir Python (--user site-packages)
# au PATH de la session pour que pipx soit appelable immediatement.
function Update-PipxOnPath {
    if (Test-PipxAvailable) {
        & pipx ensurepath 2>&1 | Out-Null
        return
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $python) { return }
    $userBase = & $python.Source -c "import site; print(site.USER_BASE)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $userBase) {
        $scriptsDir = Join-Path $userBase 'Scripts'
        if (Test-Path $scriptsDir) {
            $env:PATH = "$scriptsDir;$env:PATH"
        }
        $binDir = Join-Path $userBase 'bin'
        if (Test-Path $binDir) {
            $env:PATH = "$binDir;$env:PATH"
        }
    }
    if (Test-PipxAvailable) {
        & pipx ensurepath 2>&1 | Out-Null
    }
}

function Install-McpServerPackage {
    param(
        [Parameter(Mandatory=$true)][string]$KitRoot,
        [switch]$Repair
    )
    $mcpServerDir = Join-Path $KitRoot 'mcp-server'
    if (-not (Test-Path $mcpServerDir)) {
        Write-Skip "mcp-server/ absent du kit (skip silencieux)"
        return $false
    }

    # --repair-mcp : nettoie l'install pipx avant de réinstaller. Couvre les
    # cas d'incohérence (shim créé par une install récente mais venv resté
    # sur une ancienne version, ModuleNotFoundError sur un module récent...).
    # Tolère l'absence du package (uninstall silencieux).
    if ($Repair -and (Test-PipxAvailable)) {
        Write-Step "Mode --repair-mcp : nettoyage de l'install pipx avant reinstall..."
        # Kill les processus avant uninstall, sinon l'uninstall peut échouer.
        $mcpProcs = Get-Process -Name memory-kit-mcp -ErrorAction SilentlyContinue
        if ($mcpProcs) {
            Write-Info "Fermeture de $($mcpProcs.Count) process(s) memory-kit-mcp actif(s)..."
            $mcpProcs | Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
        $uninstOutput = & pipx uninstall memory-kit-mcp 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Ancien package memory-kit-mcp desinstalle"
        } else {
            # Tolérance : peut-être pas installé, ou install corrompue. On continue.
            Write-Skip "pipx uninstall n'a pas trouve d'install precedente (ou install corrompue) — on continue"
        }
    }

    # Si binaire deja sur PATH, on tolere un echec d'upgrade (WinError 32 :
    # binaire utilise par une session CLI active qui a charge le serveur MCP).
    $alreadyInstalled = $null -ne (Get-Command memory-kit-mcp -ErrorAction SilentlyContinue)

    # Determine la version cible (depuis pyproject.toml du kit) et la version
    # actuellement installee via pipx (si applicable). Permet de signaler
    # CLAIREMENT a l'utilisateur quand une session active bloque l'upgrade,
    # plutot que de masquer l'obsolescence avec un "upgrade differe" silencieux.
    $targetVersion = $null
    $pyprojectPath = Join-Path $mcpServerDir 'pyproject.toml'
    if (Test-Path $pyprojectPath) {
        $versionLine = Select-String -Path $pyprojectPath -Pattern '^\s*version\s*=\s*"([^"]+)"' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($versionLine) {
            $targetVersion = $versionLine.Matches[0].Groups[1].Value
        }
    }
    $installedVersion = $null
    if ($alreadyInstalled -and (Test-PipxAvailable)) {
        $pipxList = & pipx list --short 2>&1
        if ($LASTEXITCODE -eq 0) {
            $line = $pipxList | Where-Object { $_ -match '^memory-kit-mcp\s+(\S+)' } | Select-Object -First 1
            if ($line -match '^memory-kit-mcp\s+(\S+)') {
                $installedVersion = $matches[1]
            }
        }
    }

    [void](Install-Pipx)

    if (Test-PipxAvailable) {
        Write-Step "Install/upgrade memory-kit-mcp via pipx..."
        if ($targetVersion -and $installedVersion -and ($targetVersion -ne $installedVersion)) {
            Write-Info "Pipx package version: $installedVersion installed, $targetVersion required."
        }
        $pipxOutput = & pipx install --force $mcpServerDir 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "memory-kit-mcp installe via pipx (version $targetVersion)"
            return $true
        }

        # WinError 32 = fichier utilise (CLI active a charge le serveur).
        # Si la version installee MATCH la version cible, l'echec d'upgrade est
        # un no-op fonctionnel — accepte sans bruit.
        $isInUseError = ($pipxOutput -match 'WinError 32|cannot access|in use|deleteme')
        $versionsMatch = ($targetVersion -and $installedVersion -and ($targetVersion -eq $installedVersion))
        if ($alreadyInstalled -and $isInUseError -and $versionsMatch) {
            Write-Skip "memory-kit-mcp deja a la bonne version ($installedVersion) — upgrade no-op"
            return $true
        }

        # Si l'upgrade est REQUIS (versions divergent) et qu'on a un WinError
        # par fichier en cours d'usage : kill les processus memory-kit-mcp*
        # actifs (clients MCP qui ont charge le serveur via stdio), puis retry.
        # Les CLI clients (Claude Code, Codex, ...) reconnecteront automatiquement
        # leur connexion MCP au prochain appel d'outil — l'interruption est
        # transparente cote utilisateur final.
        if ($alreadyInstalled -and $isInUseError) {
            $mcpProcs = Get-Process -Name memory-kit-mcp -ErrorAction SilentlyContinue
            if ($mcpProcs) {
                Write-Info "Upgrade requis ($installedVersion -> $targetVersion). Fermeture de $($mcpProcs.Count) process(s) memory-kit-mcp actif(s)..."
                Write-Info "Les sessions CLI (Claude Code / Codex / Copilot / Vibe / Desktop) reconnecteront automatiquement au prochain outil MCP appele."
                $mcpProcs | Stop-Process -Force -ErrorAction SilentlyContinue
                Start-Sleep -Milliseconds 800
            }
            $pipxOutput2 = & pipx install --force $mcpServerDir 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Ok "memory-kit-mcp upgrade vers $targetVersion (apres fermeture des sessions actives)"
                return $true
            }
            # Echec persistant apres kill — cas rare (binaire verrouille par
            # autre chose qu'un process MCP). On signale clairement.
            Write-Warn2 "Upgrade encore bloque apres fermeture des process MCP. Sortie pipx :"
            Write-Host "    $pipxOutput2" -ForegroundColor DarkGray
            Write-Warn2 "Le serveur MCP reste sur la version $installedVersion. Tente : reboot du poste, puis relance deploy.ps1."
            return $true
        }
        Write-Warn2 "pipx install a echoue (exit $LASTEXITCODE)."
        if ($alreadyInstalled) {
            Write-Info "Binaire memory-kit-mcp deja sur PATH — utilisation de la version existante."
            return $true
        }
        Write-Warn2 "pipx install a echoue (exit $LASTEXITCODE)."
        if ($alreadyInstalled) {
            Write-Info "Binaire memory-kit-mcp deja sur PATH — utilisation de la version existante."
            return $true
        }
        Write-Step "Tentative fallback pip --user..."
    } else {
        Write-Warn2 "pipx indisponible apres tentative d'auto-install."
        if ($alreadyInstalled) {
            Write-Skip "Binaire memory-kit-mcp deja sur PATH — pas d'install pip --user."
            return $true
        }
        Write-Step "Tentative install via pip --user..."
    }

    $python = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if (-not $python) {
        Write-Warn2 "python introuvable. Install MCP server skip."
        return $alreadyInstalled
    }
    & $python.Source -m pip install --user --upgrade $mcpServerDir 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "memory-kit-mcp installe via pip --user"
        return $true
    }
    Write-Warn2 "pip install a echoue (exit $LASTEXITCODE)."
    return $alreadyInstalled
}

function Write-McpServerConfig {
    param(
        [Parameter(Mandatory=$true)][string]$VaultPath,
        [Parameter(Mandatory=$true)][string]$KitRepo,
        [Parameter(Mandatory=$true)][string]$Language
    )
    # Cf. doc d'archi v0.8.0 §8 : ~/.memory-kit/config.json est la source de
    # verite cote MCP server (override via $MEMORY_KIT_HOME).
    $mcpHome = if ($env:MEMORY_KIT_HOME) { $env:MEMORY_KIT_HOME } else { Join-Path $HOME '.memory-kit' }
    if (-not (Test-Path $mcpHome)) {
        New-Item -ItemType Directory -Path $mcpHome -Force | Out-Null
    }
    $configPath = Join-Path $mcpHome 'config.json'
    Write-MemoryKitJson -Path $configPath -Vault $VaultPath -KitRepo $KitRepo -Language $Language -Force
}

function Add-McpServerToJsonConfig {
    param(
        [Parameter(Mandatory=$true)][string]$ConfigPath,
        [Parameter(Mandatory=$true)][string]$ServerName,
        [Parameter(Mandatory=$true)][string]$Command,
        [string]$Label = '',
        [string[]]$LegacyServerNames = @()  # noms a supprimer (migration rename)
    )
    # Pattern commun Claude Code / Copilot CLI : { "mcpServers": { "{name}":
    # { "command": ..., "args": [] } } }. Idempotent : preserve le reste.
    $existing = $null
    if (Test-Path $ConfigPath) {
        try {
            $existing = Get-Content $ConfigPath -Raw | ConvertFrom-Json -AsHashtable
        } catch {
            Write-Warn2 "$ConfigPath illisible ($_). Inject MCP skip."
            return
        }
    } else {
        $existing = [ordered]@{}
        # Cree le parent si necessaire
        $parent = Split-Path -Parent $ConfigPath
        if ($parent -and -not (Test-Path $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
    }

    if (-not $existing.Contains('mcpServers')) {
        $existing['mcpServers'] = [ordered]@{}
    }
    $servers = $existing['mcpServers']

    # Cleanup legacy : retire les noms obsoletes (migration rename, ex
    # 'memory-kit' -> 'secondbrain-memory-kit'). Idempotent.
    $labelTagPre = if ($Label) { " ($Label)" } else { '' }
    foreach ($legacy in $LegacyServerNames) {
        if ($legacy -ne $ServerName -and $servers.Contains($legacy)) {
            $servers.Remove($legacy)
            Write-Ok "$ConfigPath$labelTagPre : mcpServers.$legacy supprime (legacy)"
        }
    }

    $newServer = [ordered]@{
        command = $Command
        args    = @()
    }

    $labelTag = if ($Label) { " ($Label)" } else { '' }

    if ($servers.Contains($ServerName)) {
        # Compare command : si different, update et signale
        $current = $servers[$ServerName]
        if ($current.command -ne $Command) {
            $servers[$ServerName] = $newServer
            $json = $existing | ConvertTo-Json -Depth 100
            Set-Content -Path $ConfigPath -Value $json -Encoding utf8NoBOM -NoNewline
            Write-Ok "$ConfigPath$labelTag : mcpServers.$ServerName mis a jour"
        } else {
            Write-Skip "$ConfigPath$labelTag : mcpServers.$ServerName deja present"
        }
        return
    }

    $servers[$ServerName] = $newServer
    $json = $existing | ConvertTo-Json -Depth 100
    Set-Content -Path $ConfigPath -Value $json -Encoding utf8NoBOM -NoNewline
    Write-Ok "$ConfigPath$labelTag : mcpServers.$ServerName ajoute"
}

function Add-McpServerToTomlConfig {
    param(
        [Parameter(Mandatory=$true)][string]$ConfigPath,
        [Parameter(Mandatory=$true)][string]$SectionName,
        [Parameter(Mandatory=$true)][string]$Command,
        [string]$Label = ''
    )
    # Codex : ~/.codex/config.toml. Pas de parser TOML natif PowerShell, on
    # gere via markers idempotents <!-- MEMORY-KIT:START --> / END dans des
    # commentaires TOML #.
    $startMarker = '# MEMORY-KIT:START'
    $endMarker   = '# MEMORY-KIT:END'
    $block = @"
$startMarker
[mcp_servers.$SectionName]
command = "$Command"
args = []
$endMarker
"@

    $labelTag = if ($Label) { " ($Label)" } else { '' }

    if (-not (Test-Path $ConfigPath)) {
        $parent = Split-Path -Parent $ConfigPath
        if ($parent -and -not (Test-Path $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Set-Content -Path $ConfigPath -Value $block -Encoding utf8NoBOM -NoNewline
        Write-Ok "$ConfigPath$labelTag : section [mcp_servers.$SectionName] cree (nouveau fichier)"
        return
    }

    $existing = (Get-Content -Path $ConfigPath -Raw) ?? ''
    $pattern = [regex]::Escape($startMarker) + '[\s\S]*?' + [regex]::Escape($endMarker)
    if ($existing -match $pattern) {
        # Utiliser un MatchEvaluator pour passer $block litteralement (sinon les
        # groupes $1, $2 du replacement seraient interpretes par regex).
        $evaluator = [System.Text.RegularExpressions.MatchEvaluator]{ param($m) return $block }
        $newContent = [regex]::Replace($existing, $pattern, $evaluator)
        # Compare avant/apres : si pas de changement reel, skip
        if ($newContent -eq $existing) {
            Write-Skip "$ConfigPath$labelTag : section MEMORY-KIT deja a jour"
            return
        }
        Set-Content -Path $ConfigPath -Value $newContent -Encoding utf8NoBOM -NoNewline
        Write-Ok "$ConfigPath$labelTag : section MEMORY-KIT mise a jour"
    } else {
        $separator = if ($existing.TrimEnd().Length -gt 0) { "`n`n" } else { '' }
        $merged = $existing.TrimEnd() + $separator + $block + "`n"
        Set-Content -Path $ConfigPath -Value $merged -Encoding utf8NoBOM -NoNewline
        Write-Ok "$ConfigPath$labelTag : section MEMORY-KIT injectee"
    }
}

function Add-McpServerToVibeTomlConfig {
    param(
        [Parameter(Mandatory=$true)][string]$ConfigPath,
        [Parameter(Mandatory=$true)][string]$ServerName,
        [Parameter(Mandatory=$true)][string]$Command,
        [string]$Label = ''
    )
    # Vibe utilise le format TOML "table d'arrays" [[mcp_servers]] (different
    # de Codex qui utilise [mcp_servers.X]). Inspire de mcp-iris-connector qui
    # configure son serveur via ce meme fichier ~/.vibe/config.toml.
    $startMarker = '# MEMORY-KIT:START'
    $endMarker   = '# MEMORY-KIT:END'
    $block = @"
$startMarker
[[mcp_servers]]
name = "$ServerName"
transport = "stdio"
command = "$Command"
args = []
$endMarker
"@

    $labelTag = if ($Label) { " ($Label)" } else { '' }

    if (-not (Test-Path $ConfigPath)) {
        $parent = Split-Path -Parent $ConfigPath
        if ($parent -and -not (Test-Path $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Set-Content -Path $ConfigPath -Value $block -Encoding utf8NoBOM -NoNewline
        Write-Ok "$ConfigPath$labelTag : entry [[mcp_servers]] cree (nouveau fichier)"
        return
    }

    $existing = (Get-Content -Path $ConfigPath -Raw) ?? ''
    $pattern = [regex]::Escape($startMarker) + '[\s\S]*?' + [regex]::Escape($endMarker)
    if ($existing -match $pattern) {
        $evaluator = [System.Text.RegularExpressions.MatchEvaluator]{ param($m) return $block }
        $newContent = [regex]::Replace($existing, $pattern, $evaluator)
        if ($newContent -eq $existing) {
            Write-Skip "$ConfigPath$labelTag : section MEMORY-KIT deja a jour"
            return
        }
        Set-Content -Path $ConfigPath -Value $newContent -Encoding utf8NoBOM -NoNewline
        Write-Ok "$ConfigPath$labelTag : section MEMORY-KIT mise a jour"
    } else {
        $separator = if ($existing.TrimEnd().Length -gt 0) { "`n`n" } else { '' }
        $merged = $existing.TrimEnd() + $separator + $block + "`n"
        Set-Content -Path $ConfigPath -Value $merged -Encoding utf8NoBOM -NoNewline
        Write-Ok "$ConfigPath$labelTag : entry [[mcp_servers]] injectee"
    }
}

function Deploy-McpServer {
    param(
        [Parameter(Mandatory=$true)][string]$KitRoot,
        [Parameter(Mandatory=$true)][string]$VaultPath,
        [Parameter(Mandatory=$true)][hashtable]$DetectedConfigs,
        [switch]$Repair
    )
    Write-Host ''
    # Read the kit's target version dynamically from pyproject.toml to avoid
    # the silent-drift trap where a hardcoded "v0.8.0" message stays put while
    # the package bumps. This message reflects what we're ABOUT to install.
    $mcpServerDir = Join-Path $KitRoot 'mcp-server'
    $kitTargetVersion = $null
    $pyprojectForMessage = Join-Path $mcpServerDir 'pyproject.toml'
    if (Test-Path $pyprojectForMessage) {
        $vLine = Select-String -Path $pyprojectForMessage -Pattern '^\s*version\s*=\s*"([^"]+)"' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($vLine) {
            $kitTargetVersion = $vLine.Matches[0].Groups[1].Value
        }
    }
    if ($kitTargetVersion) {
        Write-Step "> Deploiement : MCP server secondbrain-memory-kit (v$kitTargetVersion)"
    } else {
        Write-Step "> Deploiement : MCP server secondbrain-memory-kit"
    }

    $installed = Install-McpServerPackage -KitRoot $KitRoot -Repair:$Repair
    if (-not $installed) {
        Write-Warn2 "MCP server non installe. Les CLI restent en mode skills (fallback)."
        return
    }

    # Verifie que le binaire est sur le PATH. pipx ensurepath persiste l'ajout
    # au profil utilisateur (registry Windows), mais le PATH de la session
    # courante n'est pas rafraichi. On l'execute systematiquement et on
    # injecte PIPX_BIN_DIR dans $env:PATH pour que la verification ci-dessous
    # passe sans avoir a ouvrir un nouveau terminal.
    if (-not (Get-Command memory-kit-mcp -ErrorAction SilentlyContinue)) {
        Write-Step "Activation du PATH pipx (pipx ensurepath + injection session)..."
        & pipx ensurepath 2>&1 | Out-Null
        $pipxBinDir = & pipx environment --value PIPX_BIN_DIR 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $pipxBinDir) {
            $pipxBinDir = Join-Path $HOME '.local\bin'
        }
        if (Test-Path $pipxBinDir) {
            $env:PATH = "$pipxBinDir;$env:PATH"
        }
        if (Get-Command memory-kit-mcp -ErrorAction SilentlyContinue) {
            Write-Ok "memory-kit-mcp accessible apres pipx ensurepath"
        } else {
            Write-Warn2 "Binaire 'memory-kit-mcp' introuvable meme apres pipx ensurepath."
            Write-Info "Ouvre un nouveau terminal ou ajoute manuellement '$pipxBinDir' au PATH."
        }
    }

    Write-McpServerConfig -VaultPath $VaultPath -KitRepo $KitRoot -Language $script:Language

    # Inject MCP server dans les configs CLI compatibles
    if ($DetectedConfigs.ContainsKey('Claude')) {
        $claudeConfig = Join-Path $HOME '.claude.json'
        Add-McpServerToJsonConfig -ConfigPath $claudeConfig -ServerName 'secondbrain-memory-kit' -Command 'memory-kit-mcp' -LegacyServerNames @('memory-kit') -Label 'Claude Code'
    }
    if ($DetectedConfigs.ContainsKey('Codex')) {
        $codexConfig = Join-Path $DetectedConfigs['Codex'] 'config.toml'
        Add-McpServerToTomlConfig -ConfigPath $codexConfig -SectionName 'secondbrain-memory-kit' -Command 'memory-kit-mcp' -Label 'Codex'
    }
    if ($DetectedConfigs.ContainsKey('Copilot')) {
        $copilotMcpConfig = Join-Path $DetectedConfigs['Copilot'] 'mcp-config.json'
        Add-McpServerToJsonConfig -ConfigPath $copilotMcpConfig -ServerName 'secondbrain-memory-kit' -Command 'memory-kit-mcp' -LegacyServerNames @('memory-kit') -Label 'Copilot CLI'
    }
    if ($DetectedConfigs.ContainsKey('Vibe')) {
        # Mistral Vibe supporte MCP via ~/.vibe/config.toml (format
        # [[mcp_servers]] table d'arrays). Pattern verifie en lisant le
        # config existant de mcp-iris-connector qui s'y installe deja.
        $vibeConfig = Join-Path $DetectedConfigs['Vibe'] 'config.toml'
        Add-McpServerToVibeTomlConfig -ConfigPath $vibeConfig -ServerName 'secondbrain-memory-kit' -Command 'memory-kit-mcp' -Label 'Mistral Vibe'
    }

    if ($DetectedConfigs.ContainsKey('Gemini')) {
        # Gemini CLI lit ses serveurs MCP depuis ~/.gemini/settings.json
        # section mcpServers.{name}.command/args (meme format que Claude Code,
        # Copilot CLI, Claude Desktop). Champs extras 'trust' et 'description'
        # acceptes mais non injectes (l'utilisateur peut les ajouter manuellement).
        $geminiSettings = Join-Path $DetectedConfigs['Gemini'] 'settings.json'
        Add-McpServerToJsonConfig -ConfigPath $geminiSettings -ServerName 'secondbrain-memory-kit' -Command 'memory-kit-mcp' -LegacyServerNames @('memory-kit') -Label 'Gemini CLI'
    }

    # Cibles desktop : detection independante des CLI command-line. Leur config
    # MCP est lue par les apps desktop, pas par les binaires CLI.
    $claudeDesktopConfig = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'
    $claudeDesktopDir = Split-Path -Parent $claudeDesktopConfig
    if (Test-Path $claudeDesktopDir) {
        Add-McpServerToJsonConfig -ConfigPath $claudeDesktopConfig -ServerName 'secondbrain-memory-kit' -Command 'memory-kit-mcp' -LegacyServerNames @('memory-kit') -Label 'Claude Desktop'
    } else {
        Write-Skip "Claude Desktop non detecte ($claudeDesktopDir absent)"
    }

    # Codex Desktop : chemin a investiguer (pas detecte sur ce poste, attente
    # info utilisateur sur le bon emplacement).
}

# ============================================================
# Invoke-AutoUpdate (-AutoUpdate) — git pull avant deploy
# ============================================================
# Refuse silencieusement si pas un repo git, branche != main, ou working tree
# dirty. Si pull effectif, le main script se relance depuis la source pullee
# pour eviter de deployer avec une logique deploy.ps1 obsolete en memoire.

function Invoke-AutoUpdate {
    param(
        [Parameter(Mandatory=$true)][string]$KitRoot
    )

    Push-Location $KitRoot
    try {
        $gitCmd = Get-Command git -ErrorAction SilentlyContinue
        if (-not $gitCmd) {
            Write-Skip "git introuvable sur PATH : -AutoUpdate ignore"
            return $false
        }

        $isGit = & git rev-parse --is-inside-work-tree 2>$null
        if ($LASTEXITCODE -ne 0 -or "$isGit".Trim() -ne 'true') {
            Write-Skip "Pas dans un git repo : -AutoUpdate ignore"
            return $false
        }

        $branch = (& git rev-parse --abbrev-ref HEAD 2>$null).Trim()
        if ($branch -ne 'main') {
            Write-Warn2 "Branche actuelle : '$branch' (attendu : main). -AutoUpdate refuse pour ne pas pull une autre branche."
            return $false
        }

        $dirty = & git status --porcelain 2>$null
        if ($dirty) {
            Write-Warn2 "Working tree dirty (changements non commites). -AutoUpdate refuse — commit ou stash d'abord."
            return $false
        }

        Write-Step "git fetch origin --tags..."
        & git fetch origin --tags --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "git fetch a echoue : -AutoUpdate ignore"
            return $false
        }

        $behindRaw = & git rev-list --count "HEAD..origin/main" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Skip "Comparaison HEAD..origin/main impossible (origin/main absent ?)"
            return $false
        }
        $behind = [int]("$behindRaw".Trim())
        if ($behind -eq 0) {
            $localTag = (& git describe --tags --abbrev=0 HEAD 2>$null).Trim()
            $tagSuffix = if ($localTag) { " (tag local : $localTag)" } else { '' }
            Write-Skip "Deja a jour avec origin/main$tagSuffix"
            return $false
        }

        $latestTag = (& git describe --tags --abbrev=0 origin/main 2>$null).Trim()
        $tagSuffix = if ($latestTag) { " — dernier tag remote : $latestTag" } else { '' }
        Write-Step "Update disponible : $behind commit(s) en arriere$tagSuffix. git pull --ff-only..."

        & git pull --ff-only 2>&1 | ForEach-Object { Write-Info $_ }
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "git pull --ff-only a echoue : -AutoUpdate ignore (deploy continue avec la version en memoire)"
            return $false
        }
        Write-Ok "Kit mis a jour depuis origin/main"
        return $true
    } finally {
        Pop-Location
    }
}

# ============================================================
# 1. Resolution des chemins
# ============================================================

$kitRoot = $PSScriptRoot
Write-Step "Racine du kit : $kitRoot"

# -AutoUpdate : tente un git pull --ff-only avant de poursuivre. Si update
# effectif, on relance le script depuis la source mise a jour pour eviter
# de deployer avec une logique deploy.ps1 obsolete deja chargee en memoire.
if ($AutoUpdate) {
    Write-Host ''
    Write-Step "Mode -AutoUpdate : verification des updates remote..."
    $updated = Invoke-AutoUpdate -KitRoot $kitRoot
    if ($updated) {
        Write-Step "Re-execution de deploy.ps1 depuis la source mise a jour..."
        $reexecArgs = @{}
        foreach ($key in $PSBoundParameters.Keys) {
            if ($key -ne 'AutoUpdate') {
                $reexecArgs[$key] = $PSBoundParameters[$key]
            }
        }
        & $PSCommandPath @reexecArgs
        exit $LASTEXITCODE
    }
}

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

# Resolution de la langue (param explicite, detection systeme, ou prompt interactif)
$script:Language = Resolve-Language -Explicit $Language
Write-Step "Langue conversationnelle : $script:Language"

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
    },
    [ordered]@{
        Name        = 'copilot-cli'
        DisplayName = 'GitHub Copilot CLI'
        Binary      = 'copilot'
        ConfigDir   = if ($env:COPILOT_HOME) { $env:COPILOT_HOME } else { Join-Path $HOME '.copilot' }
        DeployFunc  = 'Deploy-CopilotCli'
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
    Write-Info 'Claude Code        : https://claude.com/claude-code'
    Write-Info 'Gemini CLI         : https://github.com/google-gemini/gemini-cli'
    Write-Info 'Codex              : https://github.com/openai/codex'
    Write-Info 'Mistral Vibe       : (voir documentation Mistral AI)'
    Write-Info 'GitHub Copilot CLI : https://github.com/github/copilot-cli'
    Write-Host ''
    exit 0
}

# ============================================================
# 4. Cleanup migration v0.4 -> v0.5 (idempotent)
# ============================================================

Write-Host ''
Write-Step 'Cleanup migration v0.4 -> v0.5 (skills renommes)...'
$configMap = @{}
foreach ($p in $detected) {
    switch ($p.Name) {
        'claude-code'   { $configMap['Claude']  = $p.ConfigDir }
        'gemini-cli'    { $configMap['Gemini']  = $p.ConfigDir }
        'codex'         { $configMap['Codex']   = $p.ConfigDir }
        'mistral-vibe'  { $configMap['Vibe']    = $p.ConfigDir }
        'copilot-cli'   { $configMap['Copilot'] = $p.ConfigDir }
    }
}
Remove-DeprecatedV04Files -ConfigDirs $configMap

# ============================================================
# 5. Deploiement par plateforme detectee
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
# 6. Scaffold du vault si vide (premiere installation)
# ============================================================
# Si le vault ne contient pas la zone canonique 10-episodes/, on considere
# que c'est une premiere install et on appelle scripts/scaffold-vault.py
# pour creer la structure des 9 zones + index.md (i18n via memory-kit.json).

Write-Host ''
$episodesDir = Join-Path $VaultPath '10-episodes'
if (-not (Test-Path $episodesDir)) {
    Write-Step "Vault vierge detecte : scaffolding de la structure v0.5..."
    $python = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($python) {
        $scaffoldScript = Join-Path $kitRoot 'scripts\scaffold-vault.py'
        & $python.Source $scaffoldScript --vault $VaultPath --language $script:Language
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "scaffold-vault.py a echoue (vault partiellement initialise)"
        }
    } else {
        Write-Warn2 "python introuvable : scaffold ignore. Cree manuellement les zones via scripts\scaffold-vault.py."
    }
} else {
    Write-Skip "Vault deja peuple (10-episodes/ present), scaffold ignore"
}

# ============================================================
# 6.5. Deploy-ObsidianStyle (v0.7.2, opt-out via -SkipObsidianStyle)
# ============================================================

if (-not $SkipObsidianStyle) {
    Write-Host ''
    Deploy-ObsidianStyle -KitRoot $KitRoot -VaultPath $VaultPath -Force:$ForceObsidianStyle
}

# ============================================================
# 6.6. Deploy-McpServer (v0.8.0, opt-out via -SkipMcpServer)
# ============================================================

if (-not $SkipMcpServer) {
    Deploy-McpServer -KitRoot $kitRoot -VaultPath $VaultPath -DetectedConfigs $configMap -Repair:$RepairMcp
}

# ============================================================
# 6.7. Vault schema migrations (v0.9.4, opt-out via -SkipMigrations)
# ============================================================
# Detect pending vault schema migrations and run them automatically.
# Idempotent: a vault already on the target schema version is skipped.
# An auto-backup is taken before any apply (capped at 500 MiB; user must
# pass --skip-backup if their vault is bigger).

if (-not $SkipMcpServer) {
    Write-Host ''
    Write-Step "Vault schema migrations..."

    # Resolve the migrate command. Priority:
    # 1. memory-kit-migrate on PATH (pipx entry-point installed by Deploy-McpServer)
    # 2. fallback to {pipx-bin-dir}/memory-kit-migrate.exe (PATH not yet refreshed
    #    in this shell session)
    $migrateCmd = $null
    $migrateOnPath = Get-Command memory-kit-migrate -ErrorAction SilentlyContinue
    if ($migrateOnPath) {
        $migrateCmd = $migrateOnPath.Source
    } else {
        # Fallback: ask pipx for its bin dir and look for the entry point there.
        $pipxBinDir = $null
        $pipxCmd = Get-Command pipx -ErrorAction SilentlyContinue
        if ($pipxCmd) {
            try {
                $pipxBinDir = (& $pipxCmd.Source environment --value PIPX_BIN_DIR 2>$null).Trim()
            } catch {
                $pipxBinDir = $null
            }
        }
        if ($pipxBinDir -and (Test-Path $pipxBinDir)) {
            $candidate = Join-Path $pipxBinDir 'memory-kit-migrate.exe'
            if (Test-Path $candidate) { $migrateCmd = $candidate }
        }
    }

    if ($migrateCmd) {
        $migrateDry = & $migrateCmd --quiet 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "Migration dry-run failed (will skip auto-apply): $migrateDry"
        } elseif ($migrateDry -match "No pending migrations|Nothing to migrate") {
            Write-Skip "Vault schema already up to date."
        } else {
            Write-Info "Pending migrations detected — applying with auto-backup..."
            & $migrateCmd --apply
            if ($LASTEXITCODE -ne 0) {
                Write-Warn2 "Migration failed. Check the output above. Backup is preserved under ~/.memory-kit/backups/."
            } else {
                Write-Ok "Vault migrations applied successfully."
            }
        }
    } else {
        Write-Skip "memory-kit-migrate not found (pipx package not installed yet?). Run manually: memory-kit-migrate --apply"
    }
}

# ============================================================
# 7. Resume final
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
            'Claude Code'        { Write-Host "  [Claude Code]        /mem-recall (dans une nouvelle session)" -ForegroundColor Cyan }
            'Gemini CLI'         { Write-Host "  [Gemini CLI]         /mem-recall (dans une nouvelle session)" -ForegroundColor Cyan }
            'Codex (OpenAI)'     { Write-Host "  [Codex]              /mem-recall (dans une nouvelle session)" -ForegroundColor Cyan }
            'Mistral Vibe'       { Write-Host "  [Mistral Vibe]       dis 'charge mon contexte memoire' (Vibe expose le MCP secondbrain-memory-kit + skills mais pas de slash commands)" -ForegroundColor Cyan }
            'GitHub Copilot CLI' { Write-Host "  [Copilot CLI]        /mem-recall (dans une nouvelle session)" -ForegroundColor Cyan }
        }
    }
}
