$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = 'postgresql://postgres:changeme@127.0.0.1:55439/kirill_skorikov' }
if (Test-Path -LiteralPath '.\runtime\pgsql\bin\pg_ctl.exe') {
    & '.\runtime\pgsql\bin\pg_ctl.exe' -D '.\runtime\data' status
    if ($LASTEXITCODE -ne 0) { & '.\runtime\pgsql\bin\pg_ctl.exe' -D '.\runtime\data' -l '.\runtime\postgres.log' -w start }
}
& '.\.venv\Scripts\python.exe' app.py
