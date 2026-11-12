' 创建/删除 SitGuard 开机自启快捷方式
' 用法：cscript //nologo MakeShortcut.vbs create|delete [快捷方式路径]
Option Explicit
Dim shell, fso, action, lnkPath, appDir, pythonw, python, args
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

If WScript.Arguments.Count < 2 Then
    WScript.Echo "usage: MakeShortcut.vbs create|delete <shortcut path>"
    WScript.Quit 2
End If
action = LCase(WScript.Arguments(0))
lnkPath = WScript.Arguments(1)

If action = "delete" Then
    If fso.FileExists(lnkPath) Then
        fso.DeleteFile lnkPath, True
    End If
    WScript.Echo "ok"
    WScript.Quit 0
End If

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe"
python = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\python.exe"
If Not fso.FileExists(pythonw) Then
    If fso.FileExists("C:\Python313\pythonw.exe") Then
        pythonw = "C:\Python313\pythonw.exe"
        python = "C:\Python313\python.exe"
    Else
        pythonw = "pythonw.exe"
        python = "python.exe"
    End If
End If

Dim sc
Set sc = shell.CreateShortcut(lnkPath)
sc.TargetPath = pythonw
sc.Arguments = """" & appDir & "\main.py"" --minimized"
sc.WorkingDirectory = appDir
sc.IconLocation = appDir & "\sitguard\assets\sitguard.ico"
sc.WindowStyle = 7
sc.Description = "SitGuard 久坐提醒"
sc.Save
WScript.Echo "ok"
