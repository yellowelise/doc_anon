param([string]$ResourcesDirectory, [string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ResourcesDirectory) { $ResourcesDirectory = Join-Path $projectRoot '.test-data/resources' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot '.test-data/packaged' }
$env:DOC_ANON_DATA_DIR = [IO.Path]::GetFullPath($ResourcesDirectory)
$binary = Join-Path $projectRoot 'dist/DocAnon/DocAnon.exe'
$testProcess = Start-Process -FilePath $binary -ArgumentList @('--self-test', ('"' + [IO.Path]::GetFullPath($OutputDirectory) + '"')) -WindowStyle Hidden -PassThru
$completed = $false
for ($attempt=0; $attempt -lt 5; $attempt++) {
    if ($testProcess.WaitForExit(60000)) { $completed = $true; break }
    Write-Output 'Verifica del modello e delle qualità PDF in corso…'
}
if (-not $completed) {
    Stop-Process -Id $testProcess.Id
    throw 'Il test del pacchetto non è terminato entro 5 minuti.'
}
$report = Join-Path $OutputDirectory 'self-test.json'
if (-not (Test-Path -LiteralPath $report)) { throw 'Il pacchetto non ha prodotto il report.' }
Get-Content -LiteralPath $report
if ($testProcess.ExitCode -ne 0) { throw 'Test del pacchetto fallito.' }
