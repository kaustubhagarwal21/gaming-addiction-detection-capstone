# Gemini Nano for the chat and voice channels: feasibility study and decision

PW26_SAS-03 · documentation checked 23 Nov 2026 · owners: Kaustubh Agarwal (models), Khushee P Kiran (Android devices)

**Decision:** we keep our validated server-side models as the primary path. We will benchmark Gemini Nano on our held-out chat data once we can use a supported phone, and reopen the decision if the conditions in section 6 change.

## 1. The suggestion

The suggestion, as put to us: *use the Gemini Nano API for text and voice instead of our ML models.* Today:

- **Chat:** the child's own typed chat, captured by our keyboard and an accessibility service. On the server, TF-IDF n-grams feed a calibrated logistic regression, fused with keyword matching. It was trained on a general toxicity corpus plus gaming chat (CONDA), Davidson tweets and HASOC Hindi.
  - PR-AUC on held-out gaming chat: 0.821 as served (0.825 for the recipe under the ablation protocol).
  - At the 0.95 alert threshold: precision 0.956, recall 0.428.
  - Hindi precision: 0.968 (Devanagari), 0.958 (romanised).
- **Voice:** Vosk transcribes on the phone. The server extracts 36 tone features from 10-second clips and then deletes the audio.
  - Emotion from tone: 0.574 on unseen speakers (4 classes, chance 0.25).
  - Accent audit on 6,656 Indian-English clips: 0 false alerts.
- **Scoring:** chat gives calibrated probabilities, so a fixed alert threshold means the same thing for every family. Chat and voice scores both enter the 40/30/30 fusion. All of this runs on our server, so any phone works.

## 2. What Gemini Nano is, and why it is attractive

Gemini Nano is Google's on-device foundation model. Apps reach it through ML Kit's GenAI APIs:

- a Prompt API (text or image in, text out);
- task APIs such as summarisation;
- speech APIs.

These run on AICore, the Android service that downloads, updates and accelerates the model.

The appeal is real:

- **Privacy.** Input, inference and output stay on the phone. Our system sends typed lines, transcripts and voice clips to a server.
- **Cost.** It works offline, with no server cost per call.
- **Reach.** Google reports Nano on over 140 million devices (July 2026).
- **Capability.** Google's own Nano 4 example prompt is a check for profanity and hate speech.

The privacy gain is why we studied it carefully.

## 3. What we checked and how

We checked Google's official documentation: the ML Kit GenAI overview, Prompt API and speech pages, API reference, release notes, terms of service, and Android Developers pages and blog. We added our test phone's specifications and Indian market data from Counterpoint, IDC and ASER 2024.

On 23 Nov 2026 we downloaded every page fresh and found each quoted sentence in it. Wayback Machine copies date the background rule. Claims we could not confirm are flagged or dropped.

**We could not run Nano.** Our Galaxy M52 is unsupported and none of us owns a supported phone. No Nano accuracy, latency or battery figure here is our own measurement.

## 4. Findings

| Requirement of our system | What Gemini Nano offers today | Source |
|---|---|---|
| **Allowed on a child's phone** | The terms forbid using the APIs in apps "directed towards or is likely to be accessed by individuals under the age of 18". They also forbid clinical use and production use of "Preview" services. | TERMS |
| **Our test phone** (Galaxy M52 5G, Snapdragon 778G, SM7325) | It is on no device list. AICore needs Android 14 or later, and the M52 ends at Android 13 (GSMArena). SM7325 is not a supported chipset for Gemini speech recognition. | OV, AICORE, GSMA, QC, SR |
| **Typical Indian children's phones** | The Prompt API supports 110 device models. The only Samsung models are Galaxy S25/S26, Tab S12 and Z Flip/Fold; there is no Galaxy A, M or F. Some phones under ₹30,000 qualify (POCO X7 Pro, ₹26,999 at launch). In 2025, 78% of Indian shipments cost ₹30,000 or less, and Samsung's volume is the Galaxy A series. Of rural 14–16-year-olds who can use a smartphone, 31.4% own one. No India coverage figure is published. | OV, BS-POCO, CP-PREM, CP-Q3, ASER |
| **Running while a game is in front** | Inference runs only for "the top foreground application"; a foreground service gets BACKGROUND_USE_BLOCKED. This is documented since May 2025, first as a BUSY error. Keyboards and accessibility services are not mentioned, and we have not tested them. | OV, ERR, WAYBACK |
| **Tone of voice** | Prompt API input is text and images, with no audio. Speech recognition returns text, word timings and a 0–100 audio level, but no pitch, emotion or confidence. Gemini mode needs a Pixel 10/11 or one of nine high-end chipsets; Basic mode uses a traditional recogniser. | PA, PKG, SR, SRAPI |
| **Hindi and code-mixed chat** | The Prompt API lists no languages; its April 2026 revision listed English and Korean. The task APIs have no Hindi. Speech recognition (beta) and text-to-speech support Hindi. Nothing is published on romanised or code-mixed Hindi. | PAGS, WAYBACK, TASKS, SR, TTS |
| **Calibrated scores (0.95 threshold, fusion)** | Output is text only: a finish reason (STOP, MAX_TOKENS or OTHER), the text and any function calls. There are no probabilities and at most 8 deduplicated candidates. Model versions may answer differently, and safety filters check input and output. | CAND, GCR, OV, EVAL |
| **Measured accuracy** | Google publishes no toxicity accuracy and tells developers to build their own test set. We could not measure it. For scale, toxic-BERT, a larger model, scored PR-AUC 0.709 on our gaming-chat test, against our 0.825. | EVAL, ours |
| **Compute and battery in play** | There is a per-app request quota and a long-duration (e.g. daily) battery quota, both with unpublished limits. Downloading Nano V4 needs 4.0 GB free. Its cost beside a running game is unmeasured. Our device gate already rejected a second recogniser on the M52 (51–72% of a core, against 14%). | OV, ERR, ST, ours |
| **Stable API** | The Prompt API is in beta, speech in alpha and the task APIs at 1.0.0-beta1. None has an SLA or deprecation policy. Nano 4 is in production on the Galaxy Z Flip8 and Fold8, and in preview elsewhere. | PA, SR, REL, FC |

## 5. Decision

We keep the validated server-side models as the primary path. Reasons, most decisive first:

1. **The terms rule out the ChildApp on every phone.** It runs on a child's phone, so it is an app "likely to be accessed by individuals under the age of 18".
2. **The background rule blocks the moment that matters.** Chat and speech happen while the game is the top app. Our recorder and monitor are foreground services, and Google says calls from those are refused. An exemption for our keyboard or accessibility service is undocumented and untested.
3. **Our test phone and Samsung's volume phones are unsupported.** The app must work on whatever phone the family has.
4. **Voice needs tone, and Nano takes no audio.** At most it could supply words, which Vosk already does on the phone.
5. **Chat needs calibrated, validated scores.** A calibrated 0.95 means about 95 in 100 such lines are toxic; we measured 0.956. Nano gives text without probabilities, varies by phone and version, publishes no Hindi or Hinglish accuracy, and we could not measure it.
6. **The APIs are not yet stable.** They are alpha or beta, have no SLA and have unpublished quotas.

Google's own guidance agrees. It calls cloud models "a critical fallback when on-device models, such as Gemini Nano, are unavailable due to device hardware or OS constraints". Our server already plays that role.

## 6. What would change our mind

Conditions 1 and 2 are needed for any use on the child's phone; conditions 3 to 6 decide whether to switch.

1. The terms allow apps used by under-18s.
2. There is a documented way to run inference while another app is in front, and it works on a real phone.
3. Galaxy A/M-class and ₹15,000–20,000 phones are supported. Counterpoint expects GenAI to reach cheaper phones as memory costs ease.
4. The API gives calibrated scores and, for voice, reads tone from audio.
5. Nano matches our models under 7.2 on two devices and passes our device gate.
6. The API reaches general availability, with a deprecation policy and published quotas.

## 7. Future plan

**7.1 Optional on-device feature, parent side first.** The ParentApp could write a plain-language weekly summary on the guardian's phone while the app is open, so it is in the foreground.

- It runs only when a capability check reports Nano is available. Otherwise, or on any BUSY, quota or background error, the app shows today's server text.
- It never produces scores, bands or alerts.
- It starts in English, since summarisation supports English, Japanese and Korean.
- Adults use the ParentApp, but we would confirm the terms before building it.

Mira's replies would be a natural foreground use. But Mira lives in the ChildApp, so the age clause rules it out until the terms change.

**7.2 Evaluation before any switch.**

1. **Setup:** a borrowed supported phone, a separate test app and adult testers. Log the model, Android version and Nano version (`getBaseModelName()`). Use no ChildApp and no child data.
2. **Data:** the CONDA validation split (7,721 lines, 21.5% toxic) and the 933-row Hindi hold-out (Devanagari and romanised).
3. **Prompt:** ask for a label and a 0–100 toxicity rating, at temperature 0 with a fixed seed. Freeze the prompt on training lines first.
4. **Metrics:**
   - PR-AUC.
   - Precision and recall at the cut-off nearest our alert precision.
   - Refusals and malformed outputs count as misses.
   - 1,000-resample bootstrap intervals.
   - Our deployed model re-scored on the same lines.
5. **Device:** latency, CPU, memory and battery over two 15-minute game sessions, repeated on a second device.
6. **Switch rule:** switch only if all of these hold:
   - Precision is at least 0.95 in English, Devanagari and romanised Hindi.
   - The PR-AUC interval is not below ours.
   - The device gate passes.
   - Conditions 1 and 2 hold.

There is nothing to benchmark for voice until an API reads tone. Any change of recogniser would first repeat the 6,656-clip accent audit.

**7.3 Not evaluated.**

- **Gemma models inside our app via LiteRT-LM.** This is not Gemini Nano, so AICore's rules and the ML Kit terms do not apply. We have not checked Gemma's licence, and the same device gate and calibration needs apply.
- **Cloud Gemini.** It would send the child's chat to a third party.

## 8. Claims we do not make

- **"Nano can't classify toxicity."** Google's own Nano 4 example is a moderation prompt.
- **"Nano has no Hindi."** Speech recognition and text-to-speech have it; the Prompt API simply lists no languages.
- **"Flagship-only."** Some phones under ₹30,000 qualify.
- **"Keyboards are blocked too."** This is undocumented and untested.
- **"Nano 4 is not shipping."** This is outdated.

We also dropped Google's policy line on monitoring without consent, because our app is consent-gated and parents review alerts.

## 9. Sources

All accessed 23 November 2026. The date after each label is the page's own.

**ML Kit documentation**

- **OV** (2026-11-10): https://developers.google.com/ml-kit/genai
- **TERMS** (modified 14 May 2025): https://developers.google.com/ml-kit/genai-terms
- **PA:** https://developers.google.com/ml-kit/genai/prompt/android
- **PAGS:** https://developers.google.com/ml-kit/genai/prompt/android/get-started
- **EVAL:** https://developers.google.com/ml-kit/genai/prompt/android/evaluate-prompt
- **FC** (2026-11-18): https://developers.google.com/ml-kit/genai/prompt/android/function-calling
- **SR** (2026-11-14): https://developers.google.com/ml-kit/genai/speech-recognition/android
- **ST:** https://developers.google.com/ml-kit/genai/speech-translation/android
- **TTS:** https://developers.google.com/ml-kit/genai/text-to-speech/android
- **TASKS:**
  - https://developers.google.com/ml-kit/genai/summarization/android
  - https://developers.google.com/ml-kit/genai/proofreading/android
  - https://developers.google.com/ml-kit/genai/rewriting/android
- **REL** (2026-11-09): https://developers.google.com/ml-kit/release-notes

**API reference**

- **ERR:** https://developers.google.com/android/reference/com/google/mlkit/genai/common/GenAiException.ErrorCode
- **CAND:** https://developers.google.com/android/reference/com/google/mlkit/genai/prompt/Candidate
- **GCR:** https://developers.google.com/android/reference/kotlin/com/google/mlkit/genai/prompt/GenerateContentRequest
- **PKG:** https://developers.google.com/android/reference/com/google/mlkit/genai/prompt/package-summary
- **SRAPI:** https://developers.google.com/android/reference/kotlin/com/google/mlkit/genai/speechrecognition/SpeechRecognizerResponse.AudioLevelResponse

**AICore and Android guidance**

- **AICORE:** https://support.google.com/android/answer/17065362
- Android guidance:
  - https://developer.android.com/ai/gemini-nano
  - https://developer.android.com/ai/hybrid
  - https://developer.android.com/ai/overview
- Android Developers Blog:
  - https://android-developers.googleblog.com/2026/07/android-on-device-inference.html
  - https://android-developers.googleblog.com/2026/04/AI-Core-Developer-Preview.html
- **WAYBACK** (plus the 20250617115529 and 20251005182459 snapshots):
  - https://web.archive.org/web/20250523030011/https://developers.google.com/ml-kit/genai
  - https://web.archive.org/web/20260516014504/https://developers.google.com/ml-kit/genai/prompt/android/get-started

**Test phone**

- **SAMSUNG:** https://news.samsung.com/in/samsung-launches-galaxy-m52-5g-in-india-its-leanestmeanestmonsterever
- **GSMA:** https://www.gsmarena.com/samsung_galaxy_m52_5g-11110.php
- **QC:** https://www.qualcomm.com/content/dam/qcomm-martech/dm-assets/documents/Snapdragon-778G-5G-Product-Brief.pdf

**Indian market**

- **BS-POCO** (9 Jan 2025): https://www.business-standard.com/technology/gadgets/poco-x7-series-debuts-xiaomi-hyperos-2-in-india-check-price-specs-more-125010901066_1.html
- **CP-PREM** (2 Feb 2026): https://counterpointresearch.com/en/insights/Premiumization-Gains-Strength-in-India-Smartphone-Market-in-2025-Apple-Records-its-Highest-Ever-Value-Share
- **CP-Q3** (23 Oct 2026): https://counterpointresearch.com/en/insights/india-smartphone-market-slumps-20-yoy-in-q3-sub-inr-20000-shipments-nearly-halve
- **Counterpoint GenAI** (22 Jun 2026): https://counterpointresearch.com/en/insights/genai-smartphone-share-to-rise-to-45-percent-of-global-shipments-in-2026
- **ASER 2024:** https://asercentre.org/wp-content/uploads/2022/12/ASER-2024-All-India-ppt-Jan-27-11am.pdf

**Our own evidence**

- `docs/ablation_results.json`
- `tools/project_numbers.py`
- `docs/asr_fairness.json`
- `TESTING.md` (device drill, 18 Aug 2026)
