<#
  NyayMitra demo launcher (Windows PowerShell 5.1+).
  Starts: Postgres (Docker) -> llama-server (AI) -> backend (uvicorn) ->
  Cloudflare quick tunnel, then prints the public HTTPS address to type
  into the app (sign-in screen -> server icon, top right).

  Usage, from anywhere:
    powershell -ExecutionPolicy Bypass -File D:\EDI_5\demo\start_demo.ps1
  Optional:
    -NoAI                      skip llama-server (chat will say AI offline)
    -LlamaExe / -ModelPath     if your files live elsewhere
#>
param(
  [switch]$NoAI,
  [string]$LlamaExe  = "D:\tools\llama\llama-server.exe",
  [string]$ModelPath = "D:\models\nyaymitra-demo.gguf"
)

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 may default to TLS 1.0/1.1; Cloudflare needs 1.2+.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Repo    = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Repo "backend"
$State   = Join-Path $PSScriptRoot ".state"
New-Item -ItemType Directory -Force -Path $State | Out-Null

function Say($msg, $color = "Cyan") { Write-Host "==> $msg" -ForegroundColor $color }
function Fail($msg) { Write-Host "XX  $msg" -ForegroundColor Red; exit 1 }

function Test-Port($port) {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect("127.0.0.1", $port, $null, $null)
    $ok = $async.AsyncWaitHandle.WaitOne(500)
    if ($ok) { $client.EndConnect($async) }
    return $ok
  } catch { return $false } finally { $client.Close() }
}

function Wait-Port($port, $seconds, $what) {
  for ($i = 0; $i -lt $seconds; $i++) {
    if (Test-Port $port) { return $true }
    Start-Sleep -Seconds 1
  }
  Fail "$what did not start on port $port within $seconds s. Check its window for errors."
}

# Native tools (docker, alembic) write progress/warnings to stderr. Under
# "Stop", Windows PowerShell 5.1 turns those into terminating errors, so
# run them under "Continue" and judge by exit code instead.
function Invoke-Native([scriptblock]$block) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $block } finally { $ErrorActionPreference = $old }
  return $LASTEXITCODE
}

function Test-Docker { return ((Invoke-Native { docker info > $null 2>&1 }) -eq 0) }

function Save-Pid($name, $proc) { if ($proc) { Set-Content -Path (Join-Path $State "$name.pid") -Value $proc.Id } }

# ---------------------------------------------------------------- 1. Docker
Say "Checking Docker..."
$dockerOk = Test-Docker
if (-not $dockerOk) {
  $dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  if (-not (Test-Path $dd)) { Fail "Docker Desktop not found. Install it or start Postgres yourself." }
  Say "Starting Docker Desktop (can take a minute)..." "Yellow"
  Start-Process $dd
  for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Docker) { $dockerOk = $true; break }
  }
  if (-not $dockerOk) { Fail "Docker did not come up. Open Docker Desktop, wait for 'Engine running', re-run." }
}

Say "Starting Postgres (nyaymitra-postgres on 5433)..."
Push-Location $Repo
$rc = Invoke-Native { docker compose up -d 2>&1 | Out-Host }
Pop-Location
if ($rc -ne 0) { Fail "docker compose up failed (see above)." }
Wait-Port 5433 60 "Postgres" | Out-Null

# --------------------------------------------------------------- 2. AI model
if (-not $NoAI) {
  if (Test-Port 8080) {
    Say "llama-server already running on 8080."
  } else {
    if (-not (Test-Path $LlamaExe))  { Fail "llama-server not found at $LlamaExe (use -LlamaExe, or -NoAI)." }
    if (-not (Test-Path $ModelPath)) { Fail "Model not found at $ModelPath (use -ModelPath, or -NoAI)." }
    Say "Starting llama-server (AI model, loads ~4 GB)..."
    $p = Start-Process -FilePath $LlamaExe -PassThru -WindowStyle Minimized -ArgumentList @(
      "-m", "`"$ModelPath`"", "--host", "127.0.0.1", "--port", "8080", "-c", "4096")
    Save-Pid "llama" $p
    Wait-Port 8080 180 "llama-server" | Out-Null
  }
}

# ------------------------------------------------------------------ 3. Backend
$py = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Fail "Backend venv not found at $py. Create it (README: Backend setup)." }

Say "Applying database migrations..."
Push-Location $Backend
$rc = Invoke-Native { & $py -m alembic upgrade head 2>&1 | Out-Host }
if ($rc -ne 0) { Pop-Location; Fail "alembic upgrade failed (see above)." }
Pop-Location

if (Test-Port 8000) {
  Say "Backend already running on 8000."
} else {
  Say "Starting backend (uvicorn on 127.0.0.1:8000)..."
  $p = Start-Process -FilePath "powershell" -PassThru -WorkingDirectory $Backend -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle='NyayMitra backend'; & '$py' -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
  Save-Pid "backend" $p
  Wait-Port 8000 60 "Backend" | Out-Null
}

try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10
  Say ("Backend healthy. AI online: " + $health.llm) "Green"
} catch { Fail "Backend is up but /health failed: $_" }

# ------------------------------------------------------------------- 4. Tunnel
$CfCandidates = @(
  "C:\Program Files (x86)\cloudflared\cloudflared.exe",
  "C:\Program Files\cloudflared\cloudflared.exe",
  (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\cloudflared.exe"))
$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) {
  foreach ($c in $CfCandidates) {
    if (Test-Path $c) { $cf = $c; break }
  }
}
if (-not $cf) {
  Say "Installing cloudflared (one time)..." "Yellow"
  Invoke-Native { winget install -e --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements 2>&1 | Out-Host } | Out-Null
  foreach ($c in $CfCandidates) {
    if (Test-Path $c) { $cf = $c; break }
  }
  if (-not $cf) { Fail "cloudflared installed but not found. Open a new terminal and re-run." }
}

Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$log = Join-Path $State "tunnel.log"
if (Test-Path $log) { Remove-Item $log -Force }
Say "Opening a public HTTPS tunnel (Cloudflare quick tunnel)..."
# cloudflared's own --logfile (not stderr redirection): the redirected file
# stays locked while the process runs, cloudflared's log does not.
$p = Start-Process -FilePath $cf -PassThru -WindowStyle Hidden -ArgumentList @(
  "tunnel", "--no-autoupdate", "--loglevel", "info", "--logfile", "`"$log`"", "--url", "http://127.0.0.1:8000")
Save-Pid "tunnel" $p

$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
  Start-Sleep -Seconds 1
  if (Test-Path $log) {
    try {
      # FileShare.ReadWrite: cloudflared still has the file open for writing.
      $fs = [System.IO.File]::Open($log, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
      $sr = New-Object System.IO.StreamReader($fs)
      $text = $sr.ReadToEnd()
      $sr.Close()
      $m = [regex]::Match($text, "https://[a-z0-9-]+\.trycloudflare\.com")
      if ($m.Success) { $url = $m.Value }
    } catch {}
  }
}
if (-not $url) { Fail "Tunnel did not report an address. See $log" }
Set-Content -Path (Join-Path $State "url.txt") -Value $url

# The new hostname can take a few seconds to resolve worldwide.
$reachable = $false
for ($i = 0; $i -lt 30; $i++) {
  try { Invoke-RestMethod -Uri "$url/health" -TimeoutSec 10 | Out-Null; $reachable = $true; break } catch { Start-Sleep -Seconds 2 }
}
try { Set-Clipboard -Value $url } catch {}

Write-Host ""
Write-Host "  ====================================================================" -ForegroundColor Green
Write-Host "    NyayMitra is live at:" -ForegroundColor Green
Write-Host ""
Write-Host "      $url" -ForegroundColor White
Write-Host ""
Write-Host "    (copied to clipboard)  In the app: sign-in screen -> server icon" -ForegroundColor Green
Write-Host "    (top right) -> paste -> Save.  Address changes every run." -ForegroundColor Green
if (-not $reachable) {
  Write-Host "    Note: not reachable from here yet - give it 30 s, then test in the app." -ForegroundColor Yellow
}
Write-Host "    Keep this laptop awake and online. Stop with demo\stop_demo.ps1" -ForegroundColor Green
Write-Host "  ====================================================================" -ForegroundColor Green
