"""
Single source of truth for deriving the 10 psychometric behavioural features from the
10 objective ones.

Imported by BOTH the model trainer (ml/retrain_models.py) and the live backend
(app.compute_behavioral_features) so the model is trained and served on the *identical*
feature derivation — eliminating the train/serve skew that existed when serving folded
in extra signals (notifications/screen/school-hour) that the training derivation never
modelled. Training adds small Gaussian noise on top for regularisation; serving uses
the deterministic values (which sit inside that noise distribution).

These are clinically-motivated proxies, not measured survey scores — see PRIVACY.md.
"""


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def derive_psychometrics(
    daily_play_time_hours: float,
    weekly_play_time_hours: float,
    sessions_per_day: float,
    avg_session_duration_min: float,
    late_night_play_ratio: float,
    days_played_per_week: float,
    longest_play_streak_days: float,
    binge_sessions_per_week: float,
    avg_break_between_sessions_min: float,
    rapid_relogin_ratio: float,
) -> dict:
    """Return the 10 psychometric scores (0–10, except missed_sleep 0–7) derived purely
    from the 10 objective features. Deterministic — the canonical mapping the model learns."""
    daily   = daily_play_time_hours
    spd     = sessions_per_day
    dur     = avg_session_duration_min
    lnr     = late_night_play_ratio
    dpw     = days_played_per_week
    binge   = binge_sessions_per_week
    rlr     = rapid_relogin_ratio
    return {
        'urge_to_continue_score':         round(_clip(rlr * 3 + spd * 1.0,            0, 10), 4),
        'loss_of_time_awareness_score':   round(_clip(dur / 18.0,                     0, 10), 4),
        'control_loss_score':             round(_clip(binge * 1.5 + dpw * 0.7,        0, 10), 4),
        'craving_score':                  round(_clip(rlr * 3 + lnr * 3,              0, 10), 4),
        'tolerance_score':                round(_clip(dur / 25.0 + binge * 0.4,       0, 10), 4),
        'missed_sleep_days_per_week':     round(_clip(lnr * 7,                        0, 7),  4),
        'fatigue_after_play_score':       round(_clip((dur / 60.0) * 1.5 + lnr * 3,   0, 10), 4),
        'routine_disruption_score':       round(_clip(binge * 0.8 + daily / 4.0,      0, 10), 4),
        'neglect_responsibilities_score': round(_clip(daily * 0.5 + binge * 0.5,      0, 10), 4),
        'gaming_priority_score':          round(_clip(daily / 16.0 * 10.0,            0, 10), 4),
    }
