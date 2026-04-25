# Procédure : Doc (v0.5 brain-centric)

Objectif : ingérer **un document local** (PDF, Markdown, texte, image, docx, etc.) dans le vault mémoire avec synthèse structurée et copie préservée du fichier source. Le router classe le contenu selon sa nature (épisodique, sémantique, procédural...).

Complémentaire de `/mem-archive` (session vécue) et `/mem-archeo*` (reconstruction Git/Confluence). `/mem-doc` couvre le cas du document qui traîne sur le disque : SFD reçu par mail, spec Word sur NAS, présentation kickoff, PDF scanné, etc.

## Déclenchement

L'utilisateur tape `/mem-doc {chemin}` ou exprime l'intention en langage naturel : « ingère ce document », « archive ce fichier », « enregistre ce PDF ».

Arguments :
- `{chemin}` (**obligatoire**) : chemin absolu ou relatif du fichier à ingérer.
- `--projet {slug}` ou `--domaine {slug}` (optionnel) : force le rattachement.
- `--zone X` (optionnel) : force la zone cible (par défaut, le router décide selon la nature du contenu — un PDF de spec va en `20-knowledge/`, un compte-rendu de réunion en `10-episodes/`).
- `--titre "{texte}"` (optionnel) : titre court pour l'archive.
- `--no-confirm`, `--dry-run` : passe au router.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault` et `default_scope`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Valider le chemin source

- Vérifier que `{chemin}` existe et est un fichier (pas un dossier).
- Calculer la taille en octets.
- Si > 50 Mo, demander confirmation.
- Déterminer le type via extension :
  - `.md`, `.txt` → texte natif.
  - `.pdf` → extraction via outil natif LLM (en v0.5.1 : `scripts/doc-readers/read_pdf.py`).
  - `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` → description vision LLM.
  - `.docx`, `.pptx`, `.xlsx`, `.odt`, `.html`, `.htm` → v0.5.1 (doc-readers Python).
  - Autre → tenter UTF-8, sinon arrêter avec message explicite.

### 2. Calculer le hash SHA-256 et détecter re-ingestion

- SHA-256 du fichier en mode binaire.
- Chercher dans le vault un atome existant avec `source_hash` égal. Si trouvé, demander confirmation à l'utilisateur (« Déjà ingéré le {date} dans `{archive}`. Ré-ingérer ? »).

### 3. Copier le fichier source

Chemin destination : `{VAULT}/99-meta/sources/{YYYY-MM}/{hash8}-{nom-original}.{ext}`

Note : en v0.5, les sources sont conservées dans `99-meta/sources/` (et non plus `archives/_sources/` qui n'existe plus). Idempotent : si la copie existe déjà, skip.

Créer `{VAULT}/99-meta/sources/.gitignore` au premier usage avec le pattern d'exclusion des binaires lourds.

### 4. Extraire le contenu et préformater

Extraire le contenu textuel du fichier (selon le type). Préformater pour le router :

- Le contenu est passé tel quel.
- Si la nature est ambiguë, le router décidera de la zone.
- Si l'utilisateur a passé `--zone X`, le router force la zone.

### 5. Invoquer le router avec hint source forcée

Appeler le router avec :
- `Contenu` : contenu extrait du document.
- `Hint zone` : valeur de `--zone` si fournie, sinon laisser le router décider.
- `Hint source` : `doc`.
- `Métadonnées` : projet/domaine résolu, scope, **`source_hash`**, **`source_path`** (chemin original), **`source_copy`** (chemin de la copie dans 99-meta/sources/), **`source_size_bytes`**.

{{INCLUDE _router}}

Le router ajoute au frontmatter de chaque atome créé :
- `source: doc`
- `source_hash`, `source_path`, `source_copy`, `source_size_bytes`
- `source_type` (extension du fichier)

### 6. Confirmer

Le router produit son rapport. Mentionner explicitement : « Fichier source copié dans `{copie}`, hash `{hash8}...`. Ré-ingestion idempotente. »
