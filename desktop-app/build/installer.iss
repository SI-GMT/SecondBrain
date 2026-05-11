; SecondBrain Desktop — Inno Setup installer
; -----------------------------------------------------------------------------
; Builds an unsigned .exe installer that:
;   1. Lays the PyInstaller bundle under %LOCALAPPDATA%\SecondBrainDesktop.
;   2. Optionally installs the Memory Kit engine (via the bundled kit source
;      tree + deploy.ps1) and wires up MCP for the user's LLM CLIs (Claude
;      Code, Claude Desktop, Codex, Gemini, Vibe, Copilot).
;   3. Registers an opt-in autostart key, creates Start Menu shortcuts.
;
; The kit install step is opt-in via a [Tasks] checkbox so the user can
; install the desktop alone (e.g. on a machine that already has the kit
; deployed elsewhere) or do the full bundle.
;
; Compile order:
;   1. Build the PyInstaller bundle first (see build/build_windows.ps1).
;   2. Run ISCC.exe build/installer.iss (build_windows.ps1 does both).
; -----------------------------------------------------------------------------

#define MyAppName        "SecondBrain Desktop"
#define MyAppVersion     "0.3.0"
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
Name: "installkit"; Description: "&Install the Memory Kit engine (pipx) and wire up MCP for installed LLM CLIs"; \
    GroupDescription: "Memory Kit engine:"; Flags: checkedonce

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
; Step 1: run the Memory Kit deploy script when the user opted in via the
;         "installkit" task. Pass -AutoUpdate to make it idempotent on
;         re-installs (it then upgrades the pipx env in place).
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\kit\deploy.ps1"" -AutoUpdate"; \
    WorkingDir: "{app}\kit"; \
    Flags: runhidden waituntilterminated; \
    StatusMsg: "Installing Memory Kit engine (pipx + MCP wiring)..."; \
    Tasks: installkit

; Step 2: verify the desktop bundle starts (catches missing Python runtime
;         pieces, antivirus quarantine, etc. before the user clicks the icon).
Filename: "{app}\{#MyAppExeName}"; Parameters: "--healthcheck"; \
    Flags: runhidden waituntilterminated; StatusMsg: "Verifying SecondBrain Desktop..."

; Step 3: launch the app at the end of the wizard.
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName}"; \
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

function ShouldRunKitInstall(): Boolean;
begin
  Result := IsTaskSelected('installkit');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  WantsKit: Boolean;
begin
  if CurStep = ssInstall then
  begin
    // Block the kit install step early if Python is missing so the user
    // doesn't sit through a long ``deploy.ps1`` failure for nothing.
    WantsKit := ShouldRunKitInstall();
    if WantsKit and (not IsPythonAvailable()) then
    begin
      MsgBox(
        'Python 3.12+ is required to install the Memory Kit engine, but it ' +
        'was not detected on PATH.' #13#10 #13#10 +
        'Install Python from https://www.python.org/downloads/ (or the Microsoft ' +
        'Store), then re-run this installer.' #13#10 #13#10 +
        'SecondBrain Desktop itself does not need Python — the bundled engine ' +
        'is sufficient. You can finish this install and add the kit later.',
        mbInformation, MB_OK
      );
    end;
  end;

  if CurStep = ssPostInstall then
  begin
    if (not ShouldRunKitInstall()) and (not IsKitInstalled()) then
    begin
      MsgBox(
        'SecondBrain Desktop is installed.' #13#10 #13#10 +
        'The Memory Kit engine (memory-kit-mcp) was not detected on PATH and ' +
        'you opted out of installing it. The tray app still works in standalone ' +
        'mode, but your LLM CLIs (Claude Code, Codex, Gemini, ...) will not see ' +
        'the SecondBrain vault until the kit is installed.' #13#10 #13#10 +
        'Re-run this installer with "Install the Memory Kit engine" ticked, or ' +
        'follow the guide at https://github.com/SI-GMT/SecondBrain.',
        mbInformation, MB_OK
      );
    end;
  end;
end;
