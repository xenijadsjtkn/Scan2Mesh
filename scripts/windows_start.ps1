#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InputFile,
    [ValidateSet('m', 'mm')]
    [string]$Units = 'm',
    [string]$OutputRoot
)
$ErrorActionPreference = 'Stop'

function Start-Scan2Mesh {
    $project = Split-Path -Parent $PSScriptRoot
    . (Join-Path $PSScriptRoot 'windows_common.ps1')
    $paths = Get-Scan2MeshPaths -ProjectRoot $project
    if (-not (Test-Path -LiteralPath $paths.Uv -PathType Leaf)) {
        throw 'Die Einrichtung fehlt. Zuerst Einrichten.cmd starten.'
    }
    $python = $env:SCAN2MESH_NKSR_PYTHON
    $distro = $env:SCAN2MESH_NKSR_WSL_DISTRO
    if (-not $python -or -not $distro) {
        $backend = Read-Scan2MeshBackend -Paths $paths
        if ($null -ne $backend) {
            if (-not $python) { $python = $backend.python }
            if (-not $distro) { $distro = $backend.wsl_distro }
        }
    }
    if (-not $python -or -not $distro) {
        throw 'Die NKSR-Einrichtung ist noch nicht abgeschlossen. Einrichten.cmd erneut starten.'
    }
    Set-Scan2MeshFrontendEnvironment -Paths $paths
    # Refresh the editable project location even if the repository ZIP was moved.
    Invoke-Scan2MeshNative -FilePath $paths.Uv -Arguments @('sync', '--frozen', '--no-dev', '--project', $project, '--python', '3.12') | Out-Null
    $frontend = Join-Path $paths.Venv 'Scripts\python.exe'
    $runnerArguments = @('-X', 'utf8', (Join-Path $project 'main.py'), '--units', $Units, '--nksr-python', $python, '--nksr-wsl-distro', $distro)
    if ($InputFile) { $runnerArguments += @('--input', $InputFile) }
    if ($OutputRoot) { $runnerArguments += @('--output-root', $OutputRoot) }
    Invoke-Scan2MeshNative -FilePath $frontend -Arguments $runnerArguments | Out-Null
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Start-Scan2Mesh }
    catch {
        Write-Host ('Scan2Mesh: ' + $_.Exception.Message) -ForegroundColor Red
        exit 1
    }
}
