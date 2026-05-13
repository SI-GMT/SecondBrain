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
#define MyAppVersion     "0.8.7"
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

; Force the 64-bit install hive even when ISCC is x86. Without this
; {autopf} = {pf32} = "Program Files (x86)", which the Python runtime
; detect_install_mode() probe does NOT recognise as a system root
; (it reads %ProgramFiles% which always resolves to the 64-bit path
; for a 64-bit Tray.exe). The mismatch flipped detection back to DEV,
; the wizard tried to re-bootstrap, and pip-extract crashed with
; ERROR 13 because Program Files is read-only for non-admin users.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; {autopf} resolves to:
;   * %ProgramFiles%   (64-bit) if running elevated under 64-bit mode
;   * %LOCALAPPDATA%\Programs   if running non-elevated (user install)
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
Source: "release-kit\engine\bootstrap_engine.py"; DestDir: "{app}\engine"; \
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
; context, can write under Program Files). One single Python script
; orchestrates everything (patch _pth → get-pip → pip install →
; verify) so a partial state never leaks to the per-user wizard.
; Per-user install: skip — the wizard handles it on first launch.
Filename: "{app}\engine\python\python.exe"; \
    Parameters: """{app}\engine\bootstrap_engine.py"""; \
    WorkingDir: "{app}\engine"; \
    Flags: runhidden waituntilterminated; \
    StatusMsg: "Installing the engine (this can take a minute)…"; \
    Check: IsAdminInstallMode and NeedsBootstrap

; Hard verification — [Code] CurStepChanged at ssPostInstall asserts
; that memory-kit-mcp.exe is present on a system install. If absent,
; the installer shows a clear error dialog before exiting so the user
; isn't left with a half-broken state.

; Auto-launch the tray on the Finished page. ``runasoriginaluser`` is
; mandatory on elevated installs so the wizard runs as the human
; user (writes to their per-user state) instead of the admin token.
; ``unchecked`` is intentionally omitted — the checkbox defaults to
; checked, so a one-click Finish auto-launches the wizard.
Filename: "{app}\app\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName} (we'll guide you through setup)"; \
    Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/IM {#MyAppExeName} /F"; \
    Flags: runhidden; RunOnceId: "kill-tray"
; LLM CLIs may have spawned memory-kit-mcp.exe sessions that hold a
; lock on engine files — kill them so the file deletes succeed.
Filename: "taskkill.exe"; Parameters: "/IM memory-kit-mcp.exe /F /T"; \
    Flags: runhidden; RunOnceId: "kill-engine"

[UninstallDelete]
; Wipe every artefact produced at runtime by the bootstrap +
; subsequent engine usage. Inno only tracks files copied via [Files];
; anything created post-install (site-packages, byte-cache,
; pywin32 DLLs copied next to python.exe, ad-hoc .pth edits) is
; invisible to its default uninstall pass and must be deleted
; explicitly to avoid orphan directories under Program Files.
Type: filesandordirs; Name: "{app}\engine\Lib"
Type: filesandordirs; Name: "{app}\engine\Scripts"
Type: filesandordirs; Name: "{app}\engine\python"
Type: filesandordirs; Name: "{app}\engine\wheels"
Type: filesandordirs; Name: "{app}\engine\__pycache__"
Type: files;          Name: "{app}\engine\bootstrap_engine.py"
Type: files;          Name: "{app}\engine\get-pip.py"
Type: dirifempty;     Name: "{app}\engine"
Type: filesandordirs; Name: "{app}\resources\__pycache__"
Type: filesandordirs; Name: "{app}\app\__pycache__"
Type: dirifempty;     Name: "{app}"

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

procedure CurStepChanged(CurStep: TSetupStep);
var
  ErrMsg: String;
begin
  // Post-install assertion: on a system install the engine bootstrap
  // MUST have deposited memory-kit-mcp.exe. If it didn't, the wizard
  // at first launch can't recover (Program Files is read-only for the
  // per-user run), so we tell the user immediately instead of letting
  // them hit a confusing error later.
  if (CurStep = ssPostInstall) and IsAdminInstallMode then
  begin
    if not FileExists(_KitBinaryPath()) then
    begin
      ErrMsg :=
        'The SecondBrain engine could not be installed.' + #13#10 + #13#10 +
        'Expected file is missing:' + #13#10 +
        _KitBinaryPath() + #13#10 + #13#10 +
        'This usually means the embedded Python bootstrap failed.' + #13#10 +
        'Please rerun the installer as administrator. If the issue ' +
        'persists, send the log under %TEMP%\Setup Log*.txt to support.';
      MsgBox(ErrMsg, mbCriticalError, MB_OK);
      // Abort the install — the wizard would be stuck on first launch.
      WizardForm.Close;
    end;
  end;
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

function _RemoveFromSystemPath(): Boolean;
var
  CurrentPath, NewPath, TargetDir, TargetLower, Lower: String;
  Parts: TArrayOfString;
  I, Count: Integer;
begin
  // Strip {app}\engine\Scripts from HKLM PATH at uninstall time.
  // Inno's [Registry] entry used ``preservestringtype noerror`` and
  // therefore did NOT mark the value for ``uninsdeletevalue``, so the
  // entry would otherwise remain after uninstall. Walk the value,
  // drop our segment, write back.
  Result := False;
  TargetDir := ExpandConstant('{app}\engine\Scripts');
  TargetLower := LowerCase(TargetDir);

  if not RegQueryStringValue(
      HKEY_LOCAL_MACHINE,
      'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
      'Path',
      CurrentPath) then
    Exit;

  NewPath := '';
  Count := 0;
  while Length(CurrentPath) > 0 do
  begin
    I := Pos(';', CurrentPath);
    if I = 0 then
    begin
      Lower := LowerCase(CurrentPath);
      if Lower <> TargetLower then
      begin
        if NewPath <> '' then NewPath := NewPath + ';';
        NewPath := NewPath + CurrentPath;
      end;
      CurrentPath := '';
    end
    else
    begin
      Lower := LowerCase(Copy(CurrentPath, 1, I - 1));
      if Lower <> TargetLower then
      begin
        if NewPath <> '' then NewPath := NewPath + ';';
        NewPath := NewPath + Copy(CurrentPath, 1, I - 1);
      end
      else
        Inc(Count);
      CurrentPath := Copy(CurrentPath, I + 1, Length(CurrentPath));
    end;
  end;

  if Count > 0 then
  begin
    RegWriteExpandStringValue(
      HKEY_LOCAL_MACHINE,
      'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
      'Path',
      NewPath);
    Result := True;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Strip the engine PATH entry once, before Inno deletes the
  // [Files] payload. Best-effort — broadcasting is handled by Inno's
  // own ChangesEnvironment=yes hook a few moments later.
  if CurUninstallStep = usUninstall then
  begin
    if IsAdminInstallMode then
      _RemoveFromSystemPath();
  end;
end;
