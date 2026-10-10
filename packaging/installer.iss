; Inno Setup 스크립트 — 설치 파일(NewsClipping-Setup-<버전>.exe) 생성
;   iscc /DAppVersion=0.9 packaging\installer.iss
; 사용자: 설치 파일을 실행 → '다음' → 완료. 관리자 권한 없이 사용자 폴더에 설치되고
; 바탕화면과 시작 메뉴에 아이콘이 자동으로 만들어진다.

#ifndef AppVersion
  #define AppVersion "0.0"
#endif
#define AppName "뉴스 클리핑"
#define AppExe "NewsClipping.exe"

[Setup]
AppId={{7B4F6E52-3D3A-4B79-9C0E-5C1D9A6F2E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=hupers
AppPublisherURL=https://github.com/hupers77/ProjNewsClipping
DefaultDirName={autopf}\NewsClipping
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=NewsClipping-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
#if FileExists(SourcePath + "Korean.isl")
Name: "korean"; MessagesFile: "Korean.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Files]
Source: "..\dist\NewsClipping\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; 바탕화면 아이콘은 선택 없이 항상 만든다
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} 지금 실행"; Flags: nowait postinstall skipifsilent
