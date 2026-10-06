' Starts DiscordDrive in a hidden window (no console stays open).
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

curDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = curDir
WshShell.Run "cmd /c """"" & curDir & "\DiscordDrive.cmd"" mount""", 0, False
