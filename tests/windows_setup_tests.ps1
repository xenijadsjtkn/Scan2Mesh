#requires -Version 5.1
# No Pester or Windows installation required: process boundaries are mocked.
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
. (Join-Path $repository 'scripts/windows_setup.ps1')

function Assert-Scan2MeshTest {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw ('ASSERT: ' + $Message) }
}

function Assert-Scan2MeshThrows {
    param([scriptblock]$Action, [string]$Expected)
    try { & $Action | Out-Null }
    catch {
        Assert-Scan2MeshTest ($_.Exception.Message -like ('*' + $Expected + '*')) ('Unexpected exception: ' + $_.Exception.Message)
        return
    }
    throw ('ASSERT: Expected failure containing: ' + $Expected)
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('scan2mesh-setup-tests-' + [Guid]::NewGuid().ToString('N'))
$previousLocal = $env:LOCALAPPDATA
$previousOS = $env:OS
$previousDistro = $env:SCAN2MESH_NKSR_WSL_DISTRO
$previousPython = $env:SCAN2MESH_NKSR_PYTHON
$functions = @{}
foreach ($name in @('Invoke-Scan2MeshNative', 'Test-Scan2MeshAdministrator', 'Test-Scan2MeshWslReady', 'Request-Scan2MeshWslEnable', 'Install-Scan2MeshUv', 'Read-Scan2MeshVersions', 'Get-Scan2MeshConfiguredBackend', 'Convert-Scan2MeshWslPath', 'Save-Scan2MeshVerifiedDownload')) {
    $functions[$name] = (Get-Item ('Function:\' + $name)).ScriptBlock
}

try {
    [IO.Directory]::CreateDirectory($temporary) | Out-Null
    $env:LOCALAPPDATA = $temporary
    $env:OS = 'Windows_NT'
    Remove-Item Env:SCAN2MESH_NKSR_WSL_DISTRO -ErrorAction SilentlyContinue
    Remove-Item Env:SCAN2MESH_NKSR_PYTHON -ErrorAction SilentlyContinue
    $paths = Get-Scan2MeshPaths -ProjectRoot $repository

    # Native UTF-8 text must round-trip and neither a nonzero return nor an
    # exception may leave the caller's process-wide console encoding changed.
    $consoleBefore = [Console]::OutputEncoding.CodePage
    $nativeScript = '[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false); [Console]::Write([char]196); exit 7'
    $native = Invoke-Scan2MeshNative -FilePath (Get-Process -Id $PID).Path -Arguments @('-NoLogo', '-NoProfile', '-Command', $nativeScript) -Capture -AllowFailure
    Assert-Scan2MeshTest ($native.ExitCode -eq 7 -and $native.Output -eq [string][char]196) 'Native UTF8 text or exit code changed'
    Assert-Scan2MeshTest ([Console]::OutputEncoding.CodePage -eq $consoleBefore) 'Console encoding was not restored'
    Assert-Scan2MeshThrows {
        Invoke-Scan2MeshNative -FilePath (Get-Process -Id $PID).Path -Arguments @('-NoLogo', '-NoProfile', '-Command', 'exit 9') -Capture
    } 'Exitcode 9'
    Assert-Scan2MeshTest ([Console]::OutputEncoding.CodePage -eq $consoleBefore) 'Encoding was not restored after failure'

    # Invalid configuration is diagnosed and remains byte-for-byte unchanged.
    [IO.Directory]::CreateDirectory($paths.LocalRoot) | Out-Null
    [IO.File]::WriteAllText($paths.BackendConfig, '{"schema_version":1}', (New-Object Text.UTF8Encoding($false)))
    Assert-Scan2MeshThrows { Read-Scan2MeshBackend -Paths $paths } 'nicht veraendert'
    Assert-Scan2MeshTest ((Get-Content -LiteralPath $paths.BackendConfig -Raw) -eq '{"schema_version":1}') 'Invalid config was changed'
    Remove-Item -LiteralPath $paths.BackendConfig

    foreach ($invalid in @(
        '{"schema_version":true,"wsl_distro":"Ubuntu","python":"/opt/python"}',
        '{"schema_version":1,"wsl_distro":"Ubuntu","python":"relative/python"}',
        '{"schema_version":1,"wsl_distro":"Ubuntu\nOther","python":"/opt/python"}',
        '{"schema_version":1,"wsl_distro":"Ubuntu","python":"/opt/python\u0000"}'
    )) {
        [IO.File]::WriteAllText($paths.BackendConfig, $invalid, (New-Object Text.UTF8Encoding($false)))
        Assert-Scan2MeshThrows { Read-Scan2MeshBackend -Paths $paths } 'nicht veraendert'
    }
    Remove-Item -LiteralPath $paths.BackendConfig

    # A mismatched cached archive is never treated as a verified download;
    # a failed replacement also leaves the existing cache untouched.
    $download = Join-Path $temporary 'test.zip'
    [IO.File]::WriteAllText($download, 'old cache')
    function Invoke-WebRequest { param([switch]$UseBasicParsing, $Uri, $OutFile) [IO.File]::WriteAllText($OutFile, 'wrong download') }
    Assert-Scan2MeshThrows {
        Save-Scan2MeshVerifiedDownload -Url 'https://example.invalid/artifact.zip' -Sha256 ('0' * 64) -Destination $download
    } 'SHA256'
    Assert-Scan2MeshTest ((Get-Content -LiteralPath $download -Raw) -eq 'old cache') 'Unverified download replaced cache'
    Assert-Scan2MeshTest (-not (Test-Path -LiteralPath ($download + '.part'))) 'Partial download was not cleaned'
    Remove-Item Function:\Invoke-WebRequest

    # uv includes optional platform/build text after its version; a matching
    # managed binary must not trigger another download on every setup run.
    [IO.Directory]::CreateDirectory((Split-Path -Parent $paths.Uv)) | Out-Null
    [IO.File]::WriteAllText($paths.Uv, 'mock executable')
    $script:uvProbes = 0
    function Invoke-Scan2MeshNative {
        param($FilePath, $Arguments, [switch]$Capture, [switch]$AllowFailure)
        $script:uvProbes += 1
        return [pscustomobject]@{ ExitCode = 0; Output = 'uv 0.12.23 (x86_64-pc-windows-msvc)' }
    }
    Install-Scan2MeshUv -Paths $paths -Versions ([pscustomobject]@{ uv = [pscustomobject]@{ version = '0.12.23' } })
    Assert-Scan2MeshTest ($script:uvProbes -eq 1) 'uv version was not reused'

    # Native WSL reboot-needed success is accepted; no reboot command is used.
    function Test-Scan2MeshAdministrator { return $true }
    $script:commands = @()
    function Invoke-Scan2MeshNative {
        param($FilePath, $Arguments, [switch]$Capture, [switch]$AllowFailure)
        $script:commands += ,@($FilePath, $Arguments)
        return [pscustomobject]@{ ExitCode = 3010; Output = '' }
    }
    Assert-Scan2MeshTest ((Enable-Scan2MeshWsl) -eq 3010) 'Expected reboot-needed exit'
    Assert-Scan2MeshTest (($script:commands[0][1] -join ' ') -eq '--install --no-distribution') 'Unexpected WSL flags or restart'

    # The orchestration stops before downloading or writing config when WSL
    # needs setup/reboot. No source build runs in this branch.
    function Test-Scan2MeshWslReady { return $false }
    function Request-Scan2MeshWslEnable { return 3010 }
    function Install-Scan2MeshUv { throw 'Must not download before reboot' }
    Assert-Scan2MeshTest ((Install-Scan2Mesh -Repository $repository) -eq 3010) 'Setup failed to propagate reboot status'
    Assert-Scan2MeshTest (-not (Test-Path -LiteralPath $paths.BackendConfig)) 'Config was published before setup'

    # An external installation receives only smoke validation. If validation
    # fails, no package installation/import or config replacement is attempted.
    function Test-Scan2MeshWslReady { return $true }
    function Install-Scan2MeshUv { }
    function Read-Scan2MeshVersions { return [pscustomobject]@{ schema_version = 1 } }
    function Get-Scan2MeshConfiguredBackend {
        return [pscustomobject]@{ schema_version = 1; wsl_distro = 'Existing User Distro'; python = '/home/user/custom/python' }
    }
    function Convert-Scan2MeshWslPath { param($Distro, $WindowsPath) return '/repo/check_nksr.py' }
    $script:commands = @()
    function Invoke-Scan2MeshNative {
        param($FilePath, $Arguments, [switch]$Capture, [switch]$AllowFailure)
        $script:commands += ,@($FilePath, $Arguments)
        if ($FilePath -eq 'wsl.exe') {
            Assert-Scan2MeshTest (($Arguments -join ' ') -like '*Existing User Distro*--smoke') 'External distro was modified'
            throw 'test: GPU smoke failed'
        }
        return [pscustomobject]@{ ExitCode = 0; Output = '' }
    }
    Assert-Scan2MeshThrows { Install-Scan2Mesh -Repository $repository } 'GPU smoke failed'
    Assert-Scan2MeshTest ($script:commands.Count -eq 2) 'Unexpected package/import commands for external environment'
    Assert-Scan2MeshTest (-not (Test-Path -LiteralPath $paths.BackendConfig)) 'Failed external backend was selected'

    # Only a successful external smoke check publishes its local selection.
    function Invoke-Scan2MeshNative {
        param($FilePath, $Arguments, [switch]$Capture, [switch]$AllowFailure)
        return [pscustomobject]@{ ExitCode = 0; Output = '' }
    }
    Assert-Scan2MeshTest ((Install-Scan2Mesh -Repository $repository) -eq 0) 'Successful external setup failed'
    $saved = Read-Scan2MeshBackend -Paths $paths
    Assert-Scan2MeshTest ($saved.wsl_distro -eq 'Existing User Distro') 'Wrong distro saved'
    Assert-Scan2MeshTest ($saved.python -eq '/home/user/custom/python') 'Wrong interpreter saved'
    Remove-Item -LiteralPath $paths.BackendConfig

    # A first installation creates only its dedicated distribution. A failed
    # native build publishes no backend.json; rerunning reuses the owned distro.
    function Get-Scan2MeshConfiguredBackend { return $null }
    function Read-Scan2MeshVersions {
        return [pscustomobject]@{
            schema_version = 1
            ubuntu = [pscustomobject]@{ release = '22.04'; url = 'https://example.invalid/rootfs'; sha256 = ('0' * 64) }
            backend = [pscustomobject]@{ prefix = '/opt/scan2mesh'; python = '/opt/scan2mesh/envs/nksr/bin/python' }
        }
    }
    function Save-Scan2MeshVerifiedDownload {
        param($Url, $Sha256, $Destination)
        [IO.Directory]::CreateDirectory((Split-Path -Parent $Destination)) | Out-Null
        [IO.File]::WriteAllText($Destination, 'test-only rootfs')
        return $Destination
    }
    function Convert-Scan2MeshWslPath { param($Distro, $WindowsPath) return ('/repo/' + [IO.Path]::GetFileName($WindowsPath)) }
    $script:commands = @()
    $script:managedImported = $false
    $script:failBuild = $true
    function Invoke-Scan2MeshNative {
        param($FilePath, $Arguments, [switch]$Capture, [switch]$AllowFailure)
        $script:commands += ,@($FilePath, $Arguments)
        if ($Arguments -contains '--list') {
            $list = 'Personal Ubuntu'
            if ($script:managedImported) { $list += "`nScan2Mesh-NKSR" }
            return [pscustomobject]@{ ExitCode = 0; Output = $list }
        }
        if ($Arguments -contains '--import') {
            Assert-Scan2MeshTest ($Arguments[1] -eq 'Scan2Mesh-NKSR') 'Changed another distribution'
            $script:managedImported = $true
        }
        if ($Arguments -contains 'bash' -and $script:failBuild) { throw 'test: native build failed' }
        return [pscustomobject]@{ ExitCode = 0; Output = '' }
    }
    Assert-Scan2MeshThrows { Install-Scan2Mesh -Repository $repository } 'native build failed'
    Assert-Scan2MeshTest (-not (Test-Path -LiteralPath $paths.BackendConfig)) 'Failed managed build was selected'
    Assert-Scan2MeshTest $script:managedImported 'Managed distro was not created'
    $imports = @($script:commands | Where-Object { $_[1] -contains '--import' })
    Assert-Scan2MeshTest ($imports.Count -eq 1) 'Unexpected import count'
    $script:failBuild = $false
    $script:commands = @()
    Assert-Scan2MeshTest ((Install-Scan2Mesh -Repository $repository) -eq 0) 'Retry did not complete'
    $imports = @($script:commands | Where-Object { $_[1] -contains '--import' })
    Assert-Scan2MeshTest ($imports.Count -eq 0) 'Retry reimported a distro'
    Assert-Scan2MeshTest ((Read-Scan2MeshBackend -Paths $paths).wsl_distro -eq 'Scan2Mesh-NKSR') 'Managed backend not selected'

    # An existing same-named distro without this install's ownership marker is
    # never silently adopted, unregistered or overwritten.
    Remove-Item -LiteralPath $paths.BackendConfig
    Remove-Item -LiteralPath (Join-Path (Join-Path $paths.WslRoot 'Scan2Mesh-NKSR') 'scan2mesh-managed.json')
    $script:commands = @()
    Assert-Scan2MeshThrows { Install-Scan2Mesh -Repository $repository } 'nicht veraendert'
    Assert-Scan2MeshTest (@($script:commands | Where-Object { $_[1] -contains '--import' -or $_[1] -contains 'bash' }).Count -eq 0) 'Modified an unowned distro'
    Assert-Scan2MeshTest (@($script:commands | Where-Object { $_[1] -contains '--unregister' -or $_[1] -contains '--shutdown' }).Count -eq 0) 'Destructive WSL action'
    Write-Host 'PASS: 12 Windows setup contracts'
}
finally {
    foreach ($name in $functions.Keys) { Set-Item ('Function:\' + $name) -Value $functions[$name] }
    $env:LOCALAPPDATA = $previousLocal
    $env:OS = $previousOS
    $env:SCAN2MESH_NKSR_WSL_DISTRO = $previousDistro
    $env:SCAN2MESH_NKSR_PYTHON = $previousPython
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
