#requires -Version 5.1
# Compatibility starter: the same workflow is now the normal main.py start.
[CmdletBinding()]
param(
    [string]$WslDistro = $env:SCAN2MESH_NKSR_WSL_DISTRO,
    [string]$NksrPython = $env:SCAN2MESH_NKSR_PYTHON,
    [ValidateSet("m", "mm")]
    [string]$Units = "m",
    [ValidateRange(1.0, 1.0)]
    [double]$DetailLevel = 1.0,
    [switch]$CompareTrim,
    [string]$OutputRoot = (Join-Path $env:LOCALAPPDATA "Scan2Mesh")
)

$ErrorActionPreference = "Stop"
$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA "Scan2Mesh\venv"
if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $env:LOCALAPPDATA "Scan2Mesh\cache\uv"
}
$runnerArguments = @("--units", $Units, "--output-root", $OutputRoot)
if ($WslDistro) { $runnerArguments += @("--nksr-wsl-distro", $WslDistro) }
if ($NksrPython) { $runnerArguments += @("--nksr-python", $NksrPython) }
# Highest detail and both trim exports are always enabled, also without flags.
& uv run --project $PSScriptRoot python (Join-Path $PSScriptRoot "main.py") @runnerArguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
