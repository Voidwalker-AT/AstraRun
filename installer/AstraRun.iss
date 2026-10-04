; Inno Setup 6 Script for AstraRun 1.0.0-rc.5a-dogfood
; Windows Intelligent Command Launcher & Desktop Agent

#define MyAppName "AstraRun"
#define MyAppVersion "1.0.0-rc.5a-dogfood"
#define MyAppURL "https://github.com/astrarun/astrarun"
#define MyAppExeName "AstraRun.exe"

[Setup]
AppId={{C24B5D7A-A12E-4F42-87F9-5B264E21D0E4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
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
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoDescription=AstraRun - Windows Intelligent Command Launcher & Desktop Agent
VersionInfoVersion=1.0.5.1
VersionInfoTextVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (C) 2026
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart"; Description: "Start AstraRun automatically when signing in to Windows"; GroupDescription: "Windows Integration:"

[Files]
Source: "..\dist\AstraRun\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\resources\icons\AstraRun.ico"; DestDir: "{app}\resources\icons"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AstraRun"; ValueData: """{app}\{#MyAppExeName}"" --background"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Dedicated uninstaller flow with active-task detection, graceful shutdown, and component ownership options
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  ExePath: String;
begin
  Result := True;
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  if FileExists(ExePath) then
  begin
    if Exec(ExePath, '--uninstall-ui', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
    begin
      if ResultCode <> 0 then
      begin
        // User chose to cancel uninstallation
        Result := False;
        Exit;
      end;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PlanTxt: String;
  Lines: TArrayOfString;
  I: Integer;
  TargetDir: String;
  AppDataRoot: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppDataRoot := ExpandConstant('{localappdata}\AstraRun');
    PlanTxt := AppDataRoot + '\data\uninstall_dirs_to_remove.txt';

    // 1. Remove user-selected directories from uninstallation plan
    if FileExists(PlanTxt) then
    begin
      if LoadStringsFromFile(PlanTxt, Lines) then
      begin
        for I := 0 to GetArrayLength(Lines) - 1 do
        begin
          TargetDir := Trim(Lines[I]);
          // Strict security containment: Only delete paths strictly inside %LOCALAPPDATA%\AstraRun
          if (Pos(LowerCase(AppDataRoot), LowerCase(TargetDir)) = 1) and (Length(TargetDir) > Length(AppDataRoot)) then
          begin
            if DirExists(TargetDir) then
              DelTree(TargetDir, True, True, True)
            else if FileExists(TargetDir) then
              DeleteFile(TargetDir);
          end;
        end;
      end;
      DeleteFile(PlanTxt);
      DeleteFile(AppDataRoot + '\data\uninstall_plan.json');
    end;

    // 2. Clean HKCU autostart registry entry
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'AstraRun');

    // 3. Clean temporary summon triggers and state
    DeleteFile(AppDataRoot + '\data\astrarun_summon.trigger');
    DeleteFile(AppDataRoot + '\data\astrarun_state.json');
    DeleteFile(AppDataRoot + '\data\last_gasp.json');
  end;
end;
