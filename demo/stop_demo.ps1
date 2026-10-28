<#
  Stops what start_demo.ps1 started: tunnel, backend, llama-server.
  Leaves Postgres (Docker) running - your data stays either way.
#>
$State = Join-Path $PSScriptRoot ".state"
foreach ($name in @("tunnel", "backend", "llama")) {
  $file = Join-Path $State "$name.pid"
  if (Test-Path $file) {
    $procId = Get-Content $file
    try {
      # /T also stops child processes (uvicorn under its PowerShell window).
      taskkill /PID $procId /T /F *> $null
      Write-Host "Stopped $name (PID $procId)"
    } catch { Write-Host "$name already stopped" }
    Remove-Item $file -Force
  }
}
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "Done. (Postgres left running: 'docker compose stop' in D:\EDI_5 to stop it.)"
