"""Shared text preprocessing for the chat-toxicity model.

Imported by BOTH the backend (app.py) and the trainer (ml/retrain_models.py) so
training and serving apply IDENTICAL preprocessing — eliminating the train/serve
skew that existed when the model was fit on raw text but served on clean_text().
"""
import re

# Common gaming-chat slang / obfuscation → canonical form (applied before tokenising)
SLANG_MAP = {
    'fck': 'fuck', 'fuk': 'fuck', 'fuc': 'fuck', 'fcking': 'fucking', 'fkn': 'fucking',
    'sht': 'shit', 'sh1t': 'shit', 'shyt': 'shit',
    'btch': 'bitch', 'b1tch': 'bitch',
    'stfu': 'shut the fuck up', 'gtfo': 'get the fuck out',
    'kys': 'kill yourself', 'kms': 'kill myself',
    'noob': 'loser', 'n00b': 'loser', 'nub': 'loser',
    'dumb': 'stupid', 'dum': 'stupid',
    'tr4sh': 'trash', 'trsh': 'trash',
    # Romanised-Hindi (Hinglish) obfuscations/variants → canonical spelling. Real gaming
    # chat among the target users is heavily code-mixed; the TF-IDF model (English
    # corpus) can't see these, but the keyword channel (fused via noisy-OR) can.
    # Deliberately EXCLUDED as too ambiguous in *gaming* chat: 'mc' (Minecraft),
    # 'bc' (because), 'bt' — precision-first, same policy as the English list.
    'bsdk': 'bhosdike', 'bhsdk': 'bhosdike', 'bhosadike': 'bhosdike',
    'chutya': 'chutiya', 'cutiya': 'chutiya', 'chutiye': 'chutiya',
    'madarchd': 'madarchod', 'mdrchod': 'madarchod', 'maderchod': 'madarchod',
    'bhenchod': 'behenchod', 'bhnchod': 'behenchod', 'benchod': 'behenchod',
    'gaandu': 'gandu', 'gandoo': 'gandu',
    'lawde': 'laude', 'lodu': 'laude',
    'kamine': 'kamina', 'kutte': 'kutta', 'saala': 'sala', 'saale': 'sala',
}

# Words that signal genuine hostility regardless of gaming context: profanity, a slur,
# self-harm. Game-mechanic verbs (kill/die/death/murder/destroy) and neutral emotion/
# action words (rage/angry/furious/cry/scream/punch/smash/break/hate/toxic/addicted) were
# DELIBERATELY REMOVED: in gaming chat "nice kill", "I died", "rage quit", "smash that
# combo" and "I'm addicted to this game" are normal, and auto-flagging them was a major
# false-positive source. The trained chat model is the primary signal; this keyword
# booster is kept precise on purpose (see CHAT_ALERT_T in app.py).
# English + Hindi in BOTH scripts. The Hindi terms are unambiguous abuse (no
# legitimate gaming meaning), so they carry the same weights as their English
# counterparts. Devanagari forms are included because typed chat arrives verbatim
# (Gboard Hindi is common on the target users' phones) and clean_text's \w class
# keeps Devanagari letters; NOTE the on-device STT is English-vocabulary (Indian
# English model), so SPOKEN Hindi still cannot reach these — typed chat can.
TOXIC_HIGH = {'fuck', 'shit', 'bitch', 'retard', 'suicide',
              'madarchod', 'behenchod', 'bhosdike', 'bhosdi', 'chutiya',
              'randi', 'gandu', 'laude',
              'मादरचोद', 'बहनचोद', 'भेनचोद', 'भोसड़ीके', 'चूतिया', 'रंडी', 'गांडू', 'लौड़े'}
TOXIC_MEDIUM = {'stupid', 'idiot', 'loser', 'trash', 'garbage', 'suck', 'worst',
                'pathetic', 'useless',
                'kamina', 'harami', 'kutta', 'sala', 'tatti', 'nalayak',
                'कमीना', 'हरामी', 'कुत्ता', 'साला', 'टट्टी', 'नालायक'}

# Genuinely hostile/self-harm PHRASES. keyword_toxicity() runs AFTER slang expansion,
# so 'kys' -> "kill yourself", 'kms' -> "kill myself", 'stfu' -> "shut the fuck up".
# Matching the phrase (not the bare word "kill") keeps real abuse/self-harm toxic while
# letting the game-mechanic "kill"/"die" through.
TOXIC_PHRASES = ('kill yourself', 'kill myself', 'shut the fuck up', 'get the fuck out')

STOP_WORDS = {
    'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'him', 'his', 'she', 'her', 'it', 'its',
    'they', 'them', 'their', 'what', 'which', 'who', 'this', 'that', 'these', 'those',
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
    'a', 'an', 'the', 'and', 'but', 'if', 'or', 'as', 'of', 'at', 'by', 'for', 'with', 'to',
    'from', 'in', 'out', 'on', 'off', 'over', 'then', 'here', 'there', 'when', 'where',
    'all', 'both', 'some', 'no', 'not', 'only', 'so', 'than', 'too', 'very', 'can', 'will',
    'just', 'don', 'should', 'now', 's', 't', 'd', 'll', 'm', 'o', 're', 've', 'y',
}


def normalize_slang(text):
    text = str(text).lower()
    text = re.sub(r'(.)\1{2,}', r'\1', text)   # nooo → no
    return ' '.join(SLANG_MAP.get(w, w) for w in text.split())


def clean_text(text):
    text = normalize_slang(str(text))
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\d+', '', text)
    return ' '.join(w for w in text.split() if w not in STOP_WORDS)


def keyword_toxicity(text):
    norm   = normalize_slang(text)            # 'kys' -> 'kill yourself'
    words  = set(norm.split())
    high   = len(words & TOXIC_HIGH)
    medium = len(words & TOXIC_MEDIUM)
    phrase = sum(1 for p in TOXIC_PHRASES if p in norm)
    return min(high * 0.2 + medium * 0.1 + phrase * 0.3, 0.9)
