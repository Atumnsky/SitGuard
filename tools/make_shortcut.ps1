# Create a SitGuard shortcut on the Desktop (ASCII-only script for PS 5.1)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = Join-Path $desktop "SitGuard.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath = Join-Path $env:SystemRoot "System32\wscript.exe"
$sc.Arguments = '"' + (Join-Path $here "StartSitGuard.vbs") + '"'
$sc.WorkingDirectory = $here
$sc.IconLocation = Join-Path $here "sitguard\assets\sitguard.ico"
$sc.Description = "SitGuard"
$sc.Save()
Write-Host ("Created: " + $lnk)
