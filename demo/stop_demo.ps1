<#
  Stops what start_demo.ps1 started: tunnel, backend, llama-server.
  Leaves Postgres (Docker) running - your data stays either way.
#>
$State = Join-Path $PSScriptRoot ".state"
# First the launcher window(s): their watchdog would otherwise open a new
# tunnel and publish it as soon as it sees this one go down.
Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like '*start_demo.ps1*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host "Stopped launcher (PID $($_.ProcessId))" }
Remove-Item (Join-Path $State "watch.pid") -Force -ErrorAction SilentlyContinue
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
