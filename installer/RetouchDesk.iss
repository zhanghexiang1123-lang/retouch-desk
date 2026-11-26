#ifndef AppVersion
  #define AppVersion "0.5.0"
#endif

[Setup]
AppId={{DB2F07BA-521C-49AF-939D-DA097745F905}
AppName=Retouch Desk
AppVersion={#AppVersion}
AppPublisher=Retouch Desk
AppComments=本地图片文字精修工作台
VersionInfoDescription=Retouch Desk 安装程序
VersionInfoProductName=Retouch Desk
VersionInfoProductVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Retouch Desk
DefaultGroupName=Retouch Desk
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
UninstallDisplayName=Retouch Desk · 图片文字精修
UninstallDisplayIcon={app}\RetouchDesk.exe
OutputDir=..\release\installer
OutputBaseFilename=RetouchDesk-{#AppVersion}-Setup-x64
SetupIconFile=..\assets\app-icon.ico
WizardStyle=modern
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
InfoBeforeFile=安装须知.txt

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："

[Files]
Source: "..\release\RetouchDesk\*"; DestDir: "{app}"; Excludes: "sample.local.json"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Retouch Desk"; Filename: "{app}\RetouchDesk.exe"; WorkingDir: "{app}"
Name: "{group}\卸载 Retouch Desk"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Retouch Desk"; Filename: "{app}\RetouchDesk.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\RetouchDesk.exe"; Description: "启动 Retouch Desk"; Flags: nowait postinstall skipifsilent
