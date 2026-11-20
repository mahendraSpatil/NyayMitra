# Verifies Downloads\nyaymitra-v2.gguf against Vedant's manifest SHA-256 and
# moves it to D:\models. Log: demo\.state\install_model.log
$log = Join-Path $PSScriptRoot ".state\install_model.log"
$src = Join-Path $env:USERPROFILE "Downloads\nyaymitra-v2.gguf"
$dst = "D:\models\nyaymitra-v2.gguf"
$expected = "92DDBB44A5BED92EA23D890DD72A0CD849E28DCC4B2EB07FBE16D4D79ADDBB70"
"start $(Get-Date -Format s)" | Set-Content $log
if (-not (Test-Path $src)) { "missing $src" | Add-Content $log; exit 1 }
$hash = (Get-FileHash -Algorithm SHA256 $src).Hash
"sha256 $hash" | Add-Content $log
if ($hash -ne $expected) { "MISMATCH expected $expected" | Add-Content $log; exit 2 }
Move-Item -Force $src $dst
"moved to $dst ($((Get-Item $dst).Length) bytes)" | Add-Content $log
"done" | Add-Content $log
