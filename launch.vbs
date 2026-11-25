Option Explicit
' HACKER RADIO - arranque silencioso.
' Lanza start.ps1 con la ventana de PowerShell oculta: sin consola y sin parpadeo.

Dim sh, fso, root, cmd
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
cmd  = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & root & "\start.ps1"""

sh.Run cmd, 0, False
