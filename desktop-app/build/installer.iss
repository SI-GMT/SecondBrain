; SecondBrain Desktop — Inno Setup installer (v0.7 multi-user)
; -----------------------------------------------------------------------------
; Dual-mode installer: at launch the user picks between
;
;   * System install (admin, recommended for RDP / shared machines):
;       %ProgramFiles%\SecondBrain
;     Every user of the host shares the engine binaries — only the
;     admin needs to run the installer + the engine bootstrap. Per-user
;     state (settings, vault, MCP config) stays in each user's profile.
;
;   * Per-user install (current-user only, no admin):
;       %LOCALAPPDATA%\SecondBrain
;     Same layout, no shared resource. Suitable for single-user
;     laptops where you don't want admin friction.
;
; The choice is offered via Inno's PrivilegesRequiredOverridesAllowed
; mechanism. The default is admin (system) because that's the right
; answer for the audience we want to serve next (managed Windows /
; RDP), but a per-user fallback is one click away if elevation is
; refused.
;
; On a system install the engine bootstrap (pip install into
; engine/Lib/site-packages, PATH update on HKLM) runs once at install
; time, elevated. Per-user wizard runs after that just do per-user
; setup (vault picker + ~/.memory-kit/config.json + MCP wiring into
; the user's ~/.claude.json etc.) — fast, no admin.
; -----------------------------------------------------------------------------

#define MyAppName        "SecondBrain Desktop"
#define MyAppVersion     "0.7.0"
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

; ---- Dual-mode install ------------------------------------------------------
; admin = system-wide install under {commonpf64}\SecondBrain.
; lowest = per-user install under {localappdata}\Programs\SecondBrain.
; The "dialog commandline" override lets the user pick at launch via a
; standard Windows dialog (or pass /ALLUSERS / /CURRENTUSER on the CLI).
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline

; {autopf} resolves to:
;   * %ProgramFiles% if running elevated (admin install)
;   * %LOCALAPPDATA%\Programs if running non-elevated (user install)
DefaultDirName={autopf}\SecondBrain
DirExistsWarning=auto
DisableDirPage=no
UsePreviousAppDir=yes

DefaultGroupName=SecondBrain
DisableProgramGroupPage=yes

OutputDir=..\dist
OutputBaseFilename=SecondBrainDesktop-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
SetupIconFile=generated-icons\app.ico
UninstallDisplayIcon={app}\app\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Autostart writes to HKCU\Run regardless of install mode — autostart is
; always a per-user choice.
Name: "autostart"; Description: "Start &SecondBrain Desktop at login (current user)"; \
    GroupDescription: "Startup options:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop &shortcut"; \
    GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; 1. PyInstaller bundle (the tray app).
Source: "..\dist\SecondBrainTray\*"; DestDir: "{app}\app"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; 2. Engine: embedded Python + wheels + get-pip.py. Bootstrap will
;    populate engine\Lib\site-packages from these wheels.
Source: "release-kit\engine\python\*"; DestDir: "{app}\engine\python"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "release-kit\engine\wheels\*"; DestDir: "{app}\engine\wheels"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "release-kit\engine\get-pip.py"; DestDir: "{app}\engine"; \
    Flags: ignoreversion

; 3. Kit resources (procedures + adapters + i18n) — release subset.
Source: "release-kit\resources\*"; DestDir: "{app}\resources"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; ``{autoprograms}`` resolves to All Users start menu when admin, the
; current user's Programs folder otherwise.
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"
Name: "{autoprograms}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Autostart entry — always per-user (HKCU) regardless of install mode.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "SecondBrainDesktop"; \
    ValueData: """{app}\app\{#MyAppExeName}"""; Flags: uninsdeletevalue; \
    Tasks: autostart

; Machine PATH update for system installs (admin only). The runtime
; ``register_path`` step in ``kit_installer.py`` is a fallback that
; covers the per-user install path.
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}\engine\Scripts"; \
    Flags: preservestringtype noerror; Check: IsAdminInstallMode and PathNotAlreadyOnSystem

[Run]
; System install: bootstrap the engine once at install time (admin
; context, can write under Program Files). Per-user install: skip —
; the wizard will handle it on first launch.
Filename: "{app}\engine\python\python.exe"; \
    Parameters: """{app}\engine\get-pip.py"" --no-warn-script-location"; \
    WorkingDir: "{app}\engine"; \
    Flags: runhidden waituntilterminated; \
    StatusMsg: "Bootstrapping pip…"; \
    Check: IsAdminInstallMode and NeedsBootstrap

Filename: "{app}\engine\python\python.exe"; \
    Parameters: "-m pip install --no-index --find-links ""{app}\engine\wheels"" --no-warn-script-location memory-kit-mcp"; \
    WorkingDir: "{app}\engine"; \
    Flags: runhidden waituntilterminated; \
    StatusMsg: "Installing the engine into the shared site-packages…"; \
    Check: IsAdminInstallMode and NeedsBootstrap

; Smoke-test the tray bundle.
Filename: "{app}\app\{#MyAppExeName}"; Parameters: "--healthcheck"; \
    Flags: runhidden waituntilterminated; StatusMsg: "Verifying SecondBrain Desktop..."

; Launch — first launch per user pops the in-app wizard which does
; per-user MCP wiring + vault setup. On a system install the wizard
; skips the engine-install steps because they're already done.
Filename: "{app}\app\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName} (we'll guide you through setup)"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/IM {#MyAppExeName} /F"; \
    Flags: runhidden; RunOnceId: "kill-tray"

[UninstallDelete]
; Wipe the engine site-packages produced at install time so an
; uninstall leaves no orphans.
Type: filesandordirs; Name: "{app}\engine\Lib"
Type: filesandordirs; Name: "{app}\engine\Scripts"

[Code]
function _PythonExePath(): String;
begin
  Result := ExpandConstant('{app}\engine\python\python.exe');
end;

function _KitBinaryPath(): String;
begin
  Result := ExpandConstant('{app}\engine\Scripts\memory-kit-mcp.exe');
end;

function NeedsBootstrap(): Boolean;
begin
  // Run the bootstrap when the engine binary is not yet present —
  // i.e. fresh install. Subsequent installs over the top can skip it
  // because pip would just no-op the existing site-packages.
  Result := not FileExists(_KitBinaryPath());
end;

function PathNotAlreadyOnSystem(): Boolean;
var
  CurrentPath: String;
  TargetDir: String;
begin
  TargetDir := ExpandConstant('{app}\engine\Scripts');
  if not RegQueryStringValue(
      HKEY_LOCAL_MACHINE,
      'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
      'Path',
      CurrentPath) then
  begin
    Result := True;
    Exit;
  end;
  Result := Pos(LowerCase(TargetDir), LowerCase(CurrentPath)) = 0;
end;
