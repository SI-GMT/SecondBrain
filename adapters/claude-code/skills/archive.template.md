---
name: archive
description: Archiver la session de travail dans le vault mémoire pour permettre une reprise ultérieure via /recall. Utiliser ce skill dans DEUX situations distinctes. (1) MODE COMPLET, fin de session — déclencher quand l'utilisateur dit « on s'arrête », « je pars », « on termine », tape /clear ou /archive, ou demande explicitement d'archiver. Exécuter alors toute la procédure (fichier archive horodaté + réécriture de contexte.md + mise à jour de historique.md + mise à jour de _index.md). (2) MODE INCRÉMENTAL SILENCIEUX, pendant la session — dès qu'un fait, une décision ou une prochaine étape importante émerge ET n'est pas déjà présent dans contexte.md, mettre à jour UNIQUEMENT contexte.md sans créer d'archive ni annoncer l'action à l'utilisateur. Ne jamais créer d'archive complet en mode silencieux : ça polluerait l'historique.
---

{{PROCEDURE}}
