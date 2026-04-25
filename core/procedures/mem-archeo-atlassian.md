# Procédure : Archeo Atlassian (v0.5 brain-centric)

Objectif : **rétro-archiver une arborescence Confluence** (page racine + descendance, ou space complet) avec enrichissement par les tickets Jira référencés. Délègue au router pour segmentation en atomes multi-zones.

**Prérequis : MCP Atlassian côté client.** Claude-only de facto (Atlassian n'a pas livré de connecteur MCP digne de ce nom pour Gemini/Codex/Vibe à ce jour). Si invoqué depuis un client sans MCP Atlassian, afficher un message clair et arrêter.

## Déclenchement

L'utilisateur tape `/mem-archeo-atlassian {url-confluence}` ou exprime l'intention en langage naturel : « archive cette page Confluence et ses enfants », « rétro Atlassian sur cet espace », « ingère cette doc Confluence ».

Arguments :
- `{url-confluence}` (**obligatoire**) : URL d'une page ou d'un space Confluence.
- `--projet {slug}` ou `--domaine {slug}` : force le rattachement.
- `--profondeur N` : limite la descendance (défaut illimité).
- `--skip-children` : ingère uniquement la page racine.
- `--depuis YYYY-MM-DD` : ne traite que les pages mises à jour après cette date.
- `--skip-jira` : désactive l'enrichissement par tickets Jira.
- `--dry-run` : liste les pages traitées sans écrire.
- `--no-confirm` : passe au router en mode fluide.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault` et `default_scope`. Si absent, message d'erreur standard et arrêt.

## Vérification du MCP Atlassian

Avant tout traitement, vérifier la disponibilité du MCP Atlassian côté client. Si indisponible, afficher :

> Skill `/mem-archeo-atlassian` indisponible : MCP Atlassian non détecté.
> Ce skill nécessite le connecteur MCP Atlassian, actuellement uniquement disponible côté Claude (Desktop / Code). Voir la documentation Atlassian pour l'installation.

Puis arrêter.

## Procédure

### 1. Identifier le scope (page seule, page+descendance, space)

Parser l'URL pour extraire :
- `space_key`
- `page_id` (si URL pointe sur une page) ou `null` (si URL pointe sur un space root).

Mode :
- URL = page + pas `--skip-children` → page + descendance.
- URL = page + `--skip-children` → page seule.
- URL = space root → space complet.

### 2. Énumérer les pages à traiter

Via le MCP Atlassian, lister les pages :
- Page seule : 1 page.
- Page + descendance : page racine + récursion via `child_of` jusqu'à `--profondeur` ou exhaustion.
- Space : `pages_by_space` complet.

Filtrer par `--depuis` si fourni (`updated_at >= depuis`).

### 3. Résoudre le projet/domaine cible

Identique à `mem-archeo` étape 2.

### 4. Pour chaque page : préparer le contenu

#### a. Vérifier idempotence

Chercher dans le vault un atome existant avec :
- `source: archeo-atlassian`
- `confluence_page_id` égal.
- `confluence_updated` égal.

Si trouvé → skip.
Si trouvé mais `confluence_updated` différent → créer une nouvelle archive avec `previous_atom: [[ancien]]` (immuabilité).

#### b. Récupérer le contenu de la page

Via MCP Atlassian, récupérer :
- Titre, body (Markdown ou storage format converti en MD), auteur, date de création/màj.
- Labels, espace.
- Liens entrants / sortants.

#### c. Enrichissement Jira (si pas `--skip-jira`)

Extraire les clés Jira (regex `[A-Z]+-\d+`) du contenu de la page. Pour chaque clé :
- Via MCP Atlassian, récupérer : titre du ticket, statut, assigné, sprint, type.
- Insérer une mention enrichie dans le contenu de l'atome.

#### d. Construire le contenu pour le router

Préparer un Markdown structuré, similaire à `mem-archeo` :

```
# Archive page Confluence — {titre}

[Contenu de la page, source: confluence]

## Principe : ... [si dégagé du contenu]
## Concept : ... [si dégagé du contenu]
```

### 5. Invoquer le router pour cette page

Appeler le router avec :
- `Contenu` : Markdown structuré.
- `Hint zone` : `episodes` (par défaut, mais le router peut router certaines pages doctrinales en `20-knowledge` selon nature).
- `Hint source` : `archeo-atlassian`.
- `Métadonnées` : projet/domaine, **`confluence_page_id`**, **`confluence_updated`**, `confluence_url`, `space_key`, `jira_keys: [...]`.

{{INCLUDE _router}}

### 6. Boucle sur toutes les pages

Si `--dry-run` : afficher la liste des pages + atomes prévus. Demander confirmation.

Sinon : itérer. Mode safe par défaut sauf `--no-confirm`.

### 7. Rapport final

Synthèse : N pages traitées, N archives créées, N atomes dérivés, N skips (idempotence), N révisions, N tickets Jira enrichis.
