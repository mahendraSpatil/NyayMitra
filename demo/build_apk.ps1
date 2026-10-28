<#
  Builds the release APK and copies it to D:\EDI_5\demo\NyayMitra.apk.
  Optional: -ServerUrl https://your-server  bakes in a default server
  (people can still change it in the app). Without it, set the server in
  the app on first launch.

    powershell -ExecutionPolicy Bypass -File D:\EDI_5\demo\build_apk.ps1
#>
param([string]$ServerUrl = "")

$ErrorActionPreference = "Continue"  # flutter writes progress to stderr
$Client = Join-Path (Split-Path -Parent $PSScriptRoot) "client"
Push-Location $Client
try {
  flutter pub get
  $flutterArgs = @("build", "apk", "--release")
  if ($ServerUrl) {
    $clean = $ServerUrl.TrimEnd("/")
    if ($clean.EndsWith("/api/v2")) { $clean = $clean.Substring(0, $clean.Length - 7) }
    $flutterArgs += "--dart-define=API_BASE_URL=$clean"
  }
  & flutter @flutterArgs
  if ($LASTEXITCODE -ne 0) { throw "flutter build failed" }
  $apk = Join-Path $Client "build\app\outputs\flutter-apk\app-release.apk"
  $out = Join-Path $PSScriptRoot "NyayMitra.apk"
  Copy-Item $apk $out -Force
  $mb = [math]::Round((Get-Item $out).Length / 1MB, 1)
  Write-Host ""
  Write-Host "APK ready: $out ($mb MB)" -ForegroundColor Green
  Write-Host "Install on a USB-connected phone:  adb install -r `"$out`"" -ForegroundColor Green
  Write-Host "Or send the file (WhatsApp/Drive) and open it on the phone." -ForegroundColor Green
} finally { Pop-Location }
