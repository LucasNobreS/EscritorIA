#ifndef AppVersion
  #define AppVersion "0.45.0"
#endif

[Setup]
AppId={{7F3FEABC-34EE-4571-BDF9-6DB70710B52A}
AppName=EscritorIA
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\AtelieIA-Setup
DefaultGroupName=EscritorIA
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename=EscritorIA-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=web\brand\escritoria.ico
UninstallDisplayIcon={app}\EscritorIA.exe
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; Flags: checkedonce

[Files]
Source: "dist\EscritorIA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "Instalar.bat"

[Icons]
Name: "{userdesktop}\EscritorIA"; Filename: "{app}\EscritorIA.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userprograms}\EscritorIA"; Filename: "{app}\EscritorIA.exe"; WorkingDir: "{app}"

Name: "{userprograms}\Restaurar EscritorIA"; Filename: "{app}\EscritorIA.exe"; Parameters: "--restore"; WorkingDir: "{app}"

[Run]
Filename: "{app}\EscritorIA.exe"; Description: "Abrir EscritorIA"; Flags: nowait postinstall skipifsilent

; User data in LocalAppData\EscritorIA is deliberately outside this installer.
; No UninstallDelete entry may remove that folder.
