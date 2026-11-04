param([string]$IsccPath, [switch]$TestBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$payload = Join-Path $projectRoot 'dist/DocAnon/DocAnon.exe'
if (-not (Test-Path -LiteralPath $payload)) { throw 'Prima creare dist/DocAnon con scripts/build.ps1.' }
if (-not $IsccPath) {
    $candidates = @(
        (Join-Path $projectRoot '.tools/inno/ISCC.exe'),
        (Join-Path ${env:ProgramFiles} 'Inno Setup 7/ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs/Inno Setup 7/ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs/Inno Setup 6/ISCC.exe')
    )
    $IsccPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $IsccPath) {
        $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($command) { $IsccPath = $command.Source }
    }
}
if (-not $IsccPath) { throw 'Installare Inno Setup 7 oppure specificare -IsccPath. https://jrsoftware.org/isdl.php' }
$output = Join-Path $projectRoot 'dist'
$compilerArgs = @('/Qp')
if ($TestBuild) {
    $output = Join-Path $projectRoot '.test-data/installer-build'
    New-Item -ItemType Directory -Force $output | Out-Null
    $compilerArgs += '/DTestBuild'
}
$compilerArgs += ('/O' + $output)
$compilerArgs += (Join-Path $projectRoot 'installer/DocAnon.iss')
& $IsccPath @compilerArgs
if ($LASTEXITCODE -ne 0) { throw 'Compilazione installer fallita.' }
$fileName = if ($TestBuild) { 'DocAnon-Setup-0.2.1-test-x64.exe' } else { 'DocAnon-Setup-0.2.1-x64.exe' }
$installer = Join-Path $output $fileName
if (-not (Test-Path -LiteralPath $installer)) { throw 'Installer non trovato.' }
if ($TestBuild) {
    Get-Item -LiteralPath $installer | Select-Object FullName, Length
    return
}
$checksumFile = Join-Path $output 'CHECKSUMS.sha256'
$entries = @()
if (Test-Path -LiteralPath $checksumFile) {
    $entries = @(Get-Content -LiteralPath $checksumFile | Where-Object { $_ -notmatch ('  ' + [regex]::Escape($fileName) + '$') })
}
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
$entries += "$hash  $([IO.Path]::GetFileName($installer))"
Set-Content -LiteralPath $checksumFile -Value $entries -Encoding utf8
Get-Item -LiteralPath $installer | Select-Object FullName, Length
