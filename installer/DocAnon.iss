#define AppVersion "0.2.1"
#ifdef TestBuild
  #define InstallerId "{{F6685F52-4CCA-4FDC-9F16-D3DBFF72EB42}"
  #define InstallerName "Doc Anon (verifica)"
  #define SetupSuffix "-test"
#else
  #define InstallerId "{{A45FA0C3-52DE-494D-8745-1EDDB0386945}"
  #define InstallerName "Doc Anon"
  #define SetupSuffix ""
#endif

[Setup]
AppId={#InstallerId}
AppName={#InstallerName}
AppVersion={#AppVersion}
AppVerName=Doc Anon {#AppVersion}
AppPublisher=Doc Anon
AppComments=Anonimizzazione locale dei documenti con revisione visuale
DefaultDirName={localappdata}\Programs\{#InstallerName}
DefaultGroupName={#InstallerName}
DisableDirPage=no
DisableProgramGroupPage=no
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible and not arm64
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=DocAnon-Setup-{#AppVersion}{#SetupSuffix}-x64
SetupIconFile=..\assets\doc-anon.ico
UninstallDisplayIcon={app}\DocAnon.exe
UninstallDisplayName={#InstallerName}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile=install-info.txt
CloseApplications=no
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=Installazione di Doc Anon
VersionInfoProductName=Doc Anon
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"; GroupDescription: "Collegamenti aggiuntivi:"; Flags: unchecked

[Files]
Source: "..\dist\DocAnon\*"; DestDir: "{app}"; Excludes: "LEGGIMI.txt"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LEGGIMI-installato.txt"; DestDir: "{app}"; DestName: "LEGGIMI.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\Doc Anon"; Filename: "{app}\DocAnon.exe"; WorkingDir: "{app}"
Name: "{group}\Istruzioni"; Filename: "{app}\LEGGIMI.txt"
Name: "{autodesktop}\Doc Anon"; Filename: "{app}\DocAnon.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\DocAnon.exe"; Description: "Avvia Doc Anon"; Flags: nowait postinstall skipifsilent

; No UninstallDelete: the uninstaller only removes installed program files.
; Downloaded resources in LocalAppData\DocAnon and exported user PDFs are preserved.
