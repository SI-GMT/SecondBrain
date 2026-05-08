# Doctrine binding : architecture archeo v2 — shell-delegated, deterministic, scope-bounded

> Doctrine binding (cf. `_when-to-script`, `_archived`, `_linking`, `_mcp-first`, `_frontmatter-archeo`). Référencée par `mem-archeo.md`, `mem-archeo-context.md`, `mem-archeo-stack.md`, `mem-archeo-git.md`. Source de vérité pour la refonte de la chaîne archeo après le retour terrain v0.10.x (timeouts MCP sur grosse codebase IRIS USER, pilote de la refonte).

## Pourquoi cette refonte

L'architecture v1 (en place jusqu'à v0.10.x inclus) souffre de trois défauts mutuellement amplifiants :

1. **Phase 0 récursive en Python** (`vault.topology_scanner.scan()`) sur de gros repos dépasse le timeout MCP du client (60–120 s typiques). Le LLM voit `MCP ERROR (secondbrain-memory-kit)` sans diagnostic clair et finit par re-tenter manuellement les phases suivantes — qui dépendent toutes de la sortie de Phase 0.
2. **Branch-first heuristique** (« commits uniques à la branche ») confond le périmètre d'analyse avec la chronologie Git. Sur une branche fully merged, `merge-base == HEAD(branch)` → 0 commits uniques, alors que les fichiers modifiés sur la branche existent toujours.
3. **Scope implicite et large par défaut** : Phase 0 scanne tout, Phase 1 reçoit un graphe complet et doit filtrer mentalement. Aucun mécanisme de batching ni de cap dur — le LLM peut surcharger sa propre fenêtre de contexte.

L'architecture v2 répond à ces trois défauts par trois principes structurels couplés.

## Principe 1 — Délégation au système, pas au LLM

Toute énumération de fichiers (récursive ou plate) doit être déléguée à un programme natif, pas implémentée comme une boucle Python interprétée et encore moins « simulée » par le LLM via des appels d'outils en cascade. La récursivité est un travail de système d'exploitation et de Git ; ni le LLM ni le serveur MCP n'ont à la réinventer.

Deux modes coexistent, détectés automatiquement au démarrage de Phase 0 par la présence du dossier `.git/` à la racine du repo :

- **Mode `git`** (`(repo_path / ".git").exists()`) : utiliser exclusivement le binaire `git` via `subprocess.run`. Commandes canoniques :
  - `git ls-files` — inventaire complet des fichiers tracés (gitignore-aware par construction, tri stable, output streamable).
  - `git diff --name-only <base>..HEAD` — fichiers modifiés sur la branche par rapport à `<base>`.
  - `git log --name-only --pretty="" <base>..HEAD` — fichiers touchés par tout commit unique à la branche.
  - `git merge-base <main> HEAD` — point de divergence (avec fallback first-parent si fully merged, déjà géré par la stratégie A de v0.10.0 archeo-git).
- **Mode `raw`** (pas de `.git/`) : utiliser `os.scandir` récursif Python (stdlib, pas de dépendance externe) avec une ignore-list par défaut **non négociable** : `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `dist`, `build`, `.next`, `target`, `.tox`, `.pytest_cache`, `*.pyc`, `*.pyo`, `*.egg-info`. L'utilisateur peut **ajouter** des patterns d'exclusion via paramètre, **jamais retirer** ceux par défaut.

L'output des deux modes converge vers un type uniforme `list[PurePosixPath]` (chemins relatifs au repo, normalisés POSIX même sous Windows). Phase 1, 2, 3 consomment cette liste sans savoir d'où elle vient.

## Principe 2 — Branch-first déterministe en deux passes

L'analyse contextuelle d'une branche se définit par les **fichiers** qu'elle touche, pas par les commits. La granularité commit reste pertinente pour mem-archeo-git Phase 3 (chronologie historique), mais Phase 1 contexte travaille sur des fichiers.

### Pass A — primaire, déterministe, close

L'ensemble des fichiers à analyser pour le contexte d'une branche est défini exhaustivement par :

```
files_pass_A = (
    git diff --name-only <base>..HEAD
    ∪ git log --name-only --pretty="" <base>..HEAD
)
```

Cette union capture à la fois les fichiers actuellement différents de `base` (diff statique) et les fichiers touchés par tout commit intermédiaire de la branche (y compris ceux qui auraient été créés puis supprimés, ou réécrits via squash). La liste est close, ordonnée, hashable — elle peut être persistée dans le frontmatter de l'atome topo et réutilisée à l'identique par Phase 1, 2, 3.

`<base>` est résolu selon la hiérarchie suivante. **La stratégie historique « first-parent fallback » est retirée** (case study Codex sur `ecosav` du repo IRIS USER : la branche absorbée + ancienne avait son first-parent qui remontait à 1296 commits hors périmètre fonctionnel — dérive sémantique sur master). Toute fonctionnalité Git qui ramène à la branche de base est désormais bannie comme stratégie de résolution.

- **Range strict** : `git merge-base <base> <branch>` retourne un SHA distinct de `HEAD(branch)`. La branche n'est pas fully merged → le diff `merge_base..branch` capture les commits propres. Mode = `range-strict`.

- **Auto-scope par nommage** _(défaut quand range strict vide)_ : si la branche est fully merged dans `<base>`, le scope est dérivé du **nom de la branche** via une heuristique repo-wide. Variantes générées (`ecosav` → `EcoSAV`, `ecosav`, `eco-sav`, `ecoSav`, `ECOSAV`, et préfixes git-flow strippés `feat/X` → `X`) puis match contre les dossiers du repo. Plus le match est profond, plus il est spécifique. Si plusieurs candidats, on garde le plus profond ; si zéro candidat, voir « refus ferme » ci-dessous. Mode = `auto-scope-by-name`.

- **`by_files` explicite** : l'utilisateur force `by_files=True`. Le scope est dérivé via `git log --first-parent --diff-filter=A --name-only` sur `merge_base..branch` (les fichiers introduits par la branche). Quand le diff est vide, l'heuristique nommage est utilisée comme fallback. Mode = `by-files`.

- **Anchor explicite** : `since_sha` / `since_date` / `scope_glob` fournis par l'utilisateur. Bypasse toute auto-détection. Mode = `since-sha`, `since-date`, ou `manual`.

- **Refus ferme** : si la branche est fully merged ET que l'heuristique nommage ne retourne aucun match dossier ET aucun anchor explicite n'est fourni → erreur `BranchScopeUnresolvedError` avec hint :

  ```
  BranchScopeUnresolvedError: branch '<branch>' is fully merged into '<base>' and the
  name does not match any directory in the repo. Provide one of:
    - scope_glob='<glob>'                 (e.g. 'src/Module/**')
    - since_sha=<sha>                     (commit before the branch's specialisation)
    - since_date=YYYY-MM-DD               (date floor)
  Auto-scope by name tried variants: <variants_attempted>.
  ```

  Aucun fallback ne dérive sur `<base>`. Le LLM (ou l'utilisateur) doit décider explicitement le périmètre.

Le tableau historique « stratégies A/B/C v0.10.0 » est invalidé par cet amendement. Les atomes archives créés par l'ancienne stratégie A persistent (pas d'invalidation rétroactive) ; un commentaire dans leur frontmatter `merge_base_strategy: first-parent-fallback` permet de les identifier pour reprocessing manuel si besoin.

### Pass B — secondaire, opt-in, language-aware

Les fichiers importés, étendus ou inclus depuis Pass A peuvent être ramenés dans le périmètre via une seconde passe explicite, opt-in (jamais par défaut) :

- Python : `^\s*from\s+(\S+)\s+import` et `^\s*import\s+(\S+)` regex sur les fichiers Pass A, résolution des modules en chemins relatifs au repo.
- JavaScript/TypeScript : `^\s*import\s+.+\s+from\s+['"](\S+)['"]` et `^\s*const\s+\S+\s*=\s*require\(['"](\S+)['"]\)`.
- C# / Java / autre : extension future, désactivé par défaut.

Pass B est **batch-séparable** : un seul appel `mem_archeo_context_pass_b(files_pass_a)` retourne `files_pass_b` sans bloquer le reste du flux. Si l'utilisateur veut une analyse de surface seule, il s'arrête à Pass A.

### Mode raw — Pass A dégradé

Sans Git, Pass A n'a pas de définition canonique (« fichiers modifiés sur la branche » n'existe pas). Comportement par défaut : Pass A = tous les fichiers retournés par `os.scandir` filtrés par l'ignore-list. L'utilisateur **doit** alors fournir un `scope_glob` explicite ou accepter un cap dur (cf. principe 3) sous peine de refus.

## Principe 3 — Scope tight et batch obligatoire au-delà du seuil

Aucune phase archeo ne doit charger plus que strictement nécessaire. Trois mécanismes complémentaires :

### 3.1 Paramètre `scope_glob`

Tous les outils archeo (`mem_archeo`, `mem_archeo_context`, `mem_archeo_stack`, `mem_archeo_git`) acceptent un paramètre `scope_glob: str | None = None`. Format glob POSIX (`src/api/**/*.py`, `docs/**`, `tests/integration/**`). Évalué côté wrapper après énumération brute, avant Pass A.

Lorsque le scope est fourni, l'atome topo persiste le glob littéral dans `scope_glob` (frontmatter). Les phases suivantes lisent le scope depuis le snapshot, jamais depuis les arguments d'invocation — garantit la cohérence entre phases.

### 3.2 Soft caps configurables, alerte plutôt qu'abort

Seuils par défaut, applicables aux deux modes (git et raw) :

```python
SOFT_CAP_FILES_DEFAULT = 500
SOFT_CAP_BYTES_DEFAULT = 50 * 1024 * 1024  # 50 MiB
BATCH_SIZE_DEFAULT     = 200
```

Comportement par défaut quand le scope dépasse un seuil — **alerte non-bloquante** :

- Phase 0 produit quand même la liste complète et l'atome topo, sans tronquer.
- Un finding `ScopeOverflowWarning` est ajouté à la sortie de l'outil (champ `warnings: list[str]` du résultat MCP) :

```
ScopeOverflowWarning: 1247 files / 87 MiB matched (soft cap: 500 / 50 MiB).
Continuing without truncation. Recommended next step: split into batches
of <batch_size=200> via mem_archeo_index_files + per-batch mem_archeo_context calls.
Suggested first batch: <first 200 file paths>.
```

- Phase 1/2/3 voient l'avertissement dans le snapshot et peuvent décider de batcher elles-mêmes ou de continuer en monolithe (responsabilité LLM).

Trois paramètres exposés sur tous les outils archeo, par ordre de priorité décroissante :

| Paramètre        | Type        | Effet                                                             |
|------------------|-------------|-------------------------------------------------------------------|
| `max_files`      | `int | None`| Soft cap fichiers. `None` = défaut. `0` = pas de cap.             |
| `max_bytes`      | `int | None`| Soft cap taille cumulée. `None` = défaut. `0` = pas de cap.       |
| `batch_size`    | `int | None`| Taille suggérée par lot dans l'alerte. `None` = défaut. Informationnel — n'est pas appliqué automatiquement par Phase 0, sert à orienter la suggestion. |
| `hard_abort`    | `bool`      | Si `True`, transforme la soft cap en hard cap (abort + erreur). Défaut `False`. |

L'utilisateur a donc trois leviers : laisser passer (défaut + warn), élargir explicitement les seuils (`max_files=2000`), forcer le refus (`hard_abort=True`). Aucune décision de troncature implicite — la liste complète est toujours soit produite intégralement, soit refusée explicitement.

### 3.3 Outil `mem_archeo_index_files`

Nouvel outil MCP léger qui retourne **uniquement la liste de fichiers** à traiter pour un repo + paramètres donnés, sans analyse contextuelle, sans parsing AST, sans Phase 1/2/3. Signature :

```python
def mem_archeo_index_files(
    project: str,
    repo_path: str,
    branch: str | None = None,
    scope_glob: str | None = None,
    pass_b: bool = False,
    max_files: int | None = None,
    max_bytes: int | None = None,
    batch_size: int | None = None,
    hard_abort: bool = False,
) -> ArcheoIndexResult:
    """List of files Phase 1+ will analyse, with mode/scope/caps applied.

    When the scope exceeds soft caps, the result includes both the full
    file list and a pre-computed batch slicing (list of list[Path] of
    batch_size each) for downstream phases to consume directly.
    """
```

Le retour expose toujours :

- `files: list[PurePosixPath]` — liste complète (jamais tronquée sans `hard_abort=True`).
- `files_count`, `files_bytes`.
- `warnings: list[str]` — `ScopeOverflowWarning` formaté si dépassement.
- `batches: list[list[PurePosixPath]]` — découpage pré-calculé par paquets de `batch_size`. Présent même sous le cap (un seul batch = la liste entière) pour donner au LLM un contrat uniforme.

Cela permet au LLM (ou à l'utilisateur via `/mem-archeo-index-files`) de **prévisualiser le scope** avant de lancer une vraie archeo, et soit de consommer la liste en monolithe, soit d'itérer sur `batches` :

```
> mem_archeo_index_files(project="iris-user", repo_path="...", scope_glob="src/**", batch_size=150)
→ 1247 files (87 MiB), 9 batches of <=150
→ warning: ScopeOverflowWarning(1247 / 87 MiB)
> for batch in result.batches:
>     mem_archeo_context(..., file_list_override=batch)
```

Le batch est une décision LLM, pas un automatisme — la doctrine fournit le découpage prêt à consommer, mais c'est le LLM qui choisit de l'appliquer ou non.

## Topo persistée avant analyse contextuelle

Phase 0 écrit immédiatement un atome topo au format suivant **dès qu'elle a la liste de fichiers**, avant toute Phase 1/2/3 :

```yaml
---
project: <slug>
zone: meta
kind: repo-topology
slug: <slug>
display: <slug> — repo topology
source: archeo-topology
source_mode: git | raw    # principe 1
scope_glob: <glob | null> # principe 3.1
files_count: <int>
files_bytes: <int>
branch: <branch-name | null>
base_ref: <sha | null>    # mode git seulement
merge_base_strategy: auto-first-parent | by-files | since-sha | since-date | null
files_hash: <sha256>      # hash de la liste triée pour déduplication
generated_at: <iso8601>
---

## Inventaire

<list of files, posix-relative, one per line>

## Métadonnées par fichier (optionnel, mode git)

<file>: <bytes> — touched in <N> commits — last <iso8601>
```

Les phases suivantes **lisent ce snapshot** plutôt que de relancer un scan. Le `files_hash` permet de détecter une dérive entre Phase 0 et Phase N (un fichier qui apparaîtrait/disparaîtrait entre temps invalide la cohérence de la chaîne).

## Frontmatter conditionnel par `source_mode`

`_frontmatter-archeo.md` doit être amendé pour rendre les champs Git-spécifiques optionnels selon `source_mode` :

| Champ                         | Mode `git` | Mode `raw`     |
|-------------------------------|------------|----------------|
| `branch`                      | requis     | absent         |
| `base_ref`                    | requis     | absent         |
| `merge_base_strategy`         | requis     | absent         |
| `git_commit_range`            | requis     | absent         |
| `source_mode`                 | requis     | requis         |
| `scope_glob`                  | optionnel  | requis si non-trivial |
| `files_count` / `files_bytes` | requis     | requis         |
| `files_hash`                  | requis     | requis         |

Une catégorie health-scan dédiée (proposition `archeo-mode-frontmatter-mismatch`) flag les atomes archeo dont le frontmatter ne respecte pas le mapping ci-dessus.

## Fallback CLI standalone

Phase 0 doit être disponible **hors MCP** via une CLI dédiée :

```
python -m memory_kit_mcp.archeo_topology --repo <path> [--branch <name>] [--scope-glob <glob>] [--pass-b] [--out <atom-path>]
```

Cas d'usage :

- L'utilisateur a un repo trop gros pour le timeout MCP de son CLI client (cas IRIS USER avec Gemini).
- Un CI/CD veut générer la topo sans démarrer de serveur MCP.
- Un test d'intégration veut isoler Phase 0.

L'output est un atome `repo-topology` (même format que la version MCP), écrit sur stdout par défaut ou dans le fichier passé via `--out`. Le LLM peut ensuite l'attacher au vault via `mem_attach_topology(atom_path)` (nouvel outil MCP, signature : prend le chemin, valide le format, copie dans `99-meta/repo-topology/<slug>.md`).

Cette CLI est versionnée comme un script standalone (`scripts/archeo-topology.py`) selon la doctrine `_when-to-script.md`, **avec sa propre copie de la logique** pour préserver l'usage standalone sans `pip install memory-kit-mcp` (paire cohérence de type 4 — comme `scripts/doc-readers/*` ↔ `memory_kit_mcp.readers.*`).

## Migration depuis v1

L'architecture v2 ne casse pas la v1 — elle la remplace progressivement :

1. **Phase 0** : refonte en premier (POC sur IRIS USER). `vault.topology_scanner.scan()` v1 reste accessible derrière un flag `legacy_scan: bool = False` pour compatibilité ascendante pendant la transition.
2. **Phase 1 contexte** : la v1 (skills-only stub) ne change pas tant que le port Phase 1 Python n'est pas démarré. Quand il le sera, il consommera directement la liste Pass A produite par Phase 0 v2.
3. **Phase 2 stack** : déjà déterministe (lecture des manifestes), refonte mineure pour passer par la liste Pass A au lieu de re-scanner.
4. **Phase 3 git** : déjà branch-first hardened en v0.10.0, à ré-aligner sur la définition Pass A (les commits uniques deviennent un dérivé de la liste files Pass A, plus l'inverse).

La paire cohérence #1 (`core/procedures/mem-X.md` ↔ `tools/X.py`) reste la garantie : tout changement v2 dans une procédure doit s'accompagner du changement Python correspondant dans le même commit, suivi de `python -m memory_kit_mcp.sync update`.

## Validation cible

L'architecture v2 est validée empiriquement quand :

1. `mem_archeo_index_files` retourne en < 2 s sur IRIS USER (gros repo, mode git).
2. `mem_archeo_context` sur Pass A d'une branche IRIS USER ne timeout pas côté client MCP (Gemini ou Claude Code).
3. `mem_archeo` sur un dossier raw (pas de `.git`) produit un atome topo + Phase 2 cohérent sans crash.
4. La CLI standalone `python -m memory_kit_mcp.archeo_topology` produit un atome identique (au timestamp près) à celui généré par l'outil MCP sur le même repo.
5. Le health-scan flag tout atome archeo dont `source_mode` est absent ou incohérent avec les autres champs.
