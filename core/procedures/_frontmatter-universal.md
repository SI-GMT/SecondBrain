## Frontmatter universel (toutes zones hors inbox/meta)

Tout fichier du vault hors `00-inbox/` et `99-meta/` porte les **6 champs universels** suivants. Les autres champs sont propres à chaque zone (cf. spec section 7 du document de cadrage).

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `date` | `YYYY-MM-DD` | ✅ | Date de création du fichier. Mise à jour tolérée sur `contexte.md` et notes longues. |
| `zone` | enum | ✅ | `inbox`, `episodes`, `knowledge`, `procedures`, `principes`, `objectifs`, `personnes`, `cognition`, `meta`. |
| `scope` | enum | ✅ | `perso` ou `pro`. |
| `collectif` | bool | ✅ (défaut `false`) | Flag de promotion vers CollectiveBrain. Non lu par SecondBrain v0.5.0. |
| `modality` | enum | ✅ | `left` ou `right`. Défaut `left`. `right` pour schémas, Excalidraw, métaphores, moodboards. |
| `tags` | liste | ✅ | Tags Obsidian. Doivent **redonder les champs frontmatter** pour permettre la vue graphique (Obsidian indexe les tags, pas les champs). |

### Invariants à vérifier à l'écriture

Le router et `mem-reclass` enforce les invariants cross-champs ci-dessous. Toute violation est bloquée à l'écriture et signalée à l'utilisateur :

1. **Scope perso ⇒ collectif false.** Toujours. `collectif: true` sur `scope: perso` = erreur bloquante.
2. **Sensitive true ⇒ collectif false.** Si le frontmatter porte `sensitive: true` (par défaut sur les fiches `60-personnes/`), `collectif: true` est interdit.
3. **Zone episodes ⇒ `kind` présent.** Jamais d'archive sans `kind: projet` ou `kind: domaine`.
4. **Kind projet ⇒ `projet: {slug}` présent et slug existant** dans `10-episodes/projets/`. Idem pour `kind: domaine` et `domaine: {slug}` dans `10-episodes/domaines/`.
5. **Tags reflètent frontmatter.** `zone: episodes` ⇒ tag `zone/episodes` obligatoire, et inversement. Idem pour `scope/*`, `kind/*`, `modality/*`.
6. **Modality absent ⇒ défaut `left`.** Appliqué silencieusement à l'écriture.
7. **Date obligatoire hors inbox/meta + contexte.md/historique.md.** Les contextes et historiques sont mutables, non datés.

### Cas particuliers

- **`00-inbox/`** : aucun champ obligatoire hormis `zone: inbox` et `tags: [zone/inbox]`. Les autres champs (scope, modality, etc.) sont fixés au moment du reclassement par `mem-reclass`.
- **`99-meta/`** : pas de `scope`, `collectif`, `modality` (méta neutre, transverse). Frontmatter minimal : `date`, `zone: meta`, `type` (parmi `index|doctrine|taxonomie|regle`), `tags`.
- **`contexte.md` et `historique.md`** : pas de `date` (fichiers mutables). Héritent du scope du projet/domaine déclaré une seule fois dans `contexte.md`.
