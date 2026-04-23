# Procédure : Archeo Atlassian

Objectif : **rétro-archiver une arborescence de pages Confluence** (une page racine + toute sa descendance, ou un space complet) dans le vault mémoire, avec **enrichissement automatique par les tickets Jira référencés** depuis les pages. Une archive par page Confluence ; chaque archive inclut la synthèse structurée de la page et la fiche résumée des tickets Jira qu'elle mentionne.

Complémentaire de `/mem-archeo` (rétro Git) : ensemble, ils couvrent respectivement le côté « code » et le côté « documentation/cadrage » d'un projet. Particulièrement utile pour les projets SI-GMT dont les SFD/STD/chiffrages vivent dans Confluence et dont le pilotage passe par Jira.

## Déclenchement

L'utilisateur tape `/mem-archeo-atlassian {url}` ou exprime l'intention en langage naturel : « archive la documentation Confluence de ce projet », « fais une rétro sur cet espace Atlassian », « ingère cette page et ses enfants », « remonte tout l'arbre de cette racine Confluence ».

Arguments possibles :
- `{url}` (**obligatoire**) : URL Confluence d'une page (ex: `https://{org}.atlassian.net/wiki/spaces/KEY/pages/12345/Titre`) ou d'un space root (ex: `https://{org}.atlassian.net/wiki/spaces/KEY`).
- `--projet {nom}` : force le projet cible. Sinon, résolution automatique.
- `--profondeur N` : limite de récursion dans la descendance (défaut : illimitée).
- `--skip-children` : n'archive que la page cible, pas ses enfants (ignoré si URL est un space root).
- `--depuis YYYY-MM-DD` : ne considère que les pages modifiées après cette date.
- `--skip-jira` : désactive l'enrichissement Jira (par défaut activé).
- `--dry-run` : liste les pages qui seraient archivées, sans écrire.

## Prérequis — MCP Atlassian côté client

Cette procédure exige que le client LLM dispose du **MCP Atlassian** (outils `mcp_*_Atlassian_*` disponibles, typiquement depuis `claude.ai/mcp` ou une config MCP locale équivalente). Les outils attendus :

- Confluence : `getConfluencePage`, `getConfluencePageDescendants`, `getPagesInConfluenceSpace`, éventuellement `searchConfluenceUsingCql`.
- Jira : `getJiraIssue`.

**Avant d'exécuter la procédure**, vérifier qu'au moins `getConfluencePage` est accessible. Si absent :

> Le skill `/mem-archeo-atlassian` nécessite le MCP Atlassian côté client (outils `getConfluencePage`, `getJiraIssue`, etc.). Il n'est pas disponible dans cette session. Installe le MCP Atlassian via claude.ai/mcp ou équivalent, puis relance.

Puis s'arrêter.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire le champ `vault`. Dans la suite, `{VAULT}` désigne cette valeur. Si absent : message d'erreur standard puis arrêt.

## Encodage des fichiers écrits

**Tous les fichiers écrits ou modifiés par cette procédure doivent l'être en UTF-8 sans BOM, fins de ligne LF.** Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM.

Selon l'outil d'écriture :
- **Shell POSIX** : natif UTF-8 sans BOM.
- **PowerShell 7+ (pwsh)** : `Set-Content -Encoding utf8NoBOM`.
- **Windows PowerShell 5.1** : `[System.IO.File]::WriteAllText(...)` avec `UTF8Encoding($false)`.
- **cmd.exe** : à éviter pour du Markdown accentué.
- **Python** (méthode la plus fiable sur Windows) : `Path(path).write_text(contenu, encoding='utf-8', newline='')`.

**Attention particulière aux pages Confluence** : le contenu renvoyé par `getConfluencePage` peut contenir des caractères spéciaux (guillemets typographiques, tirets cadratins, espaces insécables). Ne pas re-encoder manuellement — passer le contenu tel quel à la fonction d'écriture UTF-8.

## Écritures atomiques et protection contre les accès concurrents

Mêmes patterns que les autres procédures `mem-*` :

### Pattern 1 — Rename atomique (toutes les écritures)

1. Écrire dans `{fichier}.tmp`.
2. Rename atomique → `{fichier}`.
3. En cas d'échec, supprimer le `.tmp`.

### Pattern 2 — Hash check read-before-write (fichiers partagés)

Pour `_index.md` et `historique.md` : capture SHA-256 au début, re-hash avant écriture, merger + retry (max 3) si divergence. Batch les ajouts en fin de procédure (1 seul update par fichier, pas N).

Les archives horodatées sont nouvelles, exemptées du hash check (pattern 1 seul).

## Procédure

### 1. Valider l'URL et extraire les identifiants

- Vérifier que `{url}` est une URL Confluence valide. Formats reconnus :
  - Page : `.../wiki/spaces/{SPACE_KEY}/pages/{PAGE_ID}[/Titre]` → extraire `PAGE_ID` et `SPACE_KEY`.
  - Space root : `.../wiki/spaces/{SPACE_KEY}[/overview|/pages]` → extraire `SPACE_KEY` seulement.
  - Format court : `.../wiki/pages/viewpage.action?pageId={PAGE_ID}` → extraire `PAGE_ID`.
- Déterminer le **mode de parcours** :
  - URL page + pas de `--skip-children` → mode **descendance** (page + ses enfants récursivement).
  - URL page + `--skip-children` → mode **page unique**.
  - URL space → mode **space complet** (toutes les pages du space).

### 2. Résoudre le projet cible

Par priorité descendante :

1. **`--projet {nom}` explicite** → utiliser directement.
2. **Match du space key** : vérifier s'il match un slug existant dans `{VAULT}/_index.md` section « Projets » (insensible à la casse). Ex : space `IRIS-SYNC` → projet `iris-sync`.
3. **Titre de la page racine** : si mode page, récupérer `title` via `getConfluencePage(pageId)`, le sanitiser en slug (lowercase, espaces → `-`, caractères spéciaux retirés), vérifier match dans les projets existants.
4. **Fallback `inbox`** : si rien ne match, utiliser `inbox` et avertir explicitement l'utilisateur.

Si le projet résolu n'existe pas encore, le créer (structure `projets/{nom}/contexte.md` + `historique.md`) à l'étape 8.

### 3. Lister les pages à archiver

Selon le mode :

**Mode page unique** :
- Appeler `getConfluencePage(pageId)` avec `include_body: true`.
- Liste finale : `[page_racine]`.

**Mode descendance** :
- Appeler `getConfluencePageDescendants(pageId)` pour lister tous les descendants.
- Si `--profondeur N` est fourni, filtrer les résultats à cette profondeur max.
- Liste finale : `[page_racine] + [tous les descendants]`.

**Mode space complet** :
- Appeler `getPagesInConfluenceSpace(spaceKey)`.
- Liste finale : toutes les pages du space.

Si `--depuis YYYY-MM-DD` est fourni, filtrer la liste pour ne garder que les pages dont `lastUpdated >= {date}`.

### 4. Détecter les pages déjà archivées (idempotence)

Avant d'écrire chaque archive, lire les archives existantes dans `{VAULT}/archives/` avec frontmatter `source: archeo-atlassian` ET `confluence_page_id: {PAGE_ID}`. Pour chaque page à archiver :

- **Si aucune archive existante** → la page sera archivée (nouvelle archive).
- **Si une archive existe mais `confluence_updated` (frontmatter existant) < `lastUpdated` (valeur courante Confluence)** → la page a été modifiée depuis l'archivage. Une **nouvelle archive** sera créée (immuabilité : l'ancienne reste, la nouvelle reflète l'état actuel). Le frontmatter de la nouvelle archive référence l'ancienne via `previous_archeo: "{nom-de-l-ancien-fichier-archive}"`.
- **Si une archive existe ET `confluence_updated` == `lastUpdated`** → **skip** cette page, elle est déjà archivée à jour.

**Jamais d'écrasement d'archive vécue** (`source: vecu`) par une archive reconstituée. Si une vécue couvre le même sujet par coïncidence, les deux coexistent (types différents).

### 5. Confirmation interactive (sauf `--dry-run`)

Afficher à l'utilisateur :

```
URL analysée : {url}
Mode : {page unique | descendance | space complet}
Projet cible : {nom} ({"déjà présent" | "nouveau"})
Pages détectées : {M}
Pages à archiver : {N} (skip : {M-N} déjà à jour)
Enrichissement Jira : {activé | désactivé}

Aperçu (max 10 premières pages) :
  - {page_id} — "{titre}" — dernière modif {YYYY-MM-DD} — {état : nouvelle | mise à jour}
  - ...

{N} archives seront créées dans {VAULT}/archives/. Confirmer ? (o/n)
```

Si `--dry-run` : lister sans écrire, puis terminer.

Si refus utilisateur : arrêter sans modification.

### 6. Pour chaque page à archiver, extraire et enrichir

**6.1. Récupérer le corps de la page**

Si le corps n'a pas déjà été fetché à l'étape 3, appeler `getConfluencePage(pageId)` avec `include_body: true`. Extraire :

- `title` : titre de la page.
- `body` : corps de la page (typiquement au format `storage` — XHTML avec macros Confluence, ou `view` — HTML rendu).
- `version` : numéro de version.
- `lastUpdated` : date de dernière modification.
- `createdBy`, `createdAt` : auteur et date de création.
- `parent_id` : ID de la page parente (si non-racine).
- `space` : clé du space.

**6.2. Convertir le body en Markdown**

Le body Confluence est au format storage (XHTML custom) ou view (HTML). La conversion optimale en Markdown :

- **Si `pandoc` est disponible localement** : `pandoc -f html -t gfm` sur le body.
- **Sinon, conversion best-effort** : remplacer les balises HTML les plus courantes (`<p>`, `<h1>`-`<h6>`, `<ul>/<li>`, `<strong>`, `<em>`, `<code>`, `<pre>`, `<a>`, `<table>`) par leurs équivalents Markdown. Préserver le texte brut dans les cas non reconnus.

Enregistrer le résultat en variable `{body_md}`.

**6.3. Détecter les clés Jira référencées**

Appliquer la regex `\b([A-Z][A-Z0-9_]+-\d+)\b` sur `{body_md}` et le titre. Collecter les clés uniques (dédupliquer). Exemple : pattern `WEBUI-123`, `IRIS-42`, `GMT_SYNC-7`.

**6.4. Enrichissement Jira** (sauf `--skip-jira`)

Pour chaque clé Jira détectée :

- Appeler `getJiraIssue(key)`.
- Extraire : `summary` (titre), `status`, `assignee`, `description` (premier paragraphe uniquement, max 300 caractères), `issuetype`, `priority`, `updated`, lien vers le ticket.
- Tolérer les erreurs (ticket inexistant, accès refusé, rate limit) — noter l'erreur dans l'archive et continuer.

**6.5. Métadonnées de contexte**

- URL complète de la page.
- Chemin hiérarchique (breadcrumbs) si dispo : `{space} > {parent-of-parent} > {parent} > {current}`.
- Liste des descendants directs (si la page en a) : titres + IDs.

### 7. Écrire le fichier archive pour chaque page

Chemin : `{VAULT}/archives/YYYY-MM-DD-HHhMM-{nom}-atlassian-{slug-titre-page}.md`

Où `{slug-titre-page}` est le titre Confluence sanitisé (lowercase, espaces → `-`, caractères spéciaux retirés, max 40 chars).

Si une archive avec le même nom existe déjà (collision nom/horodatage très improbable), ajouter un suffixe `-{4-premiers-caractères-du-page-id}`.

Utiliser la date de dernière modification Confluence comme `date` et `heure` du frontmatter, pas la date courante. Ça permet que l'archive reflète le moment du jalon documenté, pas le moment de l'archivage.

Écriture via **rename atomique** (pattern 1). Pas de hash check (fichier nouveau).

Format :

```markdown
---
date: YYYY-MM-DD
heure: "HH:MM"
projet: {nom}
source: archeo-atlassian
confluence_page_id: {PAGE_ID}
confluence_page_title: "{titre}"
confluence_space: "{SPACE_KEY}"
confluence_url: "{url-complete}"
confluence_author: "{createdBy}"
confluence_created: "YYYY-MM-DD"
confluence_updated: "YYYY-MM-DD"
confluence_version: {n}
confluence_parent_id: "{PARENT_ID_or_null}"
confluence_descendants: [{liste-ids-descendants-directs}]
jira_tickets_referenced: [{liste-clés-ou-vide}]
previous_archeo: "{nom-ancien-fichier-ou-null}"
tags: [projet/{nom}, type/archive, source/archeo-atlassian]
---

# Archeo Atlassian YYYY-MM-DD — {Projet} — {Titre page Confluence}

## Résumé

[2-3 phrases reconstituant ce que la page couvre, son objet, et comment elle s'inscrit dans le projet. À déduire du titre + premier paragraphe du body + fil hiérarchique.]

## Métadonnées Confluence

- **Page** : [{titre}]({url-complete})
- **Space** : `{SPACE_KEY}`
- **ID** : `{PAGE_ID}` (version {n})
- **Auteur (création)** : {createdBy}, le YYYY-MM-DD
- **Dernière modification** : YYYY-MM-DD
- **Hiérarchie** : `{space} > {parent-of-parent} > {parent} > {current}`
- **Descendants directs** : {liste compacte avec IDs, ou "aucun"}

## Synthèse structurée

### Objet
[Ce que la page spécifie / documente / décide. Déduit du contenu.]

### Décisions et contraintes extraites
- [Décision 1]
- [Décision 2]

### Actions / TODOs mentionnés
- [ ] [Action 1]
- [ ] [Action 2]

### Glossaire (termes métier définis dans la page)
- **{terme}** : {définition}

### Questions ouvertes / zones d'incertitude
- [Question 1]

### Liens externes mentionnés (hors Jira)
- {URL} — {contexte}

## Tickets Jira référencés

{Si aucun : "Aucun ticket Jira référencé dans cette page."}

{Pour chaque ticket :}
### {JIRA-KEY} — {summary}

- **Statut** : {status} ({issuetype}, priorité {priority})
- **Assignee** : {assignee_or_"non-assigné"}
- **Mis à jour** : YYYY-MM-DD
- **Lien** : [{key}]({url})

> {premier paragraphe de la description, max 300 caractères}

## Contenu brut de la page Confluence

> [!note]- Corps Markdown de la page (déplier)
> {body_md converti en Markdown, tel que récupéré. Si très volumineux (> 10k caractères), tronquer avec mention "[contenu tronqué — voir URL Confluence pour le reste]".}

{Si previous_archeo est défini :}
## Note de révision

Cette archive supersede [{nom-ancien-fichier}](ancien.md) (page modifiée sur Confluence depuis l'archivage précédent).
```

### 8. Mettre à jour l'historique projet (batch)

Collecter toutes les lignes à ajouter à `{VAULT}/projets/{nom}/historique.md` :

```
- [YYYY-MM-DD — Atlassian : {Titre page}](../../archives/YYYY-MM-DD-HHhMM-{nom}-atlassian-{slug}.md)
```

**Un seul read-before-write** pour toutes les lignes (pas N écritures). Hash check + rename atomique.

Si `historique.md` n'existe pas (projet nouveau), créer le squelette standard avant d'ajouter les lignes.

### 9. Mettre à jour l'index global (batch)

Collecter toutes les lignes à ajouter à la section **Archives** de `{VAULT}/_index.md` :

```
- [YYYY-MM-DD — {Projet} — Atlassian : {Titre page}](archives/YYYY-MM-DD-HHhMM-{nom}-atlassian-{slug}.md)
```

Si c'est la première archive du projet, ajouter aussi dans la section **Projets** :

```
- [{Projet}](projets/{nom}/historique.md)
```

**Un seul read-before-write** + rename atomique. Merger en conservant l'ordre chronologique ascendant existant.

### 10. Enrichir le contexte projet (projet nouveau uniquement)

Si le projet a été **créé à cette archéologie** (aucun `contexte.md` préexistant), pré-remplir `{VAULT}/projets/{nom}/contexte.md` avec une synthèse dérivée des pages archivées :

- Phase : « reconstituée via archéo Atlassian le YYYY-MM-DD — pas de session vécue encore ».
- Décisions cumulées : agréger les décisions extraites des différentes pages.
- Assets actifs (URLs) : liste des URLs Confluence des pages archivées + tickets Jira les plus référencés.

Si le projet existait déjà : **ne pas écraser** `contexte.md`. Afficher : « Contexte actuel conservé. Les archives Atlassian enrichissent l'historique, pas le snapshot mutable. Utilise `/mem-recall {nom}` + édition manuelle pour intégrer des éléments. »

### 11. Confirmer

Afficher à l'utilisateur :

```
Archéologie Atlassian terminée pour le projet {nom}.

URL racine : {url}
Pages archivées : {N} (sur {M} détectées)
Tickets Jira enrichis : {K} unique(s)
Plage couverte : {date-plus-ancienne} → {date-plus-recente} (par `confluence_updated`)

Nouvelles archives dans {VAULT}/archives/ (préfixe `{YYYY-MM-DD-HHhMM-{nom}-atlassian-*}`).
Historique : {VAULT}/projets/{nom}/historique.md

Prochaine étape suggérée : ouvrir l'historique dans Obsidian, ou /mem-recall {nom} pour charger le contexte reconstitué.
```

Si des erreurs sont survenues (tickets Jira inaccessibles, pages en erreur) : en lister un résumé à la fin.
