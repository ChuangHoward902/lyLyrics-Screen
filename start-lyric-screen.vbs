Option Explicit

Dim shell, fso, root, ps1, args

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = fso.BuildPath(root, "start-lyric-screen.ps1")
args = "-NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """"

shell.Run "powershell.exe " & args, 0, False
