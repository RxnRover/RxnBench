; Inno Setup script for the Rxn Bench desktop UI.
;
; Wraps the PyInstaller onedir build (dist\Rxn Bench\, produced by
; `make dist` / packaging\rxn-bench-ui.spec) in a single-file Windows
; installer for non-technical users.
;
; Installs per-user by default (no admin rights, no UAC prompt) so the
; devices\ folder next to the exe stays end-user-writable, matching the
; drop-in device plugin model (see rxn_bench_ui/devices/__init__.py and
; docs/ai/CURRENT_STATE.md "Standalone executable packaging"). An admin
; running the installer elevated can still choose "install for all users"
; in the wizard, which targets Program Files instead.
;
; Build (from rxnbench/frontend/, after `make dist`):
;   iscc packaging\installer.iss
; or with an explicit version:
;   iscc /DMyAppVersion=0.1.0 packaging\installer.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppName "Rxn Bench"
#define MyAppPublisher "Ames National Laboratory"
#define MyAppExeName "Rxn Bench.exe"
#define MyBuildDir "..\dist\Rxn Bench"

[Setup]
AppId={{BC249110-4E08-47C2-8719-3C8B1FC5D557}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=rxnbench_logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist-installer
OutputBaseFilename=Rxn-Bench-Setup-{#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
