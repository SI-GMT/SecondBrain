# SecondBrain Desktop v0.12.2

Rebuild de l'app desktop sur le moteur **engine v0.15.0** (archivage délégué `brief→expand+gate`).

## Changements

- **Engine bundlé : 0.14.1 → 0.15.0.** L'installeur embarque le nouveau moteur ; les CLI pilotées par l'utilisateur bénéficient de l'archivage délégué (`/mem-archive` ~3× plus rapide, ~10× moins coûteux, qualité préservée). Les appels in-process du desktop (scan / repair vault) tournent sur 0.15.0.
- Aucun changement de code desktop : l'UI, l'auto-update dual-canal et la surveillance vault sont identiques à `sb-desktop-v0.12.1`. La version d'engine affichée par l'icône reflète automatiquement 0.15.0 (lecture disque fraîche).

## Qualité

- Suite desktop : **154 passed / 8 skipped, 72.81 % coverage** (gate 70 %).

## Asset

- `SecondBrainDesktop-0.12.2-setup.exe` (~75 MB, runtime Python embarqué, engine 0.15.0)

## Installation / mise à jour

Télécharger l'installeur et double-cliquer (per-user, sans terminal). Une install existante se met à jour via *Check for updates* dans le menu de l'icône, ou en relançant l'installeur.
