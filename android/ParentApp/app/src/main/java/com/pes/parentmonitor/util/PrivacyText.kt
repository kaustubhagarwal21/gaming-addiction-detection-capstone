package com.pes.parentmonitor.util

/** In-app privacy copy, kept in sync with the project's PRIVACY.md. */
object PrivacyText {
    const val POLICY = """Gaming Wellbeing Monitor — Privacy Policy
Consent version: 2026-06-01

This is a parental wellbeing tool. You install the Child app on your child's
device to understand their gaming patterns and wellbeing, and view insights here.
It is a screening/awareness aid, not a medical or diagnostic device.

WHAT IS COLLECTED (only on the child's device)
While the child is in a monitored game session:
• Gaming activity — which game is open (any app the device classifies as a game)
  and session times. To recognise games the app checks the category of installed
  apps on the device; the list of installed apps is never uploaded.
• In-game chat the child types — for tone/toxicity signals (not other players').
• Short voice clips — to estimate tone. The raw audio is converted to numbers and
  deleted immediately (never stored or shared). The words spoken are also transcribed
  to text and kept, to read the tone of what was said.

Also, between sessions (to detect sleep disruption and cravings):
• Screen on/off events (timing only).
• Notifications from games — the timing and title of each.

When they choose to:
• Daily check-ins the child voluntarily submits.

It does NOT collect messages outside games, browsing, contacts, photos, or location.

WHO CAN SEE IT
Only you, the linked parent (you sign in with your family code + PIN). The server
checks a signed token on every request, only lets you see your own children's data,
and restricts parent-only actions and views to a parent account. PINs are stored
hashed; production uses HTTPS.

YOUR RIGHTS
From Settings you can delete a child's collected data, or remove the child entirely,
at any time.

LIMITATIONS (stated honestly)
The models are demo-grade; the risk score is a screening signal, not a diagnosis.
Emotion labels (e.g. frustrated, angry, excited) are rough estimates from the voice's
tone plus a keyword reading of the words — indicative only, not accurate emotion
recognition. The tone model is adult-trained.

This tool is for monitoring your own minor child as a wellbeing aid, with the
child's awareness — not covert surveillance.
"""
}
