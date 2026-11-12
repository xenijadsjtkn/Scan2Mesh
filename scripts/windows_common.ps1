#requires -Version 5.1
# Shared helpers. Dot-sourcing this file never installs or starts anything.
Set-StrictMode -Version Latest

function Get-Scan2MeshPaths {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)
    if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA fehlt. Diese Starter sind fuer Windows vorgesehen.' }
    $localRoot = Join-Path $env:LOCALAPPDATA 'Scan2Mesh'
    [pscustomobject]@{
        ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
        LocalRoot = $localRoot
        Uv = Join-Path $localRoot 'tools\uv.exe'
        Venv = Join-Path $localRoot 'venv'
        Cache = Join-Path $localRoot 'cache\uv'
        BackendConfig = Join-Path $localRoot 'backend.json'
        Downloads = Join-Path $localRoot 'downloads'
        WslRoot = Join-Path $localRoot 'wsl'
    }
}

function Invoke-Scan2MeshNative {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [switch]$Capture,
        [switch]$AllowFailure
    )
    $previousOutputEncoding = $OutputEncoding
    $previousConsoleEncoding = [Console]::OutputEncoding
    try {
        # Windows PowerShell 5 otherwise decodes wslpath through the OEM code
        # page, corrupting non-ASCII Windows user names and scan file paths.
        $OutputEncoding = New-Object Text.UTF8Encoding($false)
        [Console]::OutputEncoding = $OutputEncoding
        if ($Capture) {
            $lines = @(& $FilePath @Arguments)
            $code = $LASTEXITCODE
            $output = ($lines -join "`n").Trim()
        }
        else {
            & $FilePath @Arguments | Out-Host
            $code = $LASTEXITCODE
            $output = ''
        }
    }
    finally {
        $OutputEncoding = $previousOutputEncoding
        [Console]::OutputEncoding = $previousConsoleEncoding
    }
    if ($code -ne 0 -and -not $AllowFailure) {
        throw ('{0} wurde mit Exitcode {1} beendet. Siehe Meldung oben.' -f $FilePath, $code)
    }
    [pscustomobject]@{ ExitCode = $code; Output = $output }
}

function Set-Scan2MeshFrontendEnvironment {
    param([Parameter(Mandatory = $true)]$Paths)
    $env:UV_PROJECT_ENVIRONMENT = $Paths.Venv
    $env:UV_CACHE_DIR = $Paths.Cache
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
}

function Read-Scan2MeshBackend {
    param([Parameter(Mandatory = $true)]$Paths)
    if (-not (Test-Path -LiteralPath $Paths.BackendConfig -PathType Leaf)) { return $null }
    try { $config = Get-Content -LiteralPath $Paths.BackendConfig -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw ('Die vorhandene Backend-Konfiguration ist unlesbar und wurde nicht veraendert: {0}' -f $Paths.BackendConfig) }
    foreach ($key in @('schema_version', 'wsl_distro', 'python')) {
        if ($null -eq $config -or $config.PSObject.Properties.Name -notcontains $key) {
            throw ('Ungueltige Backend-Konfiguration; Datei wurde nicht veraendert: {0}' -f $Paths.BackendConfig)
        }
    }
    if (-not ($config.schema_version -is [int] -or $config.schema_version -is [long]) -or $config.schema_version -ne 1 -or
        -not ($config.wsl_distro -is [string]) -or [string]::IsNullOrWhiteSpace($config.wsl_distro) -or
        $config.wsl_distro -match '[\x00\r\n]' -or
        -not ($config.python -is [string]) -or [string]::IsNullOrWhiteSpace($config.python) -or
        $config.python -match '[\x00\r\n]' -or -not $config.python.StartsWith('/')) {
        throw ('Ungueltige Backend-Konfiguration; Datei wurde nicht veraendert: {0}' -f $Paths.BackendConfig)
    }
    return $config
}

function Read-Scan2MeshVersions {
    param([Parameter(Mandatory = $true)]$Paths)
    $file = Join-Path $Paths.ProjectRoot 'setup\versions.json'
    $versions = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($versions.schema_version -ne 1) { throw ('Unbekannte Setup-Manifestversion: {0}' -f $file) }
    return $versions
}

function Save-Scan2MeshVerifiedDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Sha256,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if ($Sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Im Setup-Manifest fehlt eine gueltige SHA256-Pruefsumme.' }
    if (([Uri]$Url).Scheme -ne 'https') { throw 'Setup-Downloads muessen HTTPS verwenden.' }
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Sha256) { return $Destination }
    }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Destination)) | Out-Null
    $partial = $Destination + '.part'
    $previousProgress = $ProgressPreference
    try {
        $ProgressPreference = 'SilentlyContinue'
        Write-Host ('Herunterladen: {0}' -f $Url)
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $partial
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $Sha256) {
            throw ('SHA256-Pruefung fehlgeschlagen: {0}' -f $Url)
        }
        Move-Item -LiteralPath $partial -Destination $Destination -Force
    }
    finally {
        $ProgressPreference = $previousProgress
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    }
    return $Destination
}

function Convert-Scan2MeshWslPath {
    param([string]$Distro, [string]$WindowsPath)
    $result = Invoke-Scan2MeshNative -FilePath 'wsl.exe' -Arguments @(
        '--distribution', $Distro, '--user', 'root', '--exec', 'wslpath', '-a', '-u', $WindowsPath
    ) -Capture
    $converted = $result.Output
    if ([string]::IsNullOrWhiteSpace($converted) -or $converted.Contains("`n")) {
        throw ('WSL konnte den Pfad nicht eindeutig umwandeln: {0}' -f $WindowsPath)
    }
    return $converted
}
