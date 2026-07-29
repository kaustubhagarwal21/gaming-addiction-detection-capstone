package com.pes.gamingdetector.util

/** In-app privacy copy, kept in sync with the project's PRIVACY.md / CONSENT_VERSION. */
object PrivacyText {

    const val CONSENT_VERSION = "2026-07-30"

    /**
     * Consent recorded for a policy this APK does not contain cannot authorize
     * monitoring. Exact matching is deliberate: accepting a missing/different server
     * version could let an old APK resume after a newer policy was accepted elsewhere.
     */
    fun matchesServerVersion(serverVersion: String?): Boolean =
        serverVersion == CONSENT_VERSION

    /** Short summary shown in the first-launch consent dialog. */
    const val CONSENT_SUMMARY = """
This device will be monitored by a parent to understand gaming wellbeing.

While you play a monitored game, the app collects:
• which game is open and how long you play
• in-game chat that you type (only your own typing, never other players')
• short voice clips to gauge tone — the WAV audio is sent over HTTPS to your
  configured family server, analysed there, and deleted by default after processing;
  the transcript and derived emotion signals are kept

To spot late-night use and cravings, it also records — including between games:
• screen on/off timing, and the timing and titles of notifications from games

And the daily check-ins you choose to submit.

It does NOT read messages outside games, your browsing, photos, contacts, or location.

You can see your own wellbeing dashboard. Your linked parent can see and manage the
family’s monitoring data. The hosting provider processes uploaded data, and authorised
project operators can administer the backend for support and research maintenance.
The Parent app may use Google Firebase Cloud Messaging for optional alerts; Firebase
processes the Parent device's push token and alert text/routing fields, not raw voice
clips or your chat transcript. Alerts also remain available through secure app polling.

This is a wellbeing screening aid, not a diagnosis.
"""

    /** Full policy text shown from Settings → Privacy Policy. */
    const val POLICY = """Gaming Wellbeing Monitor — Privacy Policy
Consent version: 2026-07-30

WHAT IS COLLECTED FROM THIS DEVICE
While you are in a monitored game session:
• Gaming activity — which game is in the foreground (any app the device classifies
  as a game) and session times. To recognise games the app checks the category of
  installed apps on the device; the list of installed apps is never uploaded.
• In-game chat you type — used for tone/toxicity signals. Not other players' messages.
• Short voice clips — to estimate emotional tone. WAV audio is sent over HTTPS to
  the configured family server for feature extraction and transcription, then deleted
  by default after processing. Server operators can explicitly enable raw-audio
  retention for development/testing. Transcripts and derived emotion signals are kept.

Also, between sessions (to detect sleep disruption and cravings):
• Screen on/off events (timing only).
• Notifications from games — the timing and title of each (e.g. event/reward prompts).

When you choose to:
• Daily check-ins you voluntarily submit (mood/sleep/energy).

It does NOT collect messages outside games, browsing, contacts, photos, location,
or anything you type outside in-game chat.

WHO CAN SEE IT
The child can see their own wellbeing dashboard and check-ins. The linked parent
(signed in with the family code + PIN) can see that family's monitoring insights and
manage or delete them. The hosting provider stores/processes uploaded data, and
authorised project operators can administer the backend for support and research
maintenance. The Parent app may use Google Firebase Cloud Messaging for optional
alerts; Firebase processes the Parent device's push token and alert title/text plus
child/alert routing fields. Raw voice clips and your chat transcript are not sent to
Firebase for push delivery; authenticated in-app polling remains available. Data is
not sold or shared for advertising. The server checks signed tokens and family/role
access. PINs are stored hashed; production traffic uses HTTPS.

YOUR RIGHTS
Your parent can delete this data, or remove your account entirely, at any time from
the Parent app.

LIMITATIONS (stated honestly)
The models are demo-grade and the risk score is a screening signal, not a medical
diagnosis. Emotion labels (e.g. frustrated, angry, excited) are rough estimates from
the voice's tone plus a keyword reading of the words — indicative only, not accurate
emotion recognition. The tone model is adult-trained.

This tool is for a parent monitoring their own child as a wellbeing aid, with the
child's awareness — not covert surveillance.
"""
}
