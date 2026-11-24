# Hyperparameter studies: defence Q&A

Answers for questions on hyperparameter tuning. Sources: `ml/hparam_behaviour.py`, `ml/hparam_chat.py`, `ml/hparam_voice.py` and their results in `docs/hparam_behaviour.json`, `docs/hparam_chat.json`, `docs/hparam_voice.json`; every number below matches `tools/project_numbers.py` (the `hp_*` keys). Protocol in one line: search on training data only, each test set scored once for two settings (deployed and search winner), paired bootstrap of the difference over 1,000 resamples.

**Q1 (owner: Kaustubh). Did you tune the hyperparameters?**

Yes, for all three models, under a protocol that keeps every test set clean. Each grid was searched on training data only: 120 random-forest settings for behaviour, 14 logistic-regression settings for chat and 54 gradient-boosting settings for voice, 188 in all. Each test set was then scored exactly once for two settings, the deployed one and the search winner, with a paired bootstrap of the difference. The hand-set values sit in the middle of their grids (rank 69 of 120, 8 of 14 and 29 of 54). Only behaviour shows a measurable test gain, +0.0113 [+0.0063, +0.0165] accuracy, and it is measured on simulated labels.

**Q2 (owner: Kaustubh). Why did you not run a grid search earlier?**

Honestly, the hand-set values looked reasonable, and our effort went into data, features and leakage-free evaluation instead; the ablations show that was the right order. On the same test sets, removing the gaming-chat corpus cuts chat PR-AUC from 0.825 to 0.511, and the earlier 17-feature voice set reaches 0.499 against 0.562, while the largest tuning effect is about one accuracy point. A search is also only meaningful with a leakage-free protocol: folds grouped by speaker for voice, and for chat a validation slice whose duplicates are all removed from training. The studies reuse the ablation code for exactly that reason. The starting points were sensible: C = 1 and the 0.1 learning rate are the library defaults, and the shallow forest was a deliberate choice.

**Q3 (owner: Kaustubh). Why not deploy the tuned model?**

For chat and voice there is nothing better to deploy. The chat winner, C = 8, is worse on held-out gaming chat (PR-AUC -0.0100 [-0.0167, -0.0035]), and the voice winner differs by +0.0021 [-0.0117, +0.0154], an interval that spans zero. The behaviour winner is better on the test rows, +0.0113 [+0.0063, +0.0165], but those rows carry simulated labels, so the gain measures fit to our simulator, not to children. Adopting it would mean unlimited-depth trees that reproduce their training rows exactly, a model about 24 times larger (1.9 MB against 45.8 MB serialised) and a repeated fairness audit, and on the real survey it is no better (ρ 0.295 against 0.317 for the deployed forest; Q5). So we report it as an option and keep the deliberately regularised forest (200 trees, depth 6, min leaf 20).

**Q5 (owner: Kaustubh). Does the tuned behaviour model work better on real people?**

No. Both forests were scored on the 103 IGDS9-SF respondents exactly as the served model is scored, and nothing was selected on the survey. The tuned forest correlates ρ 0.295 [0.115, 0.456] with the IGDS9-SF total, the deployed one 0.317 [0.137, 0.478]; the paired difference is -0.022 [-0.073, +0.027] over 2,000 resamples of the respondents. The interval includes zero, so the survey cannot separate the two forests, and the point estimate favours the deployed one. The +0.0113 is fit to our simulator, not to people.

**Q6 (owner: Kaustubh). If C = 1 is right, why did your own search pick C = 8?**

Because the selection slice pooled every training corpus, and only 2,549 of its 35,546 texts (7%) were gaming chat, so it rewarded what suits general, non-gaming text. Repeating the selection on 2,427 gaming-chat texts from CONDA_train alone, with the CONDA validation split still untouched, the deployed C = 1 ranks 1 of 14 (validation PR-AUC 0.8062) and C = 8 ranks 11 (0.7819). Selected on gaming chat, the hand-set value is the tuned value.

**Q4 (owner: Kaustubh). What does the ablation show for each model?**

The ablations remove one part at a time, and they show that data and features matter far more than any hyperparameter. Behaviour, on simulated labels: screen-time hours alone reach 70.2%, the five pattern features alone 90.2% and the ten deployed features 91.6%, while all 120 forest settings stay within CV macro-F1 0.9057 to 0.9291. Chat: removing the gaming-chat corpus drops PR-AUC from 0.825 to 0.511 and removing character n-grams to 0.794, whereas the whole range of C moves validation PR-AUC by 0.0726 and the tuned C is worse on test. Voice, on unseen speakers: the 36 features beat the earlier 17 (0.562 against 0.499), while no hyperparameter moves CV macro-F1 by more than 0.0105. The accuracy came from what the models see, not from how they were tuned.
