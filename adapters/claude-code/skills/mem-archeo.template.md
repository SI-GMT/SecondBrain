---
name: mem-archeo
description: Reconstituer l'historique d'un dépôt Git existant en plusieurs archives datées dans le vault mémoire (1 archive par tag, release, merge ou fenêtre de commits). DÉCLENCHEMENT AUTOMATIQUE (sans attendre que l'utilisateur tape /mem-archeo) quand il exprime en langage naturel — « fais une rétro Git de ce projet », « reconstitue l'historique de ce dépôt », « archéo sur ce repo », « analyse les tags de version et archive-les », « remonte les bumps de version et crée des archives ». Également invocable explicitement via /mem-archeo [chemin-du-dépôt] avec options --niveau, --projet, --depuis, --jusqu-a, --fenetre, --dry-run. Détection automatique du niveau de granularité (tags → releases → merges → fenêtres de commits) avec confirmation interactive avant écriture. Idempotent : skip les archives déjà créées pour le même jalon. Jamais d'écrasement d'archive vécue.
---

{{PROCEDURE}}
