# Procédure : Promote Domain (nouveau v0.5)

Objectif : promouvoir un ensemble d'items cohérents de `00-inbox/` (ou items dispersés dans le vault) en un nouveau **domaine permanent** dans `10-episodes/domaines/{slug}/`. Vérifie la règle anti-dérive (≥ 3 items au même fil).

Cas d'usage typique : tu as accumulé en inbox 3-4 notes sur ta santé qui ne rentrent dans aucun projet. Au lieu de créer un faux projet `sante`, tu les promeus en domaine permanent.

## Déclenchement

L'utilisateur tape `/mem-promote-domain {slug-cible} [items]` ou exprime l'intention en langage naturel : « crée un domaine santé », « promeus ces 3 notes en domaine », « regroupe ce fil en domaine ».

Arguments :
- `{slug-cible}` (**obligatoire**) : slug du nouveau domaine à créer.
- `{items}` (optionnel, multi-valué) : chemins des items à promouvoir. Si absent, demander à l'utilisateur la liste.
- `--scope perso|pro` : scope du domaine. Défaut : `default_scope` du `memory-kit.json`.
- `--from-inbox` : promouvoir tous les items de l'inbox qui matchent un mot-clé (à fournir).
- `--dry-run` : affiche le plan sans appliquer.
- `--no-confirm` : applique sans confirmation.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault` et `default_scope`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Vérifier l'unicité du slug

Vérifier que `{VAULT}/10-episodes/domaines/{slug-cible}/` n'existe pas déjà. Vérifier aussi qu'il n'y a pas de projet du même slug (collision sémantique).

Si conflit, arrêter avec message clair.

### 2. Énumérer les items à promouvoir

- Si `{items}` fourni : liste explicite.
- Si `--from-inbox {keyword}` : grep dans `00-inbox/` pour les fichiers contenant le mot-clé.
- Sinon : demander à l'utilisateur (le router peut suggérer en lisant l'inbox).

### 3. Vérifier la règle anti-dérive (≥ 3 items)

Si moins de 3 items à promouvoir, afficher :

> Règle anti-dérive : un domaine ne se crée qu'à partir d'au moins 3 archives au même fil. Tu en as {N}.
> Recommandation : laisse encore en inbox jusqu'à atteindre 3 items, ou rattache à un domaine existant.

Permettre à l'utilisateur de bypasser explicitement avec `--force` (bool, à ajouter en option si besoin).

### 4. Présenter le plan

Format :

```
## Promotion de domaine — {slug-cible}

Scope : {perso|pro}

Items à promouvoir ({N}) :
  - {chemin item 1} → 10-episodes/domaines/{slug}/archives/{nom}.md
  - {chemin item 2} → ...
  - ...

Structure créée :
  10-episodes/domaines/{slug-cible}/
    contexte.md (squelette)
    historique.md (squelette)
    archives/ (avec items déplacés)

Continuer ? [o/n]
```

Si `--dry-run` : s'arrêter ici.

### 5. Appliquer (si confirmé ou `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Étapes :

1. **Créer la structure** : `mkdir -p 10-episodes/domaines/{slug-cible}/archives/`.
2. **Créer `contexte.md`** squelette :
   ```yaml
   ---
   zone: episodes
   kind: domaine
   slug: {slug-cible}
   scope: {scope}
   collectif: false
   tags: [zone/episodes, kind/domaine, domaine/{slug-cible}, scope/*]
   ---

   # {slug-cible} — Contexte actif

   ## État courant
   Domaine permanent créé le YYYY-MM-DD à partir de {N} items.

   ## Décisions cumulées
   (à enrichir au fil des sessions)

   ## Prochaines étapes
   (à définir)
   ```
3. **Créer `historique.md`** squelette : titre + N entrées initiales pour les items promus.
4. **Pour chaque item à promouvoir** :
   - Lire son frontmatter actuel.
   - Mettre à jour : `zone: episodes`, `kind: domaine`, `domaine: {slug-cible}`, ajouter tags `zone/episodes`, `kind/domaine`, `domaine/{slug-cible}`.
   - Si la date du fichier n'est pas explicite, la dériver de la date de création FS.
   - Renommer le fichier en `YYYY-MM-DD-HHhMM-{slug-cible}-{ancien-titre-court}.md`.
   - Déplacer vers `10-episodes/domaines/{slug-cible}/archives/`.
   - Pattern 1 (rename atomique).
5. **Mettre à jour `99-meta/_index.md`** : ajouter le domaine en section Domaines.
6. **Pour chaque item promu** : ajouter une ligne dans `historique.md` du nouveau domaine.

### 6. Confirmer

Format :

```
Domaine créé : {slug-cible} ({scope})
{N} items promus depuis l'inbox / autres zones.
Index mis à jour.

Pour ajouter de nouvelles archives à ce domaine : /mem-archive --domaine {slug-cible}
```
