---
name: mem-doc
description: Ingérer un document local (PDF, Markdown, texte, image, docx…) dans le vault mémoire comme archive single-shot. DÉCLENCHEMENT AUTOMATIQUE (sans attendre que l'utilisateur tape /mem-doc) quand il exprime en langage naturel — « ingère ce document », « archive ce fichier », « enregistre ce PDF dans ma mémoire », « absorbe ce document », « indexe cette spec ». Également invocable explicitement via /mem-doc {chemin} avec options --projet {nom} et --titre "{texte}". La résolution du projet cible est automatique par priorité descendante (argument explicite → match dans le chemin → match dans le CWD → fallback inbox).
---

{{PROCEDURE}}
