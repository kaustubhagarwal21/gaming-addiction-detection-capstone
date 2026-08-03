# Automated Security Audit — MobSF Static Analysis (2026-08-04)

Independent automated static security audit of both **signed release APKs** using
[Mobile Security Framework (MobSF)](https://github.com/MobSF/Mobile-Security-Framework-MobSF)
**v4.5.1** (21k+ stars, the de-facto open-source mobile app security scanner), run
locally in Docker against the exact artifacts attached to release **v2.3.11**.

| App | Artifact | Version | MobSF score |
|---|---|---|---|
| Child (Gaming Detector) | `GamingDetector-ChildApp-v2.3.11.apk` (md5 `83d3acbd…`) | 2.3.11 / `com.pes.gamingdetector` | **58/100** |
| Parent (Guardian) | `ParentMonitor-v2.1.10.apk` (md5 `e6c2d9c8…`) | 2.1.10 / `com.pes.parentmonitor` | **66/100** |

MobSF's score deliberately punishes permission-heavy apps; a parental-monitoring
app (mic, usage stats, accessibility, device admin) starts at a structural
disadvantage. What matters is the findings triage below.

## High-severity findings (1 per app — same finding, triaged benign-with-action)

**"Domain config permits clear text traffic"** — scope is exactly
`localhost`, `127.0.0.1`, `10.0.2.2` (the Android emulator's host alias): the
standard development-loopback exception in `network_security_config`. MobSF itself
rates the base config **secure** ("disallows clear text traffic to all domains");
no production domain accepts cleartext — the deployed backend is HTTPS-only.
**Action (hardening item):** move the loopback exception to the debug build's
manifest so release builds carry no cleartext scope at all.

## Warnings, each triaged

| Finding | Triage |
|---|---|
| Services/receivers "protected by a permission not defined in the app" (ChatAccessibilityService, GamingKeyboardService, GameNotificationService, AdminReceiver, WorkManager/androidx components) | **False positives.** These are `BIND_ACCESSIBILITY_SERVICE`, `BIND_INPUT_METHOD`, `BIND_NOTIFICATION_LISTENER_SERVICE`, `BIND_DEVICE_ADMIN`, `BIND_JOB_SERVICE` — *system-signature* permissions only the OS can hold. This is the mandatory platform contract for exactly these component types; an accessibility service or IME cannot exist without it. |
| Base config trusts system certificates | Standard and intended (system CA store only; **user-added CAs are not trusted**, which is the setting that matters against local MITM). |
| minSdk 26 (Android 8.0) | Deliberate device-coverage decision for the Indian mid-range market; accepted risk, documented. Revisit (→ 29) at scale. |
| IP address disclosure (`ServerUrl.java`) | The dev-server IP constants behind the developer server-URL override; same loopback/dev class as the high finding. |
| Temp file creation (`com/sun/jna/Native.java`) | Third-party library internals (JNA, a Vosk STT dependency) — not app code, no sensitive app data involved. |
| External-storage read/write (`MPAndroidChart` FileUtils, Vosk `StorageService`) | Library *capabilities*: chart-image export (unused) and Vosk unpacking its **model files** (not user data) to app storage. No chat text, audio, or credentials are written to external storage; app secrets live in `EncryptedSharedPreferences`. |
| "Hardcoded" strings (`ChatUploadQueue`, `OfflineSessionBuffer`) | SharedPreferences **key names**, not secrets. |
| "Possible hardcoded secrets" (Parent) | The Firebase **client** API key from `google-services.json` — public by design in every Android app using Firebase (access is controlled server-side), plus NIST elliptic-curve constants from the crypto library (false positives). The standing decision item on Firebase key rotation is unchanged by this finding. |

## Verdict

**No exploitable high-severity issue in either app.** The one genuine hardening
action produced by the audit is scoping the development-loopback cleartext
exception to debug builds. The audit does **not** replace a human penetration
test (stated as future work in the paper's Ethics and Limitations section), and
static analysis cannot prove the IME's runtime data-flow gates — those remain
covered by code review and the unit-test suite.

## Reproduce

```bash
docker run -d --name mobsf -p 8000:8000 -e MOBSF_API_KEY=<key> \
  opensecurity/mobile-security-framework-mobsf:latest
# upload the release APKs via the REST API (/api/v1/upload, /scan, /report_json)
```
