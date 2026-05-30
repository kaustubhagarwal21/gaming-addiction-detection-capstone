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
}

TOXIC_HIGH = {'kill', 'die', 'death', 'murder', 'destroy', 'hate', 'fuck', 'shit', 'bitch', 'retard',
              'suicide', 'kys', 'toxic', 'rage', 'addicted'}
TOXIC_MEDIUM = {'stupid', 'idiot', 'loser', 'trash', 'garbage', 'suck', 'worst', 'angry', 'furious',
                'pathetic', 'useless', 'dumb', 'noob', 'cry', 'scream', 'punch', 'smash', 'break'}

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
    words = set(normalize_slang(text).split())
    high   = len(words & TOXIC_HIGH)
    medium = len(words & TOXIC_MEDIUM)
    return min(high * 0.2 + medium * 0.1, 0.9)
