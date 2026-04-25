## Encodage des fichiers écrits

**Tous les fichiers écrits ou modifiés par cette procédure doivent l'être en UTF-8 sans BOM, fins de ligne LF.** Jamais de CP1252, Windows-1252, UTF-8 avec BOM, ni encodage OEM — ils corrompent les accents français et les caractères diacritiques (`�` dans Obsidian).

Selon l'outil d'écriture :
- **Shell POSIX** (bash, sh, git-bash, WSL, macOS, Linux) : natif UTF-8 sans BOM.
- **PowerShell 7+ (pwsh)** : `Set-Content -Encoding utf8NoBOM` ou `Out-File -Encoding utf8NoBOM`.
- **Windows PowerShell 5.1** : `-Encoding UTF8` injecte un BOM — préférer `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))`.
- **cmd.exe** : ne pas utiliser pour du Markdown accentué (encodage OEM corrompt) — basculer sur PowerShell ou bash.
- **Python** : `open(path, 'w', encoding='utf-8', newline='\n')`.
- **Outils natifs LLM** (Write, file_write…) : vérifier la doc ; en cas de doute, écrire via shell avec une commande explicite en UTF-8.
