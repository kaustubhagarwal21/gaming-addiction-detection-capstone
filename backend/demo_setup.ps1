# ─────────────────────────────────────────────────────────────────────────
#  One-command demo setup — PES Capstone PW26_SJ_05
#  Run from the backend folder:   .\demo_setup.ps1
#
#  Does everything needed for a reliable live demo:
#    1. Opens the adb reverse tunnel (phone's 127.0.0.1:5000 -> this PC)
#       so the apps reach the backend regardless of WiFi / IP changes.
#    2. (Optional) Re-seeds the demo data narrative.
#    3. Starts the Flask backend (blocks — leave this window open).
#
#  Usage:
#    .\demo_setup.ps1            # tunnel + start backend (keeps existing data)
#    .\demo_setup.ps1 -Seed      # also re-seed the demo narrative first
#    .\demo_setup.ps1 -Enforce   # require auth tokens (rejects un-authenticated
#                                #   requests). Use after both apps are reinstalled
#                                #   with token support; omit for backwards-compatible
#                                #   "shadow" mode that never rejects.
# ─────────────────────────────────────────────────────────────────────────
param([switch]$Seed, [switch]$Enforce)

$ErrorActionPreference = "Continue"

if ($Enforce) {
    $env:AUTH_ENFORCE = "1"
    Write-Host "AUTH_ENFORCE=1 — tokens are REQUIRED (un-authenticated requests get 401/403)." -ForegroundColor Yellow
} else {
    $env:AUTH_ENFORCE = "0"
}

Write-Host "=== 1/3  adb reverse tunnel ===" -ForegroundColor Cyan
adb reverse tcp:5000 tcp:5000
if ($LASTEXITCODE -eq 0) {
    Write-Host "    Tunnel OK — apps should use server URL  http://127.0.0.1:5000/" -ForegroundColor Green
} else {
    Write-Host "    adb reverse failed — is the phone connected via USB with debugging on?" -ForegroundColor Yellow
}

if ($Seed) {
    Write-Host "`n=== 2/3  Seeding demo data ===" -ForegroundColor Cyan
    python3.11 seed_demo.py
} else {
    Write-Host "`n=== 2/3  Skipping seed (use -Seed to reload the demo narrative) ===" -ForegroundColor DarkGray
}

Write-Host "`n=== 3/3  Starting backend (Ctrl+C to stop) ===" -ForegroundColor Cyan
Write-Host "    PINs ->  Child Arjun: 1234   Child Priya: 5678   Parent: 0000`n" -ForegroundColor Green
python3.11 app.py
