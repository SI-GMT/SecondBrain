## Encoding of written files

**All files written or modified by this procedure must be in UTF-8 without BOM, line endings LF.** Never CP1252, Windows-1252, UTF-8 with BOM, or OEM encoding — they corrupt French accents and diacritic characters (`�` in Obsidian).

Depending on the writing tool:
- **POSIX shell** (bash, sh, git-bash, WSL, macOS, Linux): native UTF-8 without BOM.
- **PowerShell 7+ (pwsh)**: `Set-Content -Encoding utf8NoBOM` or `Out-File -Encoding utf8NoBOM`.
- **Windows PowerShell 5.1**: `-Encoding UTF8` injects a BOM — prefer `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))`.
- **cmd.exe**: do not use for accented Markdown (OEM encoding corrupts) — switch to PowerShell or bash.
- **Python**: `open(path, 'w', encoding='utf-8', newline='\n')`.
- **Native LLM tools** (Write, file_write…): check the doc; when in doubt, write via shell with an explicit UTF-8 command.
