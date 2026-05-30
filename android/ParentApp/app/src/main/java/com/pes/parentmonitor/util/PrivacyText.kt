package com.pes.parentmonitor.util

/** In-app privacy copy, kept in sync with the project's PRIVACY.md. */
object PrivacyText {
    const val POLICY = """Gaming Wellbeing Monitor — Privacy Policy
Consent version: 2026-05-30

This is a parental wellbeing tool. You install the Child app on your child's
device to understand their gaming patterns and wellbeing, and view insights here.
It is a screening/awareness aid, not a medical or diagnostic device.

WHAT IS COLLECTED (only on the child's device, only during supported games)
• Gaming activity — which known game is open and session times.
• In-game chat the child types — for tone/toxicity signals (not other players').
• Short voice clips during a session — to estimate tone. Raw audio is converted to
  numbers and deleted immediately; it is never stored or shared.
• Screen on/off and game-notification timing.
• Daily check-ins the child voluntarily submits.

It does NOT collect messages outside games, browsing, contacts, photos, or location.

WHO CAN SEE IT
Only you, the linked parent. The server checks a signed token on every request and
only lets you see your own children's data. PINs are stored hashed; production uses HTTPS.

YOUR RIGHTS
From Settings you can delete a child's collected data at any time.

LIMITATIONS (stated honestly)
The models are demo-grade; the risk score is a screening signal, not a diagnosis.
The voice model estimates tone/arousal, not specific emotions.

This tool is for monitoring your own minor child as a wellbeing aid, with the
child's awareness — not covert surveillance.
"""
}
