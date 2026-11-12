#requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$EnableWslOnly,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

. (Join-Path $PSScriptRoot 'windows_common.ps1')
$ErrorActionPreference = 'Stop'
$script:Scan2MeshSetupScript = $PSCommandPath

function Test-Scan2MeshAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Enable-Scan2MeshWsl {
    if (-not (Test-Scan2MeshAdministrator)) { throw 'WSL-Aktivierung benoetigt Administratorrechte.' }
    $enabled = Invoke-Scan2MeshNative -FilePath 'wsl.exe' -Arguments @('--install', '--no-distribution') -AllowFailure
    if ($enabled.ExitCode -notin @(0, 3010)) { throw ('WSL-Aktivierung fehlgeschlagen (Exitcode {0}).' -f $enabled.ExitCode) }
    return 3010
}

function Test-Scan2MeshWslReady {
    if (-not (Get-Command 'wsl.exe' -ErrorAction SilentlyContinue)) { return $false }
    $status = Invoke-Scan2MeshNative -FilePath 'wsl.exe' -Arguments @('--status') -Capture -AllowFailure
    return $status.ExitCode -eq 0
}

function Request-Scan2MeshWslEnable {
    if (Test-Scan2MeshAdministrator) { Enable-Scan2MeshWsl | Out-Null }
    else {
        # Only feature installation is elevated. The original user's files and
        # distributions are handled by the unelevated parent after reboot.
        $helper = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $script:Scan2MeshSetupScript), '-EnableWslOnly'
        )
        if ($helper.ExitCode -notin @(0, 3010)) { throw ('WSL-Aktivierung fehlgeschlagen (Exitcode {0}).' -f $helper.ExitCode) }
    }
    Write-Host 'WSL wurde vorbereitet. Windows jetzt selbst neu starten und danach Einrichten.cmd erneut oeffnen.'
    Write-Host 'Es wird kein automatischer Neustart ausgeloest.'
    return 3010
}

function Install-Scan2MeshUv {
    param($Paths, $Versions)
    if (Test-Path -LiteralPath $Paths.Uv -PathType Leaf) {
        $installed = Invoke-Scan2MeshNative -FilePath $Paths.Uv -Arguments @('--version') -Capture -AllowFailure
        if ($installed.ExitCode -eq 0 -and $installed.Output -match ('^uv ' + [regex]::Escape($Versions.uv.version) + '(\s|$)')) { return }
    }
    $archive = Join-Path $Paths.Downloads ('uv-' + $Versions.uv.version + '-windows.zip')
    Save-Scan2MeshVerifiedDownload -Url $Versions.uv.url -Sha256 $Versions.uv.sha256 -Destination $archive | Out-Null
    $unpacked = Join-Path $Paths.Downloads ('uv-' + $Versions.uv.version + '-unpacked')
    [IO.Directory]::CreateDirectory($unpacked) | Out-Null
    try {
        Expand-Archive -LiteralPath $archive -DestinationPath $unpacked -Force
        $executables = @(Get-ChildItem -LiteralPath $unpacked -Filter 'uv.exe' -File -Recurse)
        if ($executables.Count -ne 1) { throw 'Das gepruefte uv-Archiv enthaelt keinen eindeutigen uv.exe-Starter.' }
        [IO.Directory]::CreateDirectory((Split-Path -Parent $Paths.Uv)) | Out-Null
        Copy-Item -LiteralPath $executables[0].FullName -Destination $Paths.Uv -Force
    }
    finally {
        if (Test-Path -LiteralPath $unpacked) { Remove-Item -LiteralPath $unpacked -Recurse -Force }
    }
}

function Test-Scan2MeshBackend {
    param($Paths, [string]$Distro, [string]$Python)
    $checker = Convert-Scan2MeshWslPath -Distro $Distro -WindowsPath (Join-Path $Paths.ProjectRoot 'scripts\check_nksr.py')
    Invoke-Scan2MeshNative -FilePath 'wsl.exe' -Arguments @(
        '--distribution', $Distro, '--exec', $Python, '-u', $checker, '--smoke'
    ) | Out-Null
}

function Get-Scan2MeshConfiguredBackend {
    param($Paths)
    $saved = Read-Scan2MeshBackend -Paths $Paths
    $distro = $env:SCAN2MESH_NKSR_WSL_DISTRO
    $python = $env:SCAN2MESH_NKSR_PYTHON
    if ($distro -or $python) {
        if (-not $distro) { $distro = if ($saved) { $saved.wsl_distro } else { 'Ubuntu-22.04' } }
        if (-not $python) {
            # Use the same discovery as Play/F5 without changing that distro.
            $probe = "from scan2mesh.nksr_runtime import _discover_python; import sys; print(_discover_python(['wsl.exe', '--distribution', sys.argv[1], '--exec', 'python3']))"
            $found = Invoke-Scan2MeshNative -FilePath (Join-Path $Paths.Venv 'Scripts\python.exe') -Arguments @('-X', 'utf8', '-c', $probe, $distro) -Capture
            $python = $found.Output
        }
        return [pscustomobject]@{ schema_version = 1; wsl_distro = $distro; python = $python }
    }
    return $saved
}

function Save-Scan2MeshBackend {
    param($Paths, $Backend)
    [IO.Directory]::CreateDirectory($Paths.LocalRoot) | Out-Null
    $temporary = $Paths.BackendConfig + '.tmp'
    $json = $Backend | ConvertTo-Json
    [IO.File]::WriteAllText($temporary, $json, (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $Paths.BackendConfig -Force
}

function Install-Scan2Mesh {
    param([string]$Repository)
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
        throw 'Einrichten.cmd unter 64-Bit-Windows ausfuehren.'
    }
    if (-not (Test-Scan2MeshWslReady)) { return Request-Scan2MeshWslEnable }

    $paths = Get-Scan2MeshPaths -ProjectRoot $Repository
    $versions = Read-Scan2MeshVersions -Paths $paths
    Install-Scan2MeshUv -Paths $paths -Versions $versions
    Set-Scan2MeshFrontendEnvironment -Paths $paths
    Invoke-Scan2MeshNative -FilePath $paths.Uv -Arguments @('sync', '--frozen', '--no-dev', '--project', $paths.ProjectRoot, '--python', '3.12') | Out-Null

    $configured = Get-Scan2MeshConfiguredBackend -Paths $paths
    if ($configured) {
        Write-Host ('Vorhandene NKSR-Umgebung pruefen: {0}' -f $configured.wsl_distro)
        # Never repair or install packages in an externally configured distro.
        Test-Scan2MeshBackend -Paths $paths -Distro $configured.wsl_distro -Python $configured.python
        Save-Scan2MeshBackend -Paths $paths -Backend $configured
        Write-Host 'Einrichtung abgeschlossen. Starten.cmd oeffnet die Dateiauswahl.'
        return 0
    }

    $distro = 'Scan2Mesh-NKSR'
    $installDirectory = Join-Path $paths.WslRoot $distro
    $ownership = Join-Path $installDirectory 'scan2mesh-managed.json'
    $listed = Invoke-Scan2MeshNative -FilePath 'wsl.exe' -Arguments @('--list', '--quiet') -Capture
    $names = @($listed.Output.Replace("`0", '') -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($names -contains $distro) {
        if (-not (Test-Path -LiteralPath $ownership -PathType Leaf)) {
            throw 'Eine Distribution Scan2Mesh-NKSR existiert bereits, ist aber nicht als diese Einrichtung markiert. Sie wurde nicht veraendert. Vorhandene NKSR-Pfade ausdruecklich konfigurieren.'
        }
    }
    else {
        $rootfs = Join-Path $paths.Downloads ('ubuntu-' + $versions.ubuntu.release + '-rootfs.tar.gz')
        Save-Scan2MeshVerifiedDownload -Url $versions.ubuntu.url -Sha256 $versions.ubuntu.sha256 -Destination $rootfs | Out-Null
        [IO.Directory]::CreateDirectory($installDirectory) | Out-Null
        Invoke-Scan2MeshNative -FilePath 'wsl.exe' -Arguments @('--import', $distro, $installDirectory, $rootfs, '--version', '2') | Out-Null
        [IO.File]::WriteAllText($ownership, '{"schema_version":1,"owner":"Scan2Mesh"}', (New-Object Text.UTF8Encoding($false)))
    }

    Write-Host 'NVIDIA-GPU in WSL pruefen ...'
    Invoke-Scan2MeshNative -FilePath 'wsl.exe' -Arguments @('--distribution', $distro, '--user', 'root', '--exec', '/usr/lib/wsl/lib/nvidia-smi', '-L') | Out-Null
    $installer = Convert-Scan2MeshWslPath -Distro $distro -WindowsPath (Join-Path $paths.ProjectRoot 'scripts\install_nksr.sh')
    $manifest = Convert-Scan2MeshWslPath -Distro $distro -WindowsPath (Join-Path $paths.ProjectRoot 'setup\versions.json')
    Write-Host 'Separate NKSR-Umgebung aufbauen. Downloads und CUDA-Kompilierung koennen laenger dauern.'
    Invoke-Scan2MeshNative -FilePath 'wsl.exe' -Arguments @(
        '--distribution', $distro, '--user', 'root', '--exec', 'bash', $installer,
        '--prefix', $versions.backend.prefix, '--manifest', $manifest
    ) | Out-Null
    # The backend installer itself finishes with a real reconstruction smoke
    # test. Publish local selection only after that process reports success.
    $backend = [pscustomobject]@{
        schema_version = 1; wsl_distro = $distro; python = $versions.backend.python
    }
    Save-Scan2MeshBackend -Paths $paths -Backend $backend
    Write-Host 'Einrichtung abgeschlossen. Starten.cmd oeffnet die Dateiauswahl; Play/F5 verwendet dieselbe Umgebung.'
    return 0
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        if ($EnableWslOnly) { exit (Enable-Scan2MeshWsl) }
        exit (Install-Scan2Mesh -Repository $ProjectRoot)
    }
    catch {
        Write-Host ('Einrichtung fehlgeschlagen: ' + $_.Exception.Message) -ForegroundColor Red
        exit 1
    }
}
