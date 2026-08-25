Option Explicit

Dim fileSystem, scriptFolder, command, shell
Set fileSystem = CreateObject("Scripting.FileSystemObject")
scriptFolder = fileSystem.GetParentFolderName(WScript.ScriptFullName)
command = Chr(34) & fileSystem.BuildPath(scriptFolder, "ipc_auto_update.cmd") & Chr(34)

Set shell = CreateObject("WScript.Shell")
shell.Run command, 0, True
