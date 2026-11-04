param([string]$TesseractDirectory = 'C:\Program Files\Tesseract-OCR', [switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Creazione ambiente fallita' }
}
$buildPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not $SkipInstall) {
    & $buildPython -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw 'Installazione PyTorch fallita' }
    & $buildPython -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze fallita' }
}
if (-not (Test-Path -LiteralPath (Join-Path $TesseractDirectory 'tesseract.exe'))) {
    throw 'Specificare -TesseractDirectory con Tesseract 5 x64 installato (UB Mannheim).'
}
New-Item -ItemType Directory -Force 'vendor/tesseract' | Out-Null
Copy-Item -LiteralPath (Join-Path $TesseractDirectory 'tesseract.exe') -Destination 'vendor/tesseract/'
Get-ChildItem -LiteralPath $TesseractDirectory -Filter '*.dll' | Copy-Item -Destination 'vendor/tesseract/'
if (Test-Path -LiteralPath (Join-Path $TesseractDirectory 'doc')) {
    Copy-Item -LiteralPath (Join-Path $TesseractDirectory 'doc') -Destination 'vendor/tesseract/' -Recurse -Force
}
& $buildPython scripts/make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Creazione icona fallita' }
& $buildPython scripts/collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'Raccolta licenze fallita' }
& $buildPython -m pytest -m 'not integration'
if ($LASTEXITCODE -ne 0) { throw 'Test falliti' }
& $buildPython -m PyInstaller --noconfirm DocAnon.spec
if ($LASTEXITCODE -ne 0) { throw 'Build fallito' }
Copy-Item -LiteralPath 'LEGGIMI.txt','THIRD_PARTY_NOTICES.md' -Destination 'dist/DocAnon/'
Compress-Archive -Path 'dist/DocAnon' -DestinationPath 'dist/DocAnon-Windows-x64.zip' -Force
Write-Output 'Pronto: dist/DocAnon/DocAnon.exe e dist/DocAnon-Windows-x64.zip'
