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
    '10-episodes'    = @('projets', 'domaines')
    '20-knowledge'   = @('metier', 'tech', 'vie', 'methodes')
    '30-procedures'  = @('pro', 'perso')
    '40-principes'   = @('pro', 'perso')
    '50-objectifs'   = @('perso/vie', 'perso/sante', 'perso/famille', 'perso/finances', 'pro/carriere', 'pro/projets')
    '60-personnes'   = @('pro/collegues', 'pro/clients', 'pro/partenaires', 'perso/famille', 'perso/amis', 'perso/connaissances')
    '70-cognition'   = @('schemas', 'metaphores', 'moodboards', 'sketches')
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

# 99-meta/_index.md squelette
$indexPath = Join-Path $Target '99-meta\_index.md'
if (-not (Test-Path $indexPath)) {
    $indexContent = @"
---
date: $(Get-Date -Format 'yyyy-MM-dd')
zone: meta
type: index
tags: [zone/meta, type/index]
---

# Vault SecondBrain v0.5 — Index

Point d'entree du second cerveau. Mis a jour automatiquement par les skills
\``mem-*\`` lors des operations d'ecriture.

## Zones

- [00-inbox](../00-inbox/) — captation brute non qualifiee
- [10-episodes](../10-episodes/) — memoire episodique (projets + domaines)
- [20-knowledge](../20-knowledge/) — memoire semantique
- [30-procedures](../30-procedures/) — savoir-faire / how-to
- [40-principes](../40-principes/) — heuristiques et lignes rouges
- [50-objectifs](../50-objectifs/) — prospective et intentions
- [60-personnes](../60-personnes/) — carnet relationnel
- [70-cognition](../70-cognition/) — productions non verbales (cerveau droit)
- [99-meta](.) — meta-memoire du vault (cette zone)

## Projets

(aucun pour l'instant)

## Domaines

(aucun pour l'instant)

## Archives

(aucune pour l'instant)
"@
    Set-Content -Path $indexPath -Value $indexContent -Encoding utf8NoBOM -NoNewline
    Write-Ok "99-meta/_index.md cree"
}

Write-Host ''
Write-Step "=== Scaffold termine ==="
Write-Host "Vault : $Target"
Write-Host "Pour deployer les skills sur ce vault de test :"
Write-Host "  .\deploy.ps1 -VaultPath `"$Target`" -Force"
