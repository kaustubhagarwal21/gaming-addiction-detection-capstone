# Gemini Nano: defence Q&A

Answers for questions on the Gemini Nano suggestion. Facts are from Google's documentation as checked on 23 Nov 2026; the full record and its sources are in `docs/GEMINI_NANO_FEASIBILITY.md`. Our own numbers match `tools/project_numbers.py`.

**Q1 (owner: Kaustubh). Why not replace your chat and voice models with Gemini Nano? Wouldn't an LLM be more accurate?**

It might be on some inputs, but nobody has measured it on gaming chat. We could not measure it either, because our test phone is unsupported. Our chat model is measured:

- PR-AUC is 0.821 on held-out gaming chat as served (0.825 for the recipe under the ablation protocol).
- At the 0.95 alert threshold, precision is 0.956 and recall is 0.428.
- Precision is 0.968 on Devanagari Hindi and 0.958 on romanised Hindi.

That threshold works only because our scores are calibrated probabilities. Nano returns text with no probabilities and may answer differently on another phone or model version. Google publishes no toxicity or Hindi accuracy for it. Size alone is no guarantee: toxic-BERT, a larger general model, reached only 0.709 PR-AUC on the same gaming-chat test. For voice the answer is a firmer no. Our model reads emotion from 36 tone features. The Prompt API takes only text and images, and the speech API returns words, timings and an audio level, not tone. Google's own Nano 4 example is a moderation prompt, so the capability is real. What is missing is calibration, validation and access on our users' phones.

**Q2 (owner: Kaustubh). Did you actually test Gemini Nano, or only read about it?**

We only read about it, but carefully. We downloaded Google's pages on 23 Nov 2026, checked every quoted sentence, and left out anything we could not confirm. We could not run Nano because no supported phone was available:

- Our Galaxy M52 (Snapdragon 778G) is on no supported list.
- AICore needs Android 14, and the M52 stops at Android 13.
- None of us owns a supported phone.

So we claim no accuracy, latency or battery number for Nano. The test is ready to run:

- **Who and where:** adult team members, a borrowed supported phone and a separate test app.
- **Setup:** a frozen prompt at temperature 0 with a fixed seed.
- **Data:** our held-out CONDA chat and the 933-row Hindi hold-out.
- **Measures:** PR-AUC and precision at the alert threshold, compared with our deployed model on the same lines. Safety-filter refusals count as misses, and we would run our device drill during a game.

We would switch only if Nano reached at least 0.95 precision in English, Devanagari and romanised Hindi, and if the terms and background rules allowed it.

**Q3 (owner: Khushee). Why can't the ChildApp run Gemini Nano on the phone while the child plays, at least on phones that support it?**

Google permits Gemini Nano inference only when the calling app is the top foreground app, and during play the top app is the game.

- **Foreground services are refused.** Our voice recorder and session monitor run as foreground services. Google's overview says calls from a foreground service get a BACKGROUND_USE_BLOCKED error. Google has documented this since May 2025, when the error was BUSY.
- **Keyboards and accessibility services are untested.** Google says nothing either way about them, and they are how we capture chat. We could not test them without a supported phone.
- **The terms rule out the ChildApp.** The ML Kit GenAI terms exclude apps likely to be accessed by under-18s. That applies on every phone, supported or not.
- **Even supported phones have quotas.** There is a per-app request quota and a long-duration battery quota, both with unpublished limits. The phone is also already running a game. Our own device gate rejected a second speech recogniser on the M52: it used 51–72% of a core, against 14% for the default path.

Nano can fit as a foreground feature on the parent's phone. It would sit behind a capability check, with today's system as the fallback.

**Q4 (owner: Khushee). Isn't on-device AI better for the child's privacy than sending data to your server?**

Yes. Privacy is the strongest argument for Gemini Nano, and it is why we studied it instead of dismissing it. Part of our voice pipeline already stays on the phone. Vosk turns speech into text on the device. The server receives 10-second clips only while the monitored game is in front, extracts tone features and deletes the audio. But typed lines, transcripts and those clips do reach our server, so Nano would be a real privacy gain. It cannot deliver that gain to our users today:

- The terms exclude apps used by children.
- Inference is blocked while the game is in front.
- Our test phone and Samsung's Galaxy A, M and F phones are not supported.

Until that changes, we limit what the server holds in three ways. Consent fails closed, audio is deleted after feature extraction, and parents can export or delete the data.

**If anyone is asked (every team member, same words):** "We studied Gemini Nano against Google's own documentation, and it is genuinely good for privacy. But today its terms exclude apps used by children, it only works while its own app is on screen, and it does not run on our test phone or on Samsung's A, M and F phones. So we keep our validated models, and we will benchmark Nano as soon as that changes."
