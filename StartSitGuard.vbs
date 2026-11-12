' SitGuard 启动器：无控制台窗口启动
' 优先使用装有依赖的 Python 3.13
Option Explicit
Dim fso, sh, base, pyw, py, cmd, rc
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)

pyw = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe"
py = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\python.exe"
If Not fso.FileExists(pyw) Then
    If fso.FileExists("C:\Python313\pythonw.exe") Then
        pyw = "C:\Python313\pythonw.exe"
        py = "C:\Python313\python.exe"
    Else
        pyw = "pythonw.exe"
        py = "python.exe"
    End If
End If

' 检查依赖，缺失则先安装
rc = sh.Run("""" & py & """ -c ""import cv2, PIL, pystray, mediapipe""", 0, True)
If rc <> 0 Then
    MsgBox "首次运行需要安装依赖（约 1-2 分钟，需要联网）。" & vbCrLf & _
           "点击确定后开始安装，完成后会自动启动。", vbInformation, "SitGuard"
    rc = sh.Run("""" & py & """ -m pip install --user opencv-python mediapipe pystray Pillow", 1, True)
    If rc <> 0 Then
        MsgBox "依赖安装失败，请手动运行：" & vbCrLf & _
               """" & py & """ -m pip install --user opencv-python mediapipe pystray Pillow", _
               vbCritical, "SitGuard"
        WScript.Quit 1
    End If
End If

cmd = """" & pyw & """ """ & base & "\main.py"""
sh.CurrentDirectory = base
sh.Run cmd, 0, False
