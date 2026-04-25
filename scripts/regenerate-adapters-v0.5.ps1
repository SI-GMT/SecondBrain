#Requires -Version 7.0

<#
.SYNOPSIS
    Regenere les templates adapters pour la v0.5 : renommages + nouveaux skills.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Write-Ok([string]$msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Step([string]$msg) { Write-Host $msg -ForegroundColor Cyan }

# Definitions des skills v0.5
$skillsV05 = [ordered]@{
    'mem' = @{
        Description = "Router universel d'ingestion. Recoit un contenu libre, le segmente en atomes, classe chaque atome dans la bonne zone du vault selon une cascade d'heuristiques. Chemin par defaut zero-friction. Declencher quand l'utilisateur dit 'note ceci', 'enregistre', 'capture ca', 'ajoute a la memoire' sans preciser de zone."
        ArgsText = "Contenu a ingerer. Le router decide ou il va. Options : --scope perso|pro, --zone X (force la zone), --projet/--domaine {slug} (force le rattachement), --no-confirm, --dry-run."
    }
    'mem-list' = @{
        Description = "Lister projets et domaines du vault avec leur etat synthetique. Renomme depuis mem-list-projects en v0.5 (gere maintenant projets ET domaines). Peut aussi lister le contenu d'une zone via --zone X."
        ArgsText = "Aucun argument requis. Options : --kind projet|domaine|all, --scope perso|pro|all, --zone X, --detail."
    }
    'mem-rename' = @{
        Description = "Renommer un projet ou un domaine de maniere complete : dossier physique, frontmatter, tags, liens Obsidian, _index.md, historique.md. Renomme depuis mem-rename-project en v0.5 (opere sur projets ET domaines)."
        ArgsText = "Deux arguments obligatoires : ancien-slug nouveau-slug. Options : --dry-run, --no-confirm."
    }
    'mem-merge' = @{
        Description = "Fusionner deux projets OU deux domaines du vault. Reattribue archives + atomes transverses. Restriction : pas de melange projet <-> domaine. Renomme depuis mem-merge-projects en v0.5."
        ArgsText = "Deux arguments obligatoires : source-slug cible-slug. Options : --dry-run, --no-confirm."
    }
    'mem-note' = @{
        Description = "Ingerer rapidement une note de connaissance dans 20-knowledge/. Shortcut explicite quand l'utilisateur sait que ce qu'il capte est un fait, un concept, une fiche, une synthese."
        ArgsText = "Contenu de la note. Options : --scope perso|pro, --famille metier|tech|vie|methodes, --type concept|fiche|glossaire|synthese|reference, --no-confirm, --dry-run."
    }
    'mem-principle' = @{
        Description = "Ingerer un principe (heuristique, ligne rouge, valeur, regle d'action) dans 40-principes/. Shortcut explicite. Le router infere le niveau de contrainte depuis le ton."
        ArgsText = "Contenu du principe. Options : --scope perso|pro, --force ligne-rouge|heuristique|preference, --domaine X, --projet {slug}, --no-confirm, --dry-run."
    }
    'mem-goal' = @{
        Description = "Ingerer un objectif (intention future, etat desire, but) dans 50-objectifs/. Shortcut explicite. Detecte horizon (court/moyen/long) depuis l'echeance."
        ArgsText = "Contenu de l'objectif. Options : --scope perso|pro, --horizon court|moyen|long, --echeance YYYY-MM-DD, --projet {slug}, --no-confirm, --dry-run."
    }
    'mem-person' = @{
        Description = "Ingerer une fiche personne (collegue, client, ami, famille) dans 60-personnes/. Shortcut explicite. Toujours sensitive=true par defaut (interdit la promotion vers CollectiveBrain)."
        ArgsText = "Contenu / description de la personne. Options : --scope perso|pro, --categorie collegues|clients|partenaires|famille|amis|connaissances, --no-confirm, --dry-run."
    }
    'mem-reclass' = @{
        Description = "Changer le scope ou la zone d'un contenu existant. Met a jour frontmatter + tags + deplace le fichier + reecrit les references croisees. Confirme par decision D3.4 du cadrage v0.5."
        ArgsText = "Chemin du fichier obligatoire + au moins une option de changement. Options : --zone X, --scope perso|pro, --type X, --projet/--domaine {slug}, --dry-run, --no-confirm."
    }
    'mem-promote-domain' = @{
        Description = "Promouvoir un ensemble d'items coherents de l'inbox en un nouveau domaine permanent dans 10-episodes/domaines/{slug}/. Verifie la regle anti-derive (>=3 items au meme fil)."
        ArgsText = "Slug du nouveau domaine + items optionnels. Options : --scope perso|pro, --from-inbox {keyword}, --dry-run, --no-confirm."
    }
}

# Skills renommes (mapping ancien -> nouveau pour suppression)
$renamings = @('mem-list-projects', 'mem-rename-project', 'mem-merge-projects')

# Suppression des templates obsoletes
Write-Step "> Suppression des templates renommes"
foreach ($old in $renamings) {
    $paths = @(
        "adapters\claude-code\skills\$old.template.md",
        "adapters\claude-code\commands\$old.md",
        "adapters\gemini-cli\commands\$old.template.toml",
        "adapters\codex\prompts\$old.template.md",
        "adapters\codex\skills\$old",
        "adapters\mistral-vibe\skills\$old"
    )
    foreach ($rel in $paths) {
        $full = Join-Path $root $rel
        if (Test-Path $full) {
            Remove-Item -Path $full -Recurse -Force
            Write-Ok "Supprime : $rel"
        }
    }
}

# Generation des nouveaux templates
Write-Host ''
Write-Step "> Generation des templates v0.5"

foreach ($name in $skillsV05.Keys) {
    Write-Host ''
    Write-Step "  $name"
    $desc = $skillsV05[$name].Description
    $argsTxt = $skillsV05[$name].ArgsText
    $descShort = $desc.Split('.')[0]

    # Claude Code skill
    $p1 = Join-Path $root "adapters\claude-code\skills\$name.template.md"
    $c1 = "---`nname: $name`ndescription: $desc`n---`n`n{{PROCEDURE}}`n"
    Set-Content -Path $p1 -Value $c1 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Claude skill   : $name.template.md"

    # Claude Code command
    $p2 = Join-Path $root "adapters\claude-code\commands\$name.md"
    $c2 = "$descShort.`n`n$argsTxt`n`n`$ARGUMENTS`n"
    Set-Content -Path $p2 -Value $c2 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Claude command : $name.md"

    # Gemini CLI command (literal multi-line strings)
    $p3 = Join-Path $root "adapters\gemini-cli\commands\$name.template.toml"
    $descEsc = $desc -replace '"', '\"'
    $c3 = "description = `"$descEsc`"`nprompt = '''`n{{PROCEDURE}}`n`n---`n$argsTxt`n'''`n"
    Set-Content -Path $p3 -Value $c3 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Gemini cmd     : $name.template.toml"

    # Codex prompt
    $p4 = Join-Path $root "adapters\codex\prompts\$name.template.md"
    $c4 = "---`ndescription: $desc`n---`n`n{{PROCEDURE}}`n`n## User input`n`n``````text`n`$ARGUMENTS`n```````n"
    Set-Content -Path $p4 -Value $c4 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Codex prompt   : $name.template.md"

    # Codex skill
    $d5 = Join-Path $root "adapters\codex\skills\$name"
    if (-not (Test-Path $d5)) { New-Item -ItemType Directory -Path $d5 -Force | Out-Null }
    $p5 = Join-Path $d5 "SKILL.md.template"
    $c5 = "---`nname: $name`ndescription: $desc`n---`n`n{{PROCEDURE}}`n"
    Set-Content -Path $p5 -Value $c5 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Codex skill    : $name/SKILL.md.template"

    # Vibe skill
    $d6 = Join-Path $root "adapters\mistral-vibe\skills\$name"
    if (-not (Test-Path $d6)) { New-Item -ItemType Directory -Path $d6 -Force | Out-Null }
    $p6 = Join-Path $d6 "SKILL.md.template"
    $c6 = "---`nname: $name`ndescription: $desc`nuser-invocable: true`n---`n`n{{PROCEDURE}}`n"
    Set-Content -Path $p6 -Value $c6 -Encoding utf8NoBOM -NoNewline
    Write-Ok "Vibe skill     : $name/SKILL.md.template"
}

Write-Host ''
Write-Step "=== Regeneration adapters terminee ==="
Write-Host "Skills regeneres : $($skillsV05.Count)"
Write-Host "Skills supprimes : $($renamings.Count)"
Write-Host "Lance .\deploy.ps1 pour propager vers les CLI."
