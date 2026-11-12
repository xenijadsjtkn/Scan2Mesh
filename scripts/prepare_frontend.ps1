#requires -Version 5.1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows_common.ps1')
try {
    $project = Split-Path -Parent $PSScriptRoot
    $paths = Get-Scan2MeshPaths -ProjectRoot $project
    Set-Scan2MeshFrontendEnvironment -Paths $paths
    $uv = $paths.Uv
    if (-not (Test-Path -LiteralPath $uv -PathType Leaf)) {
        $existing = Get-Command 'uv' -ErrorAction SilentlyContinue
        if (-not $existing) { throw 'Zuerst Einrichten.cmd ausfuehren; uv wurde noch nicht eingerichtet.' }
        $uv = $existing.Source
    }
    Invoke-Scan2MeshNative -FilePath $uv -Arguments @('sync', '--frozen', '--no-dev', '--project', $project, '--python', '3.12') | Out-Null
}
catch {
    Write-Host ('Vorbereitung fehlgeschlagen: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
