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
; MyAppVersion is injected at compile time by build_windows.ps1 via
; `ISCC /DMyAppVersion=<x.y.z>` (read from desktop-app/pyproject.toml).
; The fallback below only applies when compiling installer.iss by hand —
; never trust it for a release build (cf. dynamic-version doctrine).
#ifndef MyAppVersion
  #define MyAppVersion   "0.0.0-dev"
#endif
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

; Detect & shut down the tray (and any LLM-CLI-spawned engine
; processes) before file copy. ``force`` skips the modal close prompt
; — InitializeSetup already showed our own upgrade confirmation, so a
; second close dialog would be redundant noise. RestartApplications
; is left off; the postinstall [Run] step relaunches the tray.
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll
RestartApplications=no

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
; Inno Setup ships translation files in the compiler's Languages/
; directory. We expose every locale the kit itself supports so the
; installer UI matches the LLM conversational language the user
; picked. Locale auto-detection from the OS happens automatically;
; the user can override via the language picker on the first
; installer page (or pass /LANG=fr on the CLI).
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french";  MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "german";  MessagesFile: "compiler:Languages\German.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
; Per-language overrides for the SecondBrain-specific strings. Inno
; falls back to the English line for any locale without an override.
english.TaskAutostart=Start &SecondBrain Desktop at login (current user)
french.TaskAutostart=Démarrer &SecondBrain Desktop à l'ouverture de session (utilisateur courant)
spanish.TaskAutostart=Iniciar &SecondBrain Desktop al iniciar sesión (usuario actual)
german.TaskAutostart=&SecondBrain Desktop bei der Anmeldung starten (aktueller Benutzer)
russian.TaskAutostart=Запускать &SecondBrain Desktop при входе в систему

english.TaskDesktopIcon=Create a desktop &shortcut
french.TaskDesktopIcon=Créer un &raccourci sur le Bureau
spanish.TaskDesktopIcon=Crear un &acceso directo en el escritorio
german.TaskDesktopIcon=Verknüpfung auf dem &Desktop erstellen
russian.TaskDesktopIcon=Создать &ярлык на рабочем столе

english.GroupStartup=Startup options:
french.GroupStartup=Options de démarrage :
spanish.GroupStartup=Opciones de inicio:
german.GroupStartup=Startoptionen:
russian.GroupStartup=Параметры запуска:

english.GroupShortcuts=Shortcuts:
french.GroupShortcuts=Raccourcis :
spanish.GroupShortcuts=Accesos directos:
german.GroupShortcuts=Verknüpfungen:
russian.GroupShortcuts=Ярлыки:

english.LaunchDescription=Launch SecondBrain Desktop (we'll guide you through setup)
french.LaunchDescription=Lancer SecondBrain Desktop (un assistant vous guidera)
spanish.LaunchDescription=Iniciar SecondBrain Desktop (un asistente le guiará)
german.LaunchDescription=SecondBrain Desktop starten (ein Assistent führt Sie durch die Einrichtung)
russian.LaunchDescription=Запустить SecondBrain Desktop (мастер настройки поможет завершить установку)

english.StatusBootstrap=Installing the engine (this can take a minute)…
french.StatusBootstrap=Installation du moteur (cela peut prendre une minute)…
spanish.StatusBootstrap=Instalando el motor (puede tardar un minuto)…
german.StatusBootstrap=Engine wird installiert (kann eine Minute dauern)…
russian.StatusBootstrap=Установка движка (это может занять минуту)…

english.MsgEngineMissing=The SecondBrain engine could not be installed.%n%nExpected file is missing:%n%1%n%nThis usually means the embedded Python bootstrap failed.%nPlease rerun the installer as administrator.
french.MsgEngineMissing=Le moteur SecondBrain n'a pas pu être installé.%n%nFichier attendu manquant :%n%1%n%nGénéralement, le bootstrap Python embarqué a échoué.%nVeuillez relancer l'installateur en tant qu'administrateur.
spanish.MsgEngineMissing=No se ha podido instalar el motor SecondBrain.%n%nFalta el archivo esperado:%n%1%n%nNormalmente significa que el arranque de Python integrado falló.%nVuelva a ejecutar el instalador como administrador.
german.MsgEngineMissing=Die SecondBrain-Engine konnte nicht installiert werden.%n%nErwartete Datei fehlt:%n%1%n%nÜblicherweise schlug die eingebettete Python-Initialisierung fehl.%nBitte führen Sie das Installationsprogramm als Administrator erneut aus.
russian.MsgEngineMissing=Не удалось установить движок SecondBrain.%n%nОжидаемый файл отсутствует:%n%1%n%nОбычно это означает сбой инициализации встроенного Python.%nЗапустите установщик от имени администратора.

english.MsgAlreadyInstalledSame=SecondBrain Desktop %1 is already installed.%n%nReinstall the same version?
french.MsgAlreadyInstalledSame=SecondBrain Desktop %1 est déjà installé.%n%nRéinstaller la même version ?
spanish.MsgAlreadyInstalledSame=SecondBrain Desktop %1 ya está instalado.%n%n¿Reinstalar la misma versión?
german.MsgAlreadyInstalledSame=SecondBrain Desktop %1 ist bereits installiert.%n%nDieselbe Version erneut installieren?
russian.MsgAlreadyInstalledSame=SecondBrain Desktop %1 уже установлен.%n%nПереустановить ту же версию?

english.MsgUpgrade=SecondBrain Desktop %1 is currently installed.%n%nUpdate to version %2?%n%nThe tray application and any running engine sessions will be closed automatically. Your vault, settings and MCP wirings are preserved.
french.MsgUpgrade=SecondBrain Desktop %1 est actuellement installé.%n%nMettre à jour vers la version %2 ?%n%nL'application et les sessions du moteur seront fermées automatiquement. Votre vault, vos paramètres et vos câblages MCP sont préservés.
spanish.MsgUpgrade=SecondBrain Desktop %1 está instalado actualmente.%n%n¿Actualizar a la versión %2?%n%nLa aplicación de bandeja y las sesiones en curso del motor se cerrarán automáticamente. Su vault, su configuración y los enlaces MCP se conservan.
german.MsgUpgrade=SecondBrain Desktop %1 ist derzeit installiert.%n%nAuf Version %2 aktualisieren?%n%nDie Tray-App und laufende Engine-Sitzungen werden automatisch geschlossen. Vault, Einstellungen und MCP-Verkabelung bleiben erhalten.
russian.MsgUpgrade=SecondBrain Desktop %1 уже установлен.%n%nОбновить до версии %2?%n%nПриложение и запущенные сессии движка будут закрыты автоматически. Ваше хранилище, настройки и подключения MCP сохраняются.

[Tasks]
; Autostart writes to HKCU\Run regardless of install mode — autostart is
; always a per-user choice.
Name: "autostart"; Description: "{cm:TaskAutostart}"; \
    GroupDescription: "{cm:GroupStartup}"; Flags: unchecked
Name: "desktopicon"; Description: "{cm:TaskDesktopIcon}"; \
    GroupDescription: "{cm:GroupShortcuts}"; Flags: unchecked

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
; System install: always re-run the bootstrap on install/upgrade.
;
; Why "always" and not gated on a missing binary: Inno's [Files] step
; overwrites ``engine/python/python312._pth`` with the pristine copy
; from the embeddable zip on every upgrade. If we only re-bootstrap
; when the binary is absent, an upgrade keeps the freshly-overwritten
; (un-patched) ``_pth`` while the [Files] copy resets it — site-
; packages drop off ``sys.path`` and the engine spawn dies with
; ``ModuleNotFoundError: memory_kit_mcp``. The bootstrap is
; idempotent (pip is a no-op on already-installed wheels, _pth patch
; + pywin32 DLL copy + .pth merge are all "ensure" operations) so a
; ~10 s re-run on upgrade is cheap insurance.
;
; Per-user install: still skipped here — wizard handles it on first
; launch in the user's writable layout.
Filename: "{app}\engine\python\python.exe"; \
    Parameters: """{app}\engine\bootstrap_engine.py"""; \
    WorkingDir: "{app}\engine"; \
    Flags: runhidden waituntilterminated; \
    StatusMsg: "{cm:StatusBootstrap}"; \
    Check: IsAdminInstallMode

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
    Description: "{cm:LaunchDescription}"; \
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
const
  UninstallRegKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';

function _DetectPreviousVersion(var Version: String): Boolean;
begin
  // Look for the previous install under both hives — AppId-suffixed
  // ``_is1`` key is Inno's standard. HKLM first (system install,
  // most common) then HKCU (per-user install).
  Result := RegQueryStringValue(
              HKEY_LOCAL_MACHINE, UninstallRegKey, 'DisplayVersion', Version)
         or RegQueryStringValue(
              HKEY_CURRENT_USER, UninstallRegKey, 'DisplayVersion', Version);
end;

procedure _KillRunningProcesses();
var
  ResultCode: Integer;
begin
  // Stop the tray + any LLM-CLI-spawned engine sessions BEFORE the
  // file-copy step runs. ``CloseApplications=force`` catches anything
  // holding [Files] handles, but we kill explicitly here so the user
  // gets immediate feedback if they had the tray open.
  Exec('taskkill.exe', '/IM ' + '{#MyAppExeName}' + ' /F',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('taskkill.exe', '/IM memory-kit-mcp.exe /F /T',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
var
  PrevVersion, Msg: String;
begin
  Result := True;
  if not _DetectPreviousVersion(PrevVersion) then
    Exit;  // Fresh install — proceed normally.

  if CompareText(PrevVersion, '{#MyAppVersion}') = 0 then
    Msg := FmtMessage(CustomMessage('MsgAlreadyInstalledSame'), [PrevVersion])
  else
    Msg := FmtMessage(CustomMessage('MsgUpgrade'), [PrevVersion, '{#MyAppVersion}']);

  if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDNO then
  begin
    Result := False;
    Exit;
  end;

  _KillRunningProcesses();
end;

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
      ErrMsg := FmtMessage(CustomMessage('MsgEngineMissing'), [_KitBinaryPath()]);
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
