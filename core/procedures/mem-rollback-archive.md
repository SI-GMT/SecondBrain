# Procédure : Rollback Archive (v0.5 brain-centric)

Objectif : annuler la dernière archive d'un projet/domaine (ou du vault global). Supprime le fichier archive **ET ses atomes dérivés** (chaîne via `derived_atoms`). Demande confirmation si des atomes dérivés vont être orphelinisés.

**Limite connue** : le `contexte.md` du projet/domaine est **écrasé** à chaque archive complet. Le rollback ne restaure **pas automatiquement** l'ancien `contexte.md` — l'utilisateur peut relancer `/mem-recall {slug}` pour régénérer un contexte à partir de l'avant-dernière archive.

## Déclenchement

L'utilisateur tape `/mem-rollback-archive [{slug}]` ou exprime l'intention en langage naturel : « annule la dernière archive », « oublie la dernière session », « rollback l'archive de X ».

Arguments :
- `{slug}` (optionnel) : slug du projet/domaine. Si absent, rollback la dernière archive globale du vault (toutes zones confondues).
- `--with-derived` : supprime aussi les atomes dérivés (par défaut, demande confirmation).
- `--no-confirm` : applique sans confirmation.

## Résolution du chemin du vault

Lire {{CONFIG_FILE}} et en extraire `vault`. Si absent, message d'erreur standard et arrêt.

## Procédure

### 1. Identifier l'archive à supprimer

- Si `{slug}` fourni : lire `{VAULT}/10-episodes/{kind}/{slug}/historique.md`, prendre la dernière entrée d'archive.
- Sinon : scanner les `historique.md` de tous les projets et domaines, trouver l'archive la plus récente du vault.

Si aucune archive trouvée : afficher « Aucune archive à annuler. » et arrêter.

### 2. Identifier les atomes dérivés

Lire le frontmatter de l'archive cible. Extraire le champ `derived_atoms`. Pour chaque atome dérivé, vérifier s'il a d'autres archives parentes (champ `contexte_origine` éventuellement multi-valué) :

- Si l'atome a **une seule** archive parente (= celle qu'on supprime) → il sera orphelinisé.
- Si l'atome a **plusieurs** archives parentes → mise à jour : retirer notre archive de sa liste, conserver l'atome.

### 3. Présenter le plan

Format :

```
## Rollback — {slug ou « vault global »}

Archive à supprimer :
  {chemin de l'archive}

Atomes dérivés ({N}) :
  - [[atome 1]] — orphelin après rollback : {oui|non}
  - [[atome 2]] — orphelin après rollback : {oui|non}

Action sur les atomes :
  - {N orphelins} seront supprimés (avec --with-derived) ou conservés (par défaut, déliés)
  - {N non-orphelins} : référence vers l'archive supprimée retirée

Continuer ? [o/n]
```

### 4. Appliquer (si confirmé ou `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Étapes :

1. **Supprimer le fichier archive** : `rm {chemin-archive}`.
2. **Pour chaque atome dérivé** :
   - Si orphelin et `--with-derived` : supprimer le fichier.
   - Si orphelin sans `--with-derived` : retirer le champ `contexte_origine` (atome devient autonome).
   - Si non-orphelin : retirer notre référence dans `contexte_origine` (peut être multi-valué).
3. **Retirer la ligne dans `historique.md`** du projet/domaine. Pattern 2.
4. **Retirer l'entrée dans `99-meta/_index.md`**. Pattern 2.

### 5. Avertissement contexte

Afficher :

```
Rollback effectué.
Archive supprimée : {chemin}
Atomes dérivés : {N supprimés, N déliés}

ATTENTION : contexte.md du projet/domaine n'a PAS été restauré (il représentait
l'état au moment de l'archive supprimée). Pour régénérer un contexte cohérent,
lance /mem-recall {slug} qui se basera sur l'avant-dernière archive.
```
