# -*- coding: utf-8 -*-
"""Fixture: builds a CSV with the EXACT headers Google Forms exports for the form
defined in docs/SURVEY_IGDS9SF.md. Used by test_survey_parsing.py to prove the
analysis pipeline parses the real form BEFORE any responses are collected."""
import csv
import os
import random

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sim_responses.csv')

# Headers exactly as Google Forms exports them (question text verbatim from the doc).
GRID = ("These questions ask about your gaming over the past 12 months. "
        "Answer each on the scale: 1 = Never, 2 = Rarely, 3 = Sometimes, "
        "4 = Often, 5 = Very often.")
IGDS_ITEMS = [
    "I feel preoccupied with my gaming — I think about previous gaming sessions or the next one when I'm not playing.",
    "I feel more irritable, anxious or sad when I try to cut down or stop gaming.",
    "I feel the need to spend increasing amounts of time gaming to feel satisfied.",
    "I have tried to reduce or stop gaming without success.",
    "I have lost interest in previous hobbies or other activities because of gaming.",
    "I have continued gaming despite knowing it was causing problems with people around me.",
    "I have deceived family members or others about how much I game.",
    "I game to escape or relieve a negative mood (e.g., helplessness, guilt, anxiety).",
    "I have jeopardised or lost an important relationship, job, or study/career opportunity because of gaming.",
]

HEADERS = [
    "Timestamp",
    "Are you 18 years or older?",
    "Your age group",
    "Do you currently play video games?",
    "On average, how many hours per week do you play video games (phone/PC/console)?",
    "Which type of game do you play most?",
    "On a typical day you play, about how many hours do you game?",
    "How many days per week do you usually game?",
    "How long is a typical single gaming session?",
    "How often do you game after midnight?",
    "For quality control, please select 'Often' for this question.",
    "In a typical week, how many gaming sessions run longer than 3 hours?",
    "After ending a session, how often do you start another within 15 minutes?",
    "What is the longest run of consecutive days you've gamed recently?",
] + [f"{GRID} [{item}]" for item in IGDS_ITEMS]

HOURS_W = ["Less than 2", "2-5", "6-10", "11-20", "21-35", "More than 35"]
DAILY = ["Less than 1", "1-2", "2-3", "3-5", "More than 5"]
DAYS = ["0", "1", "2", "3", "4", "5", "6", "7"]
SESSION = ["Under 30 minutes", "30-60 minutes", "1-2 hours", "2-4 hours", "More than 4 hours"]
FREQ = ["Never", "Rarely", "Sometimes", "Often", "Very often"]
BINGE = ["0", "1-2", "3-5", "6 or more"]
STREAK = ["1-2 days", "3-6 days", "1-2 weeks", "More than 2 weeks"]
GAMES = ["Battle Royale (BGMI/Free Fire/PUBG)", "FPS (Valorant/COD)", "Casual (Candy Crush/Ludo)"]

random.seed(42)
rows = []
for i in range(120):
    sev = random.random()          # latent severity drives correlated answers
    idx = lambda lst: lst[min(len(lst) - 1, int(sev * len(lst) + random.random() * 1.2))]
    rows.append([
        "2026/08/05 10:%02d:00" % (i % 60),
        "Yes",
        random.choice(["18-20", "21-24", "25-29"]),
        "Yes",
        idx(HOURS_W), random.choice(GAMES),
        idx(DAILY), idx(DAYS), idx(SESSION), idx(FREQ),
        "Often",                                    # attention check PASS
        idx(BINGE), idx(FREQ), idx(STREAK),
    ] + [str(max(1, min(5, int(sev * 4 + 1 + random.gauss(0, 0.8))))) for _ in IGDS_ITEMS])

with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(HEADERS)
    w.writerows(rows)
print(f'wrote {OUT} — {len(rows)} simulated responses, {len(HEADERS)} columns')
