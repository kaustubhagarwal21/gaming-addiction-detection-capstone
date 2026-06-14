package com.pes.gamingdetector.util

/** In-app privacy copy, kept in sync with the project's PRIVACY.md / CONSENT_VERSION. */
object PrivacyText {

    const val CONSENT_VERSION = "2026-06-01"

    /** Short summary shown in the first-launch consent dialog. */
    const val CONSENT_SUMMARY = """
This device will be monitored by a parent to understand gaming wellbeing.

While you play a monitored game, the app collects:
• which game is open and how long you play
• in-game chat that you type (only your own typing, never other players')
• short voice clips to gauge tone — your spoken words are transcribed to text and
  kept; the raw audio is deleted right after analysis

To spot late-night use and cravings, it also records — including between games:
• screen on/off timing, and the timing and titles of notifications from games

And the daily check-ins you choose to submit.

It does NOT read messages outside games, your browsing, photos, contacts, or location.

Only your linked parent can see this data, and they manage it (including deleting it) from the Parent app.

This is a wellbeing screening aid, not a diagnosis.
"""

    /** Full policy text shown from Settings → Privacy Policy. */
    const val POLICY = """Gaming Wellbeing Monitor — Privacy Policy
Consent version: 2026-06-01

WHAT IS COLLECTED (only on this device)
While you are in a monitored game session:
• Gaming activity — which game is in the foreground (any app the device classifies
  as a game) and session times. To recognise games the app checks the category of
  installed apps on the device; the list of installed apps is never uploaded.
• In-game chat you type — used for tone/toxicity signals. Not other players' messages.
• Short voice clips — to estimate emotional tone. The raw audio is turned into numbers
  and deleted immediately (not stored or shared). The words you speak are also
  transcribed to text and kept, to read the tone of what was said.

Also, between sessions (to detect sleep disruption and cravings):
• Screen on/off events (timing only).
• Notifications from games — the timing and title of each (e.g. event/reward prompts).

When you choose to:
• Daily check-ins you voluntarily submit (mood/sleep/energy).

It does NOT collect messages outside games, browsing, contacts, photos, location,
or anything you type outside in-game chat.

WHO CAN SEE IT
Only the parent linked to this account (they sign in with your family code + PIN).
The server checks a signed token on every request, only lets a parent see their own
children's data, and restricts parent-only actions and views to the parent. PINs are
stored hashed, never as plaintext; production traffic uses HTTPS.

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
