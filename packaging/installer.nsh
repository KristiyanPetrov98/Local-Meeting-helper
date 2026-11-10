!include "LogicLib.nsh"

!macro customInstall
  Push $R0
  Push $R1
  Push $R2
  ; Install the signed Microsoft runtime when a sufficiently recent x64 runtime
  ; is absent. Windows may request elevation; never weaken OS policy silently.
  SetRegView 64
  ReadRegDWORD $R0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
  ReadRegDWORD $R1 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Minor"
  ${If} $R0 != 1
  ${OrIf} $R1 < 44
    ClearErrors
    ExecWait '"$INSTDIR\resources\runtime\vcredist\vc_redist.x64.exe" /install /quiet /norestart' $R2
    ${If} ${Errors}
      MessageBox MB_OK|MB_ICONSTOP "The Microsoft C++ runtime installer could not start. Run PM Copilot setup again."
      Abort
    ${EndIf}
    ${If} $R2 == 3010
      SetRebootFlag true
    ${ElseIf} $R2 != 0
    ${AndIf} $R2 != 1638
      MessageBox MB_OK|MB_ICONSTOP "The Microsoft C++ runtime could not be installed (code $R2). Allow the Windows permission prompt and run setup again."
      Abort
    ${EndIf}
  ${EndIf}
  Pop $R2
  Pop $R1
  Pop $R0
!macroend
