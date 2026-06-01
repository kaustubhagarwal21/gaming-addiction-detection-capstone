package com.pes.gamingdetector.util

/** In-app privacy copy, kept in sync with the project's PRIVACY.md / CONSENT_VERSION. */
object PrivacyText {

    const val CONSENT_VERSION = "2026-06-01"

    /** Short summary shown in the first-launch consent dialog. */
    const val CONSENT_SUMMARY = """
This device will be monitored by a parent to understand gaming wellbeing.

While you play a game, the app collects:
• which game is open and how long you play
• in-game chat that you type
• short voice clips to gauge tone — your spoken words are transcribed to text and
  kept; the raw audio is deleted right after analysis
• screen on/off, and the timing and titles of game notifications
• daily check-ins you choose to submit

It does NOT read messages outside games, your browsing, photos, contacts, or location.

Only your linked parent can see this data. You can delete all of it any time from Settings.

This is a wellbeing screening aid, not a diagnosis.
"""

    /** Full policy text shown from Settings → Privacy Policy. */
    const val POLICY = """Gaming Wellbeing Monitor — Privacy Policy
Consent version: 2026-06-01

WHAT IS COLLECTED (only on this device, only while playing games)
• Gaming activity — which game is in the foreground (any app the device classifies
  as a game) and session times. To recognise games the app checks the category of
  installed apps on the device; the list of installed apps is never uploaded.
• In-game chat you type — used for tone/toxicity signals. Not other players' messages.
• Short voice clips during a session — to estimate emotional tone. The raw audio is
  turned into numbers and deleted immediately (not stored or shared). The words you
  speak are also transcribed to text and kept, to read the tone of what was said.
• Screen on/off events (timing), and notifications from games — including the title
  of each game notification (e.g. event/reward prompts).
• Daily check-ins you voluntarily submit (mood/sleep/energy).

It does NOT collect messages outside games, browsing, contacts, photos, location,
or anything you type outside in-game chat.

WHO CAN SEE IT
Only the parent linked to this account (via your family PIN). The server checks a
signed token on every request and only lets a parent see their own children's data.
PINs are stored hashed, never as plaintext; production traffic uses HTTPS.

YOUR RIGHTS
From Settings you can Delete My Data (erase everything collected) at any time.

LIMITATIONS (stated honestly)
The models are demo-grade and the risk score is a screening signal, not a medical
diagnosis. Emotion labels (e.g. frustrated, angry, excited) are rough estimates from
the voice's tone plus a keyword reading of the words — indicative only, not accurate
emotion recognition. The tone model is adult-trained.

This tool is for a parent monitoring their own child as a wellbeing aid, with the
child's awareness — not covert surveillance.
"""
}
