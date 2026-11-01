<#
  NyayMitra demo launcher (Windows PowerShell 5.1+).
  Starts: Postgres (Docker) -> llama-server (AI) -> backend (uvicorn) ->
  Cloudflare quick tunnel, then prints the public HTTPS address to type
  into the app (sign-in screen -> server icon, top right).

  Usage, from anywhere:
    powershell -ExecutionPolicy Bypass -File D:\EDI_5\demo\start_demo.ps1
  Optional:
    -NoAI                      skip llama-server (chat will say AI offline)
    -NoWatch                   exit after starting (no automatic tunnel repair)
    -LlamaExe / -ModelPath     if your files live elsewhere
#>
param(
  [switch]$NoAI,
  [string]$LlamaExe  = "D:\tools\llama\llama-server.exe",
  [string]$ModelPath = "D:\models\nyaymitra-demo.gguf",
  # Not 8080: another project's Adminer container uses 8080 on this laptop.
  # Must match LLM_BASE_URL in backend\.env.
  [int]$LlamaPort    = 8081,
  # Exit after starting instead of watching and repairing the tunnel.
  [switch]$NoWatch
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

# True only if llama-server itself answers on the port ({"status":"ok"}),
# not merely "something is listening" - a different app on the same port
# once made the backend think the AI was up when it wasn't.
function Test-Llama($port) {
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3
    return ($r.status -eq "ok")
  } catch { return $false }
}

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
  if (Test-Llama $LlamaPort) {
    Say "llama-server already running on $LlamaPort."
  } elseif (Test-Port $LlamaPort) {
    Fail "Port $LlamaPort is used by another program, not llama-server. Stop it, or pass -LlamaPort <free port> and set LLM_BASE_URL in backend\.env to match."
  } else {
    if (-not (Test-Path $LlamaExe))  { Fail "llama-server not found at $LlamaExe (use -LlamaExe, or -NoAI)." }
    if (-not (Test-Path $ModelPath)) { Fail "Model not found at $ModelPath (use -ModelPath, or -NoAI)." }
    Say "Starting llama-server (AI model, loads ~4 GB)..."
    $p = Start-Process -FilePath $LlamaExe -PassThru -WindowStyle Minimized -ArgumentList @(
      "-m", "`"$ModelPath`"", "--host", "127.0.0.1", "--port", "$LlamaPort", "-c", "4096")
    Save-Pid "llama" $p
    Wait-Port $LlamaPort 180 "llama-server" | Out-Null
    # Port opens before the model finishes loading; wait for real readiness.
    for ($i = 0; $i -lt 120 -and -not (Test-Llama $LlamaPort); $i++) { Start-Sleep -Seconds 2 }
    if (-not (Test-Llama $LlamaPort)) { Fail "llama-server started but never reported ready. Check its window." }
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

# Publishes the address to branch "demo-server" (file server.json) of this
# repo, where the app looks it up automatically. Plumbing commands only:
# your checked-out branch, working files and index are never touched.
function Publish-ServerUrl($url) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $tmpIndex = Join-Path $State "publish.index"
  $jsonFile = Join-Path $State "server.json"
  Push-Location $Repo
  try {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $json = "{`"url`": `"$url`", `"updatedAt`": `"$stamp`"}"
    [System.IO.File]::WriteAllText($jsonFile, $json)
    $blob = (git hash-object -w "$jsonFile" | Out-String).Trim()
    if (Test-Path $tmpIndex) { Remove-Item $tmpIndex -Force }
    $env:GIT_INDEX_FILE = $tmpIndex
    git update-index --add --cacheinfo "100644,$blob,server.json" 2>&1 | Out-Null
    $tree = (git write-tree | Out-String).Trim()
    Remove-Item Env:\GIT_INDEX_FILE
    $commit = (git commit-tree $tree -m "Demo server address $stamp" | Out-String).Trim()
    if (-not $commit) { return $false }
    git push --force --quiet origin "$($commit):refs/heads/demo-server" 2>&1 | Out-Host
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  } finally {
    if (Test-Path Env:\GIT_INDEX_FILE) { Remove-Item Env:\GIT_INDEX_FILE }
    if (Test-Path $tmpIndex) { Remove-Item $tmpIndex -Force -ErrorAction SilentlyContinue }
    Pop-Location
    $ErrorActionPreference = $old
  }
}

function Test-Public($url) {
  try { Invoke-RestMethod -Uri "$url/health" -TimeoutSec 15 | Out-Null; return $true } catch { return $false }
}

function Test-Internet {
  try { Invoke-WebRequest -Uri "https://www.cloudflare.com" -UseBasicParsing -TimeoutSec 10 | Out-Null; return $true } catch { return $false }
}

# Starts a fresh quick tunnel and returns its https address (or $null).
function Start-Tunnel {
  Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  $log = Join-Path $State "tunnel.log"
  if (Test-Path $log) { Remove-Item $log -Force -ErrorAction SilentlyContinue }
  # cloudflared's own --logfile (not stderr redirection): the redirected
  # file stays locked while the process runs, cloudflared's log does not.
  $p = Start-Process -FilePath $cf -PassThru -WindowStyle Hidden -ArgumentList @(
    "tunnel", "--no-autoupdate", "--loglevel", "info", "--logfile", "`"$log`"", "--url", "http://127.0.0.1:8000")
  Save-Pid "tunnel" $p
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    if (-not (Test-Path $log)) { continue }
    try {
      # FileShare.ReadWrite: cloudflared still has the file open for writing.
      $fs = [System.IO.File]::Open($log, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
      $sr = New-Object System.IO.StreamReader($fs)
      $text = $sr.ReadToEnd()
      $sr.Close()
      $m = [regex]::Match($text, "https://[a-z0-9-]+\.trycloudflare\.com")
      if ($m.Success) { return $m.Value }
    } catch {}
  }
  return $null
}

# Opens a tunnel, waits until it answers from the internet, publishes it.
function Open-AndPublish {
  Say "Opening a public HTTPS tunnel (Cloudflare quick tunnel)..."
  $url = Start-Tunnel
  if (-not $url) { Say "Tunnel did not report an address (see .state\tunnel.log)." "Yellow"; return $null }
  Set-Content -Path (Join-Path $State "url.txt") -Value $url -NoNewline
  for ($i = 0; $i -lt 30 -and -not (Test-Public $url); $i++) { Start-Sleep -Seconds 2 }
  if (Publish-ServerUrl $url) {
    Say "Published $url - phones pick it up automatically." "Green"
  } else {
    Say "Could not publish to GitHub (git push failed). Phones won't find it automatically;" "Yellow"
    Say "type it in the app instead: server icon -> paste -> Use this." "Yellow"
  }
  try { Set-Clipboard -Value $url } catch {}
  return $url
}

$url = Open-AndPublish
if (-not $url) { Fail "Could not open a tunnel. Check the internet connection and re-run." }

Write-Host ""
Write-Host "  ====================================================================" -ForegroundColor Green
Write-Host "    NyayMitra is live at:  $url" -ForegroundColor Green
Write-Host "    Phones connect automatically - nothing to type in the app." -ForegroundColor Green
Write-Host "    KEEP THIS WINDOW OPEN: it repairs the tunnel if it drops." -ForegroundColor Green
Write-Host "    Stop everything with demo\stop_demo.ps1" -ForegroundColor Green
Write-Host "  ====================================================================" -ForegroundColor Green

if ($NoWatch) { exit 0 }

# --------------------------------------------------------------- 5. Watchdog
# Keeps the laptop from going to sleep while this window is open (a
# per-process request, released when the window closes - no settings are
# changed). ES_CONTINUOUS | ES_SYSTEM_REQUIRED.
try {
  Add-Type -Namespace NyayMitra -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
  [NyayMitra.Power]::SetThreadExecutionState([uint32]2147483649) | Out-Null
} catch {}

$fails = 0
while ($true) {
  Start-Sleep -Seconds 30
  $tunnelProc = Get-Process cloudflared -ErrorAction SilentlyContinue
  if ($tunnelProc -and (Test-Public $url)) { $fails = 0; continue }
  $fails++
  $time = Get-Date -Format "HH:mm:ss"
  if (-not (Test-Port 8000)) {
    Write-Host "[$time] Backend is not running on 8000 - restart it (the tunnel is fine)." -ForegroundColor Yellow
    continue
  }
  if (-not (Test-Internet)) {
    Write-Host "[$time] No internet on this laptop - waiting for it to come back..." -ForegroundColor Yellow
    continue
  }
  # Give a brief blip a minute to heal; restart at once if cloudflared died.
  if ($tunnelProc -and $fails -lt 3) {
    Write-Host "[$time] Public address not answering ($fails/3)..." -ForegroundColor Yellow
    continue
  }
  Write-Host "[$time] Tunnel is down - opening a new one." -ForegroundColor Yellow
  $new = Open-AndPublish
  if ($new) { $url = $new; $fails = 0 }
}
