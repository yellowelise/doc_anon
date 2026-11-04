param([Parameter(Mandatory=$true)][string]$ResourcesDirectory, [switch]$Isolated)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $projectRoot 'dist/DocAnon-Setup-0.2.1-x64.exe'
$registryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{A45FA0C3-52DE-494D-8745-1EDDB0386945}_is1'
$productionKey = $registryKey
$productionBefore = $null
if ($Isolated -and (Test-Path -LiteralPath $productionKey)) {
    $production = Get-ItemProperty -LiteralPath $productionKey
    $productionBefore = @{ Version=$production.DisplayVersion; Directory=$production.InstallLocation;
        Hash=(Get-FileHash -LiteralPath (Join-Path $production.InstallLocation 'DocAnon.exe')).Hash }
}
if ($Isolated) {
    $installer = Join-Path $projectRoot '.test-data/installer-build/DocAnon-Setup-0.2.1-test-x64.exe'
    $registryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{F6685F52-4CCA-4FDC-9F16-D3DBFF72EB42}_is1'
}
if (Test-Path -LiteralPath $registryKey) { throw 'Doc Anon risulta già installato: non modifico la registrazione esistente.' }
$testRoot = Join-Path $projectRoot ('.test-data/installer-' + [guid]::NewGuid().ToString('N'))
$appDir = [IO.Path]::GetFullPath((Join-Path $testRoot 'app'))
if (-not $appDir.StartsWith([IO.Path]::GetFullPath((Join-Path $projectRoot '.test-data')) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'La destinazione di prova deve rimanere in .test-data.'
}
$groupName = 'Doc Anon - verifica ' + [guid]::NewGuid().ToString('N')
$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) $groupName
New-Item -ItemType Directory -Force $testRoot | Out-Null
$report = [ordered]@{ ok=$false; version='0.2.1'; isolatedIdentity=[bool]$Isolated; installed=$false; reinstalled=$false; payloadFilesVerified=0; shortcutVerified=$false; offlineSelfTest=$null; uninstalled=$false; outputsPreserved=$false }
$oldDataDir = $env:DOC_ANON_DATA_DIR

function Invoke-InstallerProcess([string]$Binary, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Binary -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    for ($i=0; $i -lt 4; $i++) {
        if ($process.WaitForExit(60000)) {
            if ($process.ExitCode -ne 0) { throw "Processo fallito ($($process.ExitCode)): $Binary" }
            return
        }
        Write-Output 'Operazione in corso…'
    }
    throw "Timeout: processo $($process.Id) ancora attivo."
}

try {
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/LANG=italian', '/TASKS=""',
        ('/DIR="' + $appDir + '"'), ('/GROUP="' + $groupName + '"'))
    Invoke-InstallerProcess $installer ($arguments + ('/LOG="' + (Join-Path $testRoot 'install.log') + '"'))
    $report.installed = Test-Path -LiteralPath (Join-Path $appDir 'DocAnon.exe')
    if (-not $report.installed -or -not (Test-Path -LiteralPath $registryKey)) { throw 'Installazione o registrazione assente.' }
    $registered = Get-ItemProperty -LiteralPath $registryKey
    if ($registered.DisplayVersion -ne '0.2.1') { throw 'Versione installata errata.' }
    if ([IO.Path]::GetFullPath($registered.InstallLocation).TrimEnd('\') -ne $appDir) { throw 'Percorso di installazione inatteso.' }
    $shortcut = Join-Path $startMenu 'Doc Anon.lnk'
    if (-not (Test-Path -LiteralPath $shortcut)) { throw 'Collegamento menu Start assente.' }
    $shell = New-Object -ComObject WScript.Shell
    $report.shortcutVerified = $shell.CreateShortcut($shortcut).TargetPath -eq (Join-Path $appDir 'DocAnon.exe')
    if (-not $report.shortcutVerified) { throw 'Destinazione collegamento errata.' }
    Write-Output 'Installazione e collegamento verificati.'

    # Reinstall over the same version, preserving the same install identity and location.
    Invoke-InstallerProcess $installer ($arguments + ('/LOG="' + (Join-Path $testRoot 'reinstall.log') + '"'))
    $report.reinstalled = $true
    $payloadRoot = Join-Path $projectRoot 'dist/DocAnon'
    foreach ($file in Get-ChildItem -LiteralPath $payloadRoot -Recurse -File) {
        $relative = [IO.Path]::GetRelativePath($payloadRoot, $file.FullName)
        if ($relative -eq 'LEGGIMI.txt') { continue }
        $installed = Join-Path $appDir $relative
        if (-not (Test-Path -LiteralPath $installed)) { throw "File mancante: $relative" }
        if ((Get-FileHash -LiteralPath $installed).Hash -ne (Get-FileHash -LiteralPath $file.FullName).Hash) { throw "File diverso: $relative" }
        $report.payloadFilesVerified++
    }
    if ((Get-FileHash -LiteralPath (Join-Path $appDir 'LEGGIMI.txt')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $projectRoot 'installer/LEGGIMI-installato.txt')).Hash) { throw 'Istruzioni installate errate.' }
    Write-Output "Reinstallazione e $($report.payloadFilesVerified) file verificati."

    $env:DOC_ANON_DATA_DIR = [IO.Path]::GetFullPath($ResourcesDirectory)
    $outputDir = Join-Path $testRoot 'offline-test'
    Invoke-InstallerProcess (Join-Path $appDir 'DocAnon.exe') @('--self-test', ('"' + $outputDir + '"'))
    $report.offlineSelfTest = Get-Content -LiteralPath (Join-Path $outputDir 'self-test.json') -Raw | ConvertFrom-Json
    if (-not $report.offlineSelfTest.ok -or $report.offlineSelfTest.network_attempts -ne 0) { throw 'Prova offline fallita.' }
    Write-Output 'Applicazione installata: modello, OCR, esportazione e interfaccia verificati offline.'
}
catch {
    $report.error = $_.Exception.Message
}
finally {
    $env:DOC_ANON_DATA_DIR = $oldDataDir
    $uninstaller = Join-Path $appDir 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        # Only run the uninstaller created in this freshly allocated test directory.
        if (-not ([IO.Path]::GetFullPath($uninstaller)).StartsWith($appDir + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Disinstallazione fuori directory di prova.' }
        Invoke-InstallerProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/LOG="' + (Join-Path $testRoot 'uninstall.log') + '"'))
        $report.uninstalled = (-not (Test-Path -LiteralPath (Join-Path $appDir 'DocAnon.exe'))) -and (-not (Test-Path -LiteralPath $registryKey)) -and (-not (Test-Path -LiteralPath (Join-Path $startMenu 'Doc Anon.lnk')))
    }
    $report.outputsPreserved = (Test-Path -LiteralPath (Join-Path $testRoot 'offline-test/self-test.json')) -and (Test-Path -LiteralPath (Join-Path $ResourcesDirectory 'ready.json'))
    $report.productionInstallationPreserved = $true
    if ($productionBefore) {
        $productionAfter = Get-ItemProperty -LiteralPath $productionKey
        $report.productionInstallationPreserved = $productionAfter.DisplayVersion -eq $productionBefore.Version -and
            $productionAfter.InstallLocation -eq $productionBefore.Directory -and
            (Get-FileHash -LiteralPath (Join-Path $productionAfter.InstallLocation 'DocAnon.exe')).Hash -eq $productionBefore.Hash
    }
    $report.ok = $report.installed -and $report.reinstalled -and $report.shortcutVerified -and $report.uninstalled -and $report.outputsPreserved -and $report.offlineSelfTest.ok -and $report.productionInstallationPreserved -and (-not $report.Contains('error'))
    $json = $report | ConvertTo-Json -Depth 6
    Set-Content -LiteralPath (Join-Path $testRoot 'installer-test.json') -Value $json -Encoding utf8
    Set-Content -LiteralPath (Join-Path $projectRoot 'verification/installer-test.json') -Value $json -Encoding utf8
    Write-Output $json
}
if (-not $report.ok) { throw 'Verifica installer fallita: consultare verification/installer-test.json.' }
