# Procédure : Mem (router universel — nouveau v0.5)

Objectif : ingestion zéro-friction d'un contenu libre dans le vault. Le router sémantique segmente, classe et écrit dans la(les) bonne(s) zone(s) sans que l'utilisateur ait à réfléchir au classement.

C'est le **chemin par défaut** pour 80 % des cas d'ingestion. Les skills spécialisés (`mem-archive`, `mem-note`, `mem-principle`, `mem-goal`, `mem-person`, `mem-doc`, `mem-archeo*`) sont des shortcuts qui forcent une zone spécifique.

## Déclenchement

L'utilisateur tape `/mem {contenu}` ou exprime l'intention en langage naturel : « note ceci », « enregistre », « capture ça », « ajoute à la mémoire ».

Options reconnues :
- `--scope perso|pro` : force le scope. Défaut : `default_scope` du `memory-kit.json`.
- `--zone X` : force la zone (équivalent à invoquer le skill spécialisé). Bypass de la cascade d'heuristiques.
- `--projet {slug}` ou `--domaine {slug}` : force le rattachement épisodique.
- `--no-confirm` : force le mode fluide même sur multi-atomes.
- `--dry-run` : affiche le plan sans écrire.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire les champs `vault` et `default_scope`. Dans la suite, `{VAULT}` désigne la valeur du vault.

Si le fichier est absent ou illisible, répondre :
> Kit mémoire non configuré. Fichier attendu : {{CONFIG_FILE}}. Exécute `deploy.ps1` depuis la racine du kit.

Puis s'arrêter.

## Procédure

### 1. Préformatage par l'adapter

L'adapter (Claude Code, Gemini CLI, Codex, Vibe) a déjà :
- Normalisé fins de ligne (LF) et encodage (UTF-8 sans BOM).
- Injecté le contexte d'invocation : projet courant (CWD), branche Git, scope par défaut.
- Pré-annoté les indices de scope si évidents.

### 2. Invoquer le router

Passer au router le contenu, sans hint de zone (sauf si `--zone X` fourni). Laisser le router décider de la segmentation, du classement, de l'écriture.

{{INCLUDE _router}}

### 3. Rapport

Le router produit son propre rapport (cf. R9 du bloc router). Aucune action supplémentaire de la procédure `mem`.

---

Arguments à parser : le contenu est tout ce qui suit `/mem` (ou la phrase naturelle). Les options `--xxx` sont extraites avant invocation du router.
