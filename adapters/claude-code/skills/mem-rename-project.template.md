---
name: mem-rename-project
description: Renommer un projet dans le vault mémoire de manière COMPLÈTE — plus aucune référence à l'ancien slug ni à l'ancien label affiché ne doit subsister. Met à jour le dossier projet, les frontmatters ET les H1 ET le corps de contexte.md + historique.md + toutes les archives référencées. Renomme les fichiers archives (remplace l'ancien slug dans le nom tout en préservant l'horodatage). Met à jour _index.md (section Projets et section Archives — labels + chemins). Nettoie .obsidian/workspace.json des entrées stales. Vérification finale par grep pour détecter toute occurrence résiduelle. DÉCLENCHEMENT via /mem-rename-project {ancien} {nouveau} ou langage naturel — « renomme le projet X en Y », « change le slug de X ». Si le nouveau label n'est pas fourni, le dériver du nouveau slug (tirets/underscores → espaces + capitalisation). Si le nouveau slug existe déjà, suggérer /mem-merge-projects.
---

{{PROCEDURE}}
