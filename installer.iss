[Setup]
AppName=WiFi Manager
AppVersion=1.0
DefaultDirName={autopf}\WifiManager
DefaultGroupName=WiFi Manager
OutputBaseFilename=WifiManagerSetup
OutputDir=Output
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\WifiManager.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\WiFi Manager"; Filename: "{app}\WifiManager.exe"
Name: "{autodesktop}\WiFi Manager"; Filename: "{app}\WifiManager.exe"

[Run]
Filename: "{app}\WifiManager.exe"; Description: "Run WiFi Manager"; Flags: nowait postinstall skipifsilent
