$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    Write-Host '請先依 README 建立 .venv 並安裝 requirements.txt。'
    exit 1
}
# 某些 Windows 沙箱的系統 TEMP 不可寫，使用已忽略的本機暫存目錄。
New-Item -ItemType Directory -Force '.tmp' | Out-Null
$env:TEMP = Join-Path $PSScriptRoot '.tmp'
$env:TMP = $env:TEMP
& '.\.venv\Scripts\python.exe' -m streamlit run app.py --server.address 127.0.0.1
