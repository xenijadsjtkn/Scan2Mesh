#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$WslDistro = $env:SCAN2MESH_NKSR_WSL_DISTRO,
    [string]$NksrPython = $env:SCAN2MESH_NKSR_PYTHON,
    [ValidateSet("m", "mm")]
    [string]$Units = "m",
    [string]$OutputRoot = (Join-Path $env:LOCALAPPDATA "Scan2Mesh")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($WslDistro)) {
    $WslDistro = "Ubuntu-22.04"
}
if ([string]::IsNullOrWhiteSpace($NksrPython)) {
    throw "NKSR-Python fehlt. -NksrPython mit dem Linux-Pfad zur eingerichteten NKSR-Umgebung angeben."
}
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe wurde nicht gefunden. Dieser Starter verwendet Windows mit WSL."
}
if ([Threading.Thread]::CurrentThread.ApartmentState -ne "STA") {
    throw "Den Starter mit powershell.exe -NoProfile -STA -File .\nksr-direkt.ps1 ausfuehren."
}

$runner = Join-Path $PSScriptRoot "scripts\nksr_direct.py"
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Direktes NKSR-Skript fehlt: $runner"
}

Add-Type -AssemblyName System.Windows.Forms
$picker = New-Object System.Windows.Forms.OpenFileDialog
$picker.Title = "Direkter NKSR-Test: Punktwolke auswaehlen"
$picker.Filter = "Punktwolken|*.ply;*.pcd;*.pts;*.xyz;*.xyzn;*.xyzrgb|PLY-Dateien (*.ply)|*.ply|PCD-Dateien (*.pcd)|*.pcd"
$picker.CheckFileExists = $true
$picker.Multiselect = $false
$picker.RestoreDirectory = $true
try {
    if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host "Abgebrochen."
        return
    }
    $source = $picker.FileName
}
finally {
    $picker.Dispose()
}

$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
[IO.Directory]::CreateDirectory($OutputRoot) | Out-Null

function Convert-ToLinuxPath([string]$WindowsPath) {
    $lines = @(& wsl.exe --distribution $WslDistro --exec wslpath -a -u $WindowsPath)
    if ($LASTEXITCODE -ne 0 -or $lines.Count -ne 1) {
        throw "Windows-Pfad konnte nicht nach WSL umgewandelt werden: $WindowsPath"
    }
    $converted = ([string]$lines[0]).Trim()
    if ([string]::IsNullOrWhiteSpace($converted)) {
        throw "WSL lieferte einen leeren Dateipfad: $WindowsPath"
    }
    return $converted
}

$previousOutputEncoding = $OutputEncoding
$previousConsoleEncoding = [Console]::OutputEncoding
try {
    # wslpath emits UTF-8, including for Windows paths with non-ASCII names.
    $OutputEncoding = [Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = $OutputEncoding
    $linuxSource = Convert-ToLinuxPath $source
    $linuxRunner = Convert-ToLinuxPath $runner
    $linuxOutput = Convert-ToLinuxPath $OutputRoot

    Write-Host "Eingabe: $source"
    Write-Host "Koordinateneinheit: $Units"
    Write-Host "Direkter NKSR-Aufruf mit allen Originalpunkten."
    & wsl.exe --distribution $WslDistro --exec $NksrPython -u $linuxRunner --input $linuxSource --output-root $linuxOutput --units $Units
    if ($LASTEXITCODE -ne 0) {
        throw "Der direkte NKSR-Lauf ist fehlgeschlagen (Exitcode $LASTEXITCODE). Siehe Meldung oben."
    }
}
finally {
    $OutputEncoding = $previousOutputEncoding
    [Console]::OutputEncoding = $previousConsoleEncoding
}

Write-Host "Ergebnisse liegen in einem neuen nksr-direkt-Ordner unter: $OutputRoot"
Invoke-Item -LiteralPath $OutputRoot
