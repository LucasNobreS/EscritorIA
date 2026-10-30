$ErrorActionPreference = 'Stop'
# Keep this portable folder in its final location before creating the shortcut.
$launcher = Join-Path $PSScriptRoot 'Iniciar.bat'
if (-not (Test-Path -LiteralPath $launcher)) { throw 'Extraia o ZIP completo antes de continuar.' }
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'EscritorIA.lnk'
# Never replace an existing shortcut, which may belong to another installation.
$index = 2
while (Test-Path -LiteralPath $shortcutPath) {
    $shortcutPath = Join-Path $desktop ("EscritorIA ($index).lnk")
    $index++
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Abrir o escritorio local EscritorIA'
$icon = Join-Path $PSScriptRoot 'web\brand\escritoria.ico'
if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = '"' + $icon + '",0' }
$shortcut.Save()
Write-Host 'Atalho criado. Mantenha a pasta do aplicativo neste local.'
