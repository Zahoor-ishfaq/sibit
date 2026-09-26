; Inno Setup script for Sibit — builds dist\Sibit-Setup-1.0.0.exe
;
;   1. cd frontend && npm run build
;   2. .venv\Scripts\pyinstaller build\sibit.spec --noconfirm --distpath dist --workpath build\work
;   3. "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" build\sibit-installer.iss

#define AppName "Sibit"
#define AppVersion "1.0.0"
#define AppExe "Sibit.exe"

[Setup]
AppId={{6E1B7A3C-5D2F-4C8B-9A41-51B17F1E0C0A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Sibit
AppComments=Firewall Migration Rule Verifier — See every rule. Miss nothing.
VersionInfoDescription=Sibit Setup
VersionInfoVersion={#AppVersion}
; Per-user install by default: no admin rights needed. The user can choose "all users" instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile=..\brand\sibit.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} — Firewall Migration Rule Verifier
WizardStyle=modern
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp
OutputDir=..\dist
OutputBaseFilename=Sibit-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=2
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Sibit\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Firewall Migration Rule Verifier"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nSibit compares a Cisco ASA running config with the migrated FTD Access Control Policy and highlights every rule that changed — especially rules that became less secure.%n%nSibit runs 100% offline: your firewall files never leave this computer.
FinishedLabel=Setup has finished installing [name].%n%nSibit opens in your web browser. A small console window stays open while it runs — close it to quit Sibit.
