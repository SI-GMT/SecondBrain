---
name: mem-rollback-archive
description: Annuler la dernière archive d'un projet (ou du vault global si pas de projet spécifié). Supprime le fichier archive, retire la ligne correspondante de historique.md et de _index.md. NE RESTAURE PAS contexte.md — l'avertir à l'utilisateur et suggérer /mem-recall pour régénérer un contexte à partir des archives restantes. DÉCLENCHEMENT via /mem-rollback-archive [projet] ou langage naturel — « annule la dernière archive », « oublie la dernière session », « rollback l'archive de X ».
---

{{PROCEDURE}}
