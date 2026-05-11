; SecondBrain Desktop — Inno Setup installer
; -----------------------------------------------------------------------------
; Builds an unsigned .exe installer that:
;   1. Lays the PyInstaller bundle under %LOCALAPPDATA%\SecondBrainDesktop.
;   2. Bundles the Memory Kit source tree so the in-app first-run wizard
;      can install the engine + wire MCP into the user's LLM CLIs without
;      requiring them to type anything in a terminal.
;   3. Registers an opt-in autostart key, creates Start Menu shortcuts.
;
; The kit install + MCP wiring is **not** done by Inno itself. The
; PyInstaller-built ``SecondBrainTray.exe`` detects on first launch
; that ``~/.memory-kit/config.json`` is missing and runs its built-in
; setup wizard, which collects the user's choices (vault path,
; language, which LLM CLIs to wire) and invokes the bundled deploy
; script in the background with the right flags. This keeps a single,
; guided, end-to-end experience without forking the install logic
; between two places.
;
; Compile order:
;   1. Build the PyInstaller bundle first (see build/build_windows.ps1).
;   2. Run ISCC.exe build/installer.iss (build_windows.ps1 does both).
; -----------------------------------------------------------------------------

#define MyAppName        "SecondBrain Desktop"
#define MyAppVersion     "0.5.0"
#define MyAppPublisher   "SI-GMT"
#define MyAppURL         "https://github.com/SI-GMT/SecondBrain"
#define MyAppExeName     "SecondBrainTray.exe"

[Setup]
; The AppId GUID must remain stable across releases so upgrades land in
; the same install dir. Generate once, never rotate.
AppId={{4F8E1B8F-4A94-4D5C-9F7E-4E3D2F1A0B91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\SecondBrainDesktop
DefaultGroupName=SecondBrain
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=SecondBrainDesktop-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
UsePreviousAppDir=yes
UsePreviousTasks=yes
WizardStyle=modern
ChangesEnvironment=no
SetupIconFile=generated-icons\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start &SecondBrain Desktop at login"; \
    GroupDescription: "Startup options:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop &shortcut"; \
    GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; 1. The PyInstaller bundle (~80 MB).
Source: "..\dist\SecondBrainTray\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; 2. Kit source tree — bundled so deploy.ps1 can do its job offline.
;    Trimmed to the bits deploy.ps1 actually reads.
Source: "..\..\core\*"; DestDir: "{app}\kit\core"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\adapters\*"; DestDir: "{app}\kit\adapters"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\mcp-server\*"; DestDir: "{app}\kit\mcp-server"; \
    Excludes: "*.pyc,__pycache__,*.dist-info,build,dist,.venv,.venv-build"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\scripts\*"; DestDir: "{app}\kit\scripts"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\deploy.ps1"; DestDir: "{app}\kit"; Flags: ignoreversion
Source: "..\..\deploy.sh"; DestDir: "{app}\kit"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}\kit"; Flags: ignoreversion
Source: "..\..\CLAUDE.md"; DestDir: "{app}\kit"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Optional autostart — only written when the user ticks the task.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "SecondBrainDesktop"; \
    ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; \
    Tasks: autostart

[Run]
; Verify the bundle starts (catches missing Python runtime pieces or AV
; quarantine before the user clicks the tray icon and hits a silent
; failure). The actual kit install + MCP wiring runs from inside the app
; on first launch via the setup wizard, not from this installer.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--healthcheck"; \
    Flags: runhidden waituntilterminated; StatusMsg: "Verifying SecondBrain Desktop..."

; Launch the app at the end of the wizard. The desktop will detect that
; the kit is not yet installed and pop its built-in setup wizard.
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName} (will guide you through setup)"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the running tray before removing files. /F = force, /T = process tree.
Filename: "taskkill.exe"; Parameters: "/IM {#MyAppExeName} /F"; \
    Flags: runhidden; RunOnceId: "kill-tray"

[Code]
function IsPythonAvailable(): Boolean;
var
  ResultCode: Integer;
begin
  // Probe via ``where python``. Cheap, no Python startup.
  if Exec(ExpandConstant('{cmd}'), '/C where python >NUL 2>&1', '',
          SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := ResultCode = 0
  else
    Result := False;
end;

function IsKitInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  if Exec(ExpandConstant('{cmd}'), '/C where memory-kit-mcp >NUL 2>&1', '',
          SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := ResultCode = 0
  else
    Result := False;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if (not IsPythonAvailable()) and (not IsKitInstalled()) then
    begin
      MsgBox(
        'SecondBrain Desktop is installed.' #13#10 #13#10 +
        'Python 3.12+ was not detected on PATH, so the in-app setup ' +
        'wizard will not be able to install the Memory Kit engine on ' +
        'first launch.' #13#10 #13#10 +
        'Install Python from https://www.python.org/downloads/ (or the ' +
        'Microsoft Store), then re-run the wizard from the tray menu: ' +
        'Settings -> Re-run setup wizard.' #13#10 #13#10 +
        'The tray itself works without Python — it just can''t install ' +
        'the engine for the LLM CLIs to use.',
        mbInformation, MB_OK
      );
    end;
  end;
end;
