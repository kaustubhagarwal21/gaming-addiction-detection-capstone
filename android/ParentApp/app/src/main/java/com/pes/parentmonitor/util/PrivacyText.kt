package com.pes.parentmonitor.util

/** In-app privacy copy, kept in sync with the project's PRIVACY.md. */
object PrivacyText {
    const val POLICY = """Gaming Wellbeing Monitor — Privacy Policy
Consent version: 2026-07-30

This is a parental wellbeing tool. You install the Child app on your child's
device to understand their gaming patterns and wellbeing, and view insights here.
It is a screening/awareness aid, not a medical or diagnostic device.

WHAT IS COLLECTED
While the child is in a monitored game session:
• Gaming activity — which game is open (any app the device classifies as a game)
  and session times. To recognise games the app checks the category of installed
  apps on the device; the list of installed apps is never uploaded.
• In-game chat the child types — for tone/toxicity signals (not other players').
• Short voice clips — to estimate tone. A clip is sent over the configured HTTPS
  connection to this project's backend, converted to emotion/features, and deleted
  there by default. Spoken words are transcribed on the device; that transcript is
  also sent and kept.

Also, between sessions (to detect sleep disruption and cravings):
• Screen on/off events (timing only).
• Notifications from games — the timing and title of each.

When they choose to:
• Daily check-ins the child voluntarily submits.

It does NOT collect messages outside games, browsing, contacts, photos, or location.

WHO CAN SEE IT
The child can see their own wellbeing dashboard and voluntary check-ins. You, the
linked parent, can see your family's monitoring insights after signing in with the
family code + PIN. The server checks signed tokens and restricts data by family and
role. The hosting provider processes the uploaded data, and authorised project
operators can technically administer the service for support and maintenance.
Google Firebase Cloud Messaging processes this Parent device's push token and the
alert title/text plus child/alert routing fields needed to deliver optional push
notifications. Raw voice clips and chat transcripts are not sent to Firebase for
push delivery; alerts also remain available through authenticated in-app polling.
Data is not sold or shared for advertising. PINs are stored hashed.

CONSENT AND RETENTION
Monitoring starts only after this policy is accepted on the Child device and the
family PIN is confirmed. A timestamp and policy version are recorded; a policy
change requires consent again. Raw audio is deleted after feature extraction in
production. Other records remain until the parent deletes the data/account, unless
the deployment has a shorter configured retention period.

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
