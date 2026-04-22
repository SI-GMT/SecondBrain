---
name: mem-merge-projects
description: Fusionner deux projets du vault mémoire. Le projet source est supprimé après que ses archives soient retaggées au nom du projet cible, que son historique soit concaténé à celui de la cible, et que son entrée soit retirée de _index.md. NE TOUCHE PAS au contexte.md de la cible (fusion sémantique = décision éditoriale de l'utilisateur). DÉCLENCHEMENT via /mem-merge-projects {source} {cible} ou langage naturel — « fusionne le projet X dans Y », « regroupe X et Y sous Y ».
---

{{PROCEDURE}}
