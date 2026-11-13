#define AppName "RPG 2.0"
#define AppVersion "2.0.0"
#define SourceDir GetEnv("RPG_PACKAGE_DIR")
#define ReleaseDir GetEnv("RPG_RELEASE_DIR")

[Setup]
AppId={{52695641-532D-5032-2D30-7838365F3634}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Rivas Pardo Lab | Biologia Mecanica
DefaultDirName={autopf}\RPG 2.0
DefaultGroupName=RPG 2.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
OutputDir={#ReleaseDir}
OutputBaseFilename=RPG-Windows-v2.0-x86_64-Setup
SetupIconFile=..\..\icon.ico
LicenseFile={#SourceDir}\LICENSE.txt
UninstallDisplayIcon={app}\RPG-2.0.exe
WizardStyle=modern

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RPG 2.0"; Filename: "{app}\RPG-2.0.exe"
Name: "{autodesktop}\RPG 2.0"; Filename: "{app}\RPG-2.0.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\RPG-2.0.exe"; Description: "Launch RPG 2.0"; Flags: nowait postinstall skipifsilent
