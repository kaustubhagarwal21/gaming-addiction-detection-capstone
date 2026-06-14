
Findings
High: child can read and mark parent alerts as read. /api/alerts and /api/alerts/mark_read use guard() but not deny_non_parent(), so a child token can access their own parent alert feed and mark tamper/risk alerts read. See backend/app.py (line 3515) and backend/app.py (line 3550).

High: consent can be bypassed after reboot. HomeActivity gates monitoring behind consent, but BootReceiver starts PassiveMonitorService whenever the child is logged in, even if consent was declined or never completed. See HomeActivity.kt (line 84) and BootReceiver.kt (line 13).

High: consent is still child-controlled. Backend POST /api/consent accepts the child token via guard(user_id) and does not require a parent role. The Child app shows the “I Agree” dialog and then starts monitoring. See backend/app.py (line 2314) and HomeActivity.kt (line 236).

High: changing family PIN breaks multi-child families. Parent login groups children by family_code + parent_pin_hash, but /api/user/update changes parent_pin_hash only for one user row. New PIN sees only that child; old PIN may still access siblings. See backend/app.py (line 2123) and backend/app.py (line 2241).

High: child PIN update bypasses registration rules. Registration enforces 4-6 digit PINs and rejects duplicate child PIN hashes, but /api/user/update writes a new pin_hash without length/digit/duplicate checks. This can create invalid or colliding logins. See backend/app.py (line 2047), backend/app.py (line 2062), and backend/app.py (line 2229).

Medium: deleting data also deletes guardian push tokens. _delete_user_data() removes guardian_devices even for scope="data"; Parent Settings calls that when deleting data but keeping the child account. One-child families lose FCM alerts until re-login. See backend/app.py (line 2272), backend/app.py (line 2372), and SettingsActivity.kt (line 143).

Medium: game notification titles are collected outside active play. GameNotificationService uploads any notification from a package classified as a game when logged in; it does not require an active session. This conflicts with the “only during gaming” privacy promise. See GameNotificationService.kt (line 14) and backend/app.py (line 3847).

Medium: auto-end loses server session state on network failure. performAutoEnd() clears local session state even if endSession() fails or throws, leaving the backend session open/stale. See PassiveMonitorService.kt (line 434).

Medium: deleted child can still be targeted by old parent token. Parent tokens contain a static allowed list. After account deletion, old tokens can still pass guard() for that user id and insert orphan rows like nudges/limits because these tables lack user foreign keys. See backend/app.py (line 163), backend/app.py (line 2374), and backend/app.py (line 3970).

Medium: parent risk notification memory is global, not per child. Alert IDs were fixed per-child, but lastRiskLevel and riskNotifiedAt are shared across children, so switching siblings can suppress risk notifications. See PrefsManager.kt (line 45) and AlertPollingService.kt (line 94).

Medium: backend tests cannot currently import the app locally. python -m pytest tests/ -q fails before running tests because pandas/pyarrow were compiled against NumPy 1.x while this env has numpy 2.4.4. The import dies at backend/app.py (line 27).

High: Child tokens can access parent-only reports.
Routes like parent dashboard, emotions, chat analysis, feedback summary, weekly report/PDF, and anomalies only call guard(user_id), so a child token for its own user_id passes. Add deny_non_parent() to parent-facing report/resolve endpoints.
Refs: backend/app.py (line 3001), backend/app.py (line 3301), backend/app.py (line 3345), backend/app.py (line 4108), backend/app.py (line 4485)

High: Ending a session is not idempotent.
Calling /api/session/<sid>/end twice recalculates end_time, rewrites duration, creates another prediction, and can create duplicate alerts. This can happen from manual end plus passive auto-end/retry.
Refs: backend/app.py (line 2539), backend/app.py (line 2558), backend/app.py (line 2566), SessionActivity.kt (line 87), PassiveMonitorService.kt (line 434)

High/Medium: Backend auto-closes stale/open sessions without final scoring.
_close_stale_sessions() and the “close previous open session” path update end_time directly, but skip final behavioral snapshot, prediction, alert creation, and streak update. Lost end-events can become invisible in risk history.
Refs: backend/app.py (line 2397), backend/app.py (line 2443), backend/app.py (line 2477)

Medium: Child nudges are marked delivered before display succeeds.
GET /api/child/nudges marks rows delivered immediately; the child app may then fail to post the notification if permission is denied or the app dies. Parent nudges can silently disappear.
Refs: backend/app.py (line 4003), backend/app.py (line 4009), PassiveMonitorService.kt (line 171), PassiveMonitorService.kt (line 204)

Medium: Parent alert polling marks alerts as notified even when Android notification permission is denied.
The service advances lastNotifiedAlertId after calling sendAlertNotification, but notify() is skipped if POST_NOTIFICATIONS is not granted. Granting permission later will not show missed alerts.
Refs: AlertPollingService.kt (line 85), AlertPollingService.kt (line 136)

Medium: Offline chat retry queue drops messages on HTTP failures.
ChatUploadQueue.flush() treats any HTTP response as delivered. A 500/503/401 response will remove the captured chat line from the queue even though the backend did not save it.
Refs: ChatUploadQueue.kt (line 63), ChatUploadQueue.kt (line 69)

Medium: A 0h parent time limit is allowed but ignored by child dashboards/warnings.
Backend accepts limits from 0 to 24, but later uses if daily_limit and bool(daily_limit), so 0.0 becomes “no parent limit set” and the child app falls back to the default goal.
Refs: backend/app.py (line 3944), backend/app.py (line 4071), backend/app.py (line 4090), GameMonitorService.kt (line 99)

Low/Medium: Fresh default seed and Postgres smoke test are stale against family-code login.
init_db() creates the default user without family_code, but parent login now requires one. pg_smoketest.py also seeds users without family_code and logs parent in without it, so that smoke path is broken.
Refs: backend/app.py (line 951), backend/app.py (line 2116), pg_smoketest.py (line 37), pg_smoketest.py (line 68)