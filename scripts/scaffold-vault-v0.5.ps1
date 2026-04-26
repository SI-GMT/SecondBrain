#Requires -Version 7.0

<#
.SYNOPSIS
    Cree l'arborescence des 9 zones du vault SecondBrain v0.5 dans un dossier cible.

.DESCRIPTION
    Scaffolde la structure brain-centric v0.5 (9 zones racines + sous-dossiers
    de base) dans un dossier cible vide ou existant. Idempotent : ne touche pas
    aux dossiers deja crees, ne supprime rien.

    Usage typique :
      - Creer un vault de test pour iterer sur les skills v0.5 sans toucher au prod.
      - Bootstrap un nouveau vault SecondBrain v0.5 from scratch.

    Ce script ne migre PAS un vault v0.4 existant — utiliser
    scripts/migrate-vault-v0.5.py pour cela (phase E).

.PARAMETER Target
    Chemin absolu du dossier cible. Cree si absent.

.PARAMETER Force
    Si le dossier contient deja un sous-dossier d'une zone, l'efface avant
    de le recreer. DESTRUCTIF. A utiliser uniquement sur un vault de test
    qu'on veut reset.

.EXAMPLE
    .\scripts\scaffold-vault-v0.5.ps1 -Target "C:\_BDC\GMT\memory-test"
    .\scripts\scaffold-vault-v0.5.ps1 -Target "D:\new-vault" -Force
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Target,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Skip([string]$msg) { Write-Host "  [--] $msg" -ForegroundColor DarkGray }

# ============================================================
# Definition des 9 zones racines + sous-dossiers de base
# ============================================================

$zones = [ordered]@{
    '00-inbox'       = @()
    '10-episodes'    = @('projects', 'domains')
    '20-knowledge'   = @('business', 'tech', 'life', 'methods')
    '30-procedures'  = @('work', 'personal')
    '40-principles'  = @('work', 'personal')
    '50-goals'       = @('personal/life', 'personal/health', 'personal/family', 'personal/finance', 'work/career', 'work/projects')
    '60-people'      = @('work/colleagues', 'work/clients', 'work/partners', 'personal/family', 'personal/friends', 'personal/acquaintances')
    '70-cognition'   = @('schemas', 'metaphors', 'moodboards', 'sketches')
    '99-meta'        = @()
}

# ============================================================
# Execution
# ============================================================

Write-Step "Scaffold vault SecondBrain v0.5 -> $Target"

if (-not (Test-Path $Target)) {
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
    Write-Ok "Dossier cible cree : $Target"
} else {
    Write-Skip "Dossier cible deja present : $Target"
}

foreach ($zone in $zones.Keys) {
    $zonePath = Join-Path $Target $zone
    if (Test-Path $zonePath) {
        if ($Force) {
            Remove-Item -Path $zonePath -Recurse -Force
            New-Item -ItemType Directory -Path $zonePath -Force | Out-Null
            Write-Ok "Zone $zone reset (Force)"
        } else {
            Write-Skip "Zone $zone existe deja"
        }
    } else {
        New-Item -ItemType Directory -Path $zonePath -Force | Out-Null
        Write-Ok "Zone $zone creee"
    }

    foreach ($sub in $zones[$zone]) {
        $subPath = Join-Path $zonePath $sub
        if (-not (Test-Path $subPath)) {
            New-Item -ItemType Directory -Path $subPath -Force | Out-Null
            Write-Ok "  Sous-dossier $zone/$sub cree"
        }
    }
}

# ============================================================
# Fichiers seed
# ============================================================

# .gitignore minimal pour eviter de commiter le vault par accident s'il est versionne
$gitignorePath = Join-Path $Target '.gitignore'
if (-not (Test-Path $gitignorePath)) {
    @(
        '# Vault SecondBrain — non versionne par defaut',
        '# Si tu veux versionner, supprime ce fichier mais reflechis aux donnees personnelles',
        '*'
    ) -join "`n" | Set-Content -Path $gitignorePath -Encoding utf8NoBOM -NoNewline
    Write-Ok ".gitignore cree (vault non versionne par defaut)"
}

# index.md squelette (a la racine du vault)
$indexPath = Join-Path $Target 'index.md'
if (-not (Test-Path $indexPath)) {
    $indexContent = @"
---
date: $(Get-Date -Format 'yyyy-MM-dd')
zone: meta
type: index
tags: [zone/meta, type/index]
---

# Vault SecondBrain v0.5 — Index

Entry point of the second brain. Automatically updated by the \``mem-*\`` skills
on write operations.

## Zones

- [00-inbox](00-inbox/) — raw unqualified capture
- [10-episodes](10-episodes/) — episodic memory (projects + domains)
- [20-knowledge](20-knowledge/) — semantic memory
- [30-procedures](30-procedures/) — know-how / how-to
- [40-principles](40-principles/) — heuristics and red lines
- [50-goals](50-goals/) — prospective intentions
- [60-people](60-people/) — relational notebook
- [70-cognition](70-cognition/) — non-verbal productions (right brain)
- [99-meta](99-meta/) — vault meta-memory

## Projects

(none yet)

## Domains

(none yet)

## Archives

(none yet)
"@
    Set-Content -Path $indexPath -Value $indexContent -Encoding utf8NoBOM -NoNewline
    Write-Ok "index.md cree"
}

Write-Host ''
Write-Step "=== Scaffold termine ==="
Write-Host "Vault : $Target"
Write-Host "Pour deployer les skills sur ce vault de test :"
Write-Host "  .\deploy.ps1 -VaultPath `"$Target`" -Force"
