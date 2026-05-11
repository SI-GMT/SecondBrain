; SecondBrain Desktop — Inno Setup installer (v0.6 Rolls-Royce)
; -----------------------------------------------------------------------------
; Builds an unsigned .exe installer that lays out a fully self-contained
; SecondBrain installation under a user-pickable directory. The default
; is %LOCALAPPDATA%\SecondBrain. After install the directory contains
; everything needed to run without Python or pipx on the host:
;
;   {app}\
;     app\
;       SecondBrainTray.exe + _internal\ (PyInstaller bundle)
;     engine\
;       python\            (Python embeddable runtime — pre-extracted)
;       wheels\            (memory-kit-mcp + transitive dep wheels)
;       get-pip.py         (pip bootstrap script)
;     resources\
;       core\, adapters\, i18n\  (kit source-of-truth, release subset)
;     uninstall.exe
;
; First launch of ``SecondBrainTray.exe`` runs the in-app setup wizard,
; which uses these artifacts to:
;   - extract pip into the embedded Python (one-shot bootstrap),
;   - pip-install memory-kit-mcp from the bundled wheels offline,
;   - add ``{app}\engine\Scripts`` to the user PATH,
;   - write ~/.memory-kit/config.json,
;   - inject MCP config into every selected LLM CLI (Claude Code,
;     Claude Desktop, Codex, Gemini, Mistral Vibe, Copilot CLI).
;
; The installer does NOT touch the user PATH itself — the wizard does,
; so PATH changes happen at the same time as the wheels are extracted
; and we never end up with PATH pointing at a half-installed engine.
; -----------------------------------------------------------------------------

#define MyAppName        "SecondBrain Desktop"
#define MyAppVersion     "0.6.0"
#define MyAppPublisher   "SI-GMT"
#define MyAppURL         "https://github.com/SI-GMT/SecondBrain"
#define MyAppExeName     "SecondBrainTray.exe"

[Setup]
AppId={{4F8E1B8F-4A94-4D5C-9F7E-4E3D2F1A0B91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; ---- Install directory ------------------------------------------------------
; User-pickable, with %LOCALAPPDATA%\SecondBrain as the default. The
; ``DisableDirPage`` flag is NOT set so the wizard asks. ``DiskSpaceMBLabel``
; is rendered automatically. We don't require admin rights — installs land
; entirely under the user profile.
DefaultDirName={localappdata}\SecondBrain
DirExistsWarning=auto
DisableDirPage=no
UsePreviousAppDir=yes

DefaultGroupName=SecondBrain
DisableProgramGroupPage=yes

OutputDir=..\dist
OutputBaseFilename=SecondBrainDesktop-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
ChangesEnvironment=no
SetupIconFile=generated-icons\app.ico
UninstallDisplayIcon={app}\app\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start &SecondBrain Desktop at login"; \
    GroupDescription: "Startup options:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop &shortcut"; \
    GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; 1. PyInstaller bundle (the tray app).
Source: "..\dist\SecondBrainTray\*"; DestDir: "{app}\app"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; 2. Engine: embedded Python + wheels + get-pip.py. The wizard runs the
;    bootstrap on first launch.
Source: "release-kit\engine\python\*"; DestDir: "{app}\engine\python"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "release-kit\engine\wheels\*"; DestDir: "{app}\engine\wheels"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "release-kit\engine\get-pip.py"; DestDir: "{app}\engine"; \
    Flags: ignoreversion

; 3. Kit resources (procedures + adapters + i18n) — release subset, NOT
;    a copy of the dev tree.
Source: "release-kit\resources\*"; DestDir: "{app}\resources"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Optional autostart — only written when the user ticks the task.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "SecondBrainDesktop"; \
    ValueData: """{app}\app\{#MyAppExeName}"""; Flags: uninsdeletevalue; \
    Tasks: autostart

[Run]
; Smoke-test the bundle runs (catches missing DLLs, antivirus quarantine).
Filename: "{app}\app\{#MyAppExeName}"; Parameters: "--healthcheck"; \
    Flags: runhidden waituntilterminated; StatusMsg: "Verifying SecondBrain Desktop..."

; Offer to launch the app — first launch triggers the in-app setup wizard.
Filename: "{app}\app\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName} (we'll guide you through setup)"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/IM {#MyAppExeName} /F"; \
    Flags: runhidden; RunOnceId: "kill-tray"
