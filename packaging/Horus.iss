#define AppName "Horus"
#define AppVersion "0.16.0"

[Setup]
AppId={{3F0B5D6D-E749-4F97-8B97-75A50CC0B029}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Horus
DefaultDirName={localappdata}\Programs\Horus
DefaultGroupName=Horus
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=HorusSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Horus.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\Horus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start Horus when I sign in"; Flags: unchecked

[Icons]
Name: "{autoprograms}\Horus"; Filename: "{app}\Horus.exe"
Name: "{autodesktop}\Horus"; Filename: "{app}\Horus.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Horus"; ValueData: """{app}\Horus.exe"" --service"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Horus.exe"; Description: "Configure Horus"; Flags: nowait postinstall skipifsilent
