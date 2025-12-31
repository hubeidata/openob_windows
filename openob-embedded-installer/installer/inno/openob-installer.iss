#ifdef AppNameOverride
	#define AppName AppNameOverride
#else
	#define AppName "OpenOB"
#endif

#ifdef AppVersionOverride
	#define AppVersion AppVersionOverride
#else
	#define AppVersion "0.0.0"
#endif
#define AppPublisher "OpenOB"
#define AppURL ""

[Setup]
AppId={{A45F514A-BC7B-4A4B-ACD1-77F7C9B7C9B1}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\..\dist
OutputBaseFilename=OpenOB-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ChangesEnvironment=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\\Spanish.isl"

[Files]
Source: "..\..\packaging\openob_runtime\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\images\ob-logo.ico"; DestDir: "{app}\images"; Flags: ignoreversion

[Tasks]
Name: "addtopath"; Description: "Add OpenOB to PATH (current user)"; Flags: checkedonce
; Name: "installredisservice"; Description: "Install Redis as Windows Service (requires Administrator)"; Flags: unchecked

[Registry]
; Add {app}\bin to the current-user PATH if the task is selected.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
	ValueData: "{olddata};{app}\\bin"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}\\bin'))

[Icons]
Name: "{group}\OpenOB"; Filename: "{app}\bin\openob.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\images\ob-logo.ico"
Name: "{group}\OpenOB UI"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\ui\app.py"""; WorkingDir: "{app}"; IconFilename: "{app}\images\ob-logo.ico"
Name: "{autodesktop}\OpenOB UI"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\ui\app.py"""; WorkingDir: "{app}"; IconFilename: "{app}\images\ob-logo.ico"
; Name: "{group}\Start Redis (optional)"; Filename: "{app}\bin\redis-start.cmd"; WorkingDir: "{app}"

[Run]
Filename: "{app}\bin\openob.cmd"; Description: "Run OpenOB"; Flags: nowait postinstall skipifsilent
; If user selected the task, install and start Redis as a Windows service (requires UAC elevation)
; Filename: "{app}\bin\redis-install.cmd"; Description: "Install and start Redis as Windows service"; Flags: postinstall shellexec nowait; Tasks: installredisservice

[Code]
function NeedsAddPath(Dir: string): Boolean;
var
	Path: string;
begin
	if not RegQueryStringValue(HKCU, 'Environment', 'Path', Path) then
	begin
		Result := True;
		exit;
	end;

	Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Path) + ';') = 0;
end;
