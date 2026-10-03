; Inno Setup 6 Script for AstraRun 1.0.0-rc.2-dogfood
; Windows Intelligent Command Launcher & Desktop Agent

#define MyAppName "AstraRun"
#define MyAppVersion "1.0.0-rc.2-dogfood"
#define MyAppPublisher "Astra Engineering Team"
#define MyAppURL "https://github.com/astrarun/astrarun"
#define MyAppExeName "AstraRun.exe"

[Setup]
AppId={{C24B5D7A-A12E-4F42-87F9-5B264E21D0E4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
; Per-user installation: requires ZERO administrative privileges
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=AstraRun-Setup-{#MyAppVersion}
SetupIconFile=..\resources\icons\AstraRun.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start AstraRun automatically when signing in to Windows"; GroupDescription: "Windows Integration:"

[Files]
Source: "..\dist\AstraRun\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\icons\AstraRun.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\resources\icons\AstraRun.ico"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AstraRun"; ValueData: """{app}\{#MyAppExeName}"" --background"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Preserve user models and data by default on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Note: %LOCALAPPDATA%\AstraRun\models and data are preserved by default
  end;
end;
