; SecondBrain Desktop — Inno Setup installer
; -----------------------------------------------------------------------------
; Builds an unsigned .exe installer that lays down the PyInstaller bundle
; under %LOCALAPPDATA%, registers an autostart key (opt-in via task), and
; ships a "Configure MCP targets" post-install action that re-runs the kit's
; deploy.ps1 to inject the MCP config in every detected LLM CLI.
;
; The installer does NOT install Python — the bundle is fully self-contained.
; The kit itself (memory-kit-mcp Python package) is expected to be on PATH;
; if absent, the post-install hook surfaces a one-shot dialog explaining how
; to obtain it. We deliberately don't auto-install the kit from this installer
; — that's a separate concern owned by deploy.ps1, which handles every
; supported CLI (Claude Code, Codex, Gemini, Vibe, Copilot) consistently.
;
; To compile:
;   1. Build the PyInstaller bundle first (see build/build_windows.ps1).
;   2. Run ISCC.exe build/installer.iss
; -----------------------------------------------------------------------------

#define MyAppName        "SecondBrain Desktop"
#define MyAppVersion     "0.1.0"
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
Name: "autostart"; Description: "Start &SecondBrain Desktop at login"; GroupDescription: "Startup options:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop &shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; The PyInstaller bundle ships as a directory under dist/SecondBrainTray/.
; recursesubdirs preserves the layout (Python runtime, DLLs, _internal/, etc.).
Source: "..\dist\SecondBrainTray\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
; Sanity-check the bundle starts (so the installer surface a useful error
; instead of leaving the user with a silent broken install). The
; --healthcheck flag is documented in __main__.py; exit code 0 = ok.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--healthcheck"; \
    Flags: runhidden waituntilterminated; StatusMsg: "Verifying install..."

; Offer to launch the app at the end of the wizard.
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; Try to stop a running tray before removing the files. /F = force.
Filename: "taskkill.exe"; Parameters: "/IM {#MyAppExeName} /F"; \
    Flags: runhidden; RunOnceId: "kill-tray"

[Code]
function IsKitInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  // We rely on Windows 'where' to detect memory-kit-mcp on PATH. Cheap,
  // does not require Python introspection. A non-zero exit means absent.
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
    if not IsKitInstalled() then
    begin
      MsgBox(
        'The Memory Kit engine (memory-kit-mcp) was not detected on PATH.' #13#10 #13#10
        'SecondBrain Desktop will run, but vault scan / repair / update will be unavailable until the engine is installed.' #13#10 #13#10
        'See https://github.com/SI-GMT/SecondBrain for the kit install guide (deploy.ps1).',
        mbInformation, MB_OK
      );
    end;
  end;
end;
