"""Our category list (from PLAN.md) and the mapping from source labels to it."""

import re

CATEGORIES = {
    "music": "Music",
    "nightlife": "Nightlife",
    "theatre": "Theatre",
    "film": "Film",
    "exhibitions": "Exhibitions",
    "meetups": "Meetups",
    "grzybki": "Grzybki",
    "study_buddies": "Study buddies",
    "running": "Running",
    "yoga": "Yoga",
    "sports": "Sports",
    "festivals": "Festivals",
    "markets": "Markets",
    "culture": "Culture",
    "education": "Education",
    "family": "Family & kids",
    "business": "Business",
    "health": "Health",
    "other": "Other",
    "toilets": "Public toilets",
    "aed": "Defibrillators (AED)",
}

# Practical map layers, not social categories: kept apart from the keyword guessing below,
# and hidden from /places unless asked for by category.
AMENITIES = {"toilets", "aed"}

# Source label (lowercased) -> our slug. Labels seen in dane.um.warszawa.pl data.
LABEL_MAP = {
    "kultura": "culture",
    "historia": "culture",
    "sport": "sports",
    "czas wolny": "meetups",
    "edukacja": "education",
    "dla dzieci": "family",
    "biznes": "business",
    "zdrowie": "health",
    "społeczeństwo": "meetups",
    "bieganie": "running",
    "joga": "yoga",
    "taniec": "music",
    "fitness": "sports",
    "gimnastyka": "sports",
    "aktywności w wodzie": "sports",
    "gry zespołowe": "sports",
    "sporty walki": "sports",
    "sporty rakietowe": "sports",
    "nordic walking": "sports",
    "aktywności parkowe i miejskie": "sports",
    "sauna": "health",
    "boisko": "sports",
    "toaleta": "toilets",
    "defibrylator": "aed",
}

# Title keywords refine broad labels like "Kultura".
KEYWORDS = [
    (re.compile(r"koncert|muzyk|jazz|recital|orkiestr", re.I), "music"),
    (re.compile(r"spektakl|teatr|premier", re.I), "theatre"),
    (re.compile(r"\bfilm|kino|seans", re.I), "film"),
    (re.compile(r"wystaw|galeri|muzeum|ekspozycj", re.I), "exhibitions"),
    (re.compile(r"festiwal|festyn|piknik", re.I), "festivals"),
    (re.compile(r"jarmark|targ|kiermasz|bazar", re.I), "markets"),
    (re.compile(r"\bjog[aiy]|yoga", re.I), "yoga"),
    (re.compile(r"\bbieg|run\b|maraton", re.I), "running"),
    (re.compile(r"grzyb", re.I), "grzybki"),
    (re.compile(r"\bparty|impreza|\bdj\b|clubbing|nocne", re.I), "nightlife"),
]


def map_categories(labels: list[str], title: str = "") -> list[str]:
    out: list[str] = []
    for label in labels:
        slug = LABEL_MAP.get(label.strip().lower())
        if slug and slug not in out:
            out.append(slug)
    if AMENITIES & set(out):
        return out  # "Toaleta – Muzeum ..." is a toilet, not an exhibition
    for pattern, slug in KEYWORDS:
        if pattern.search(title) and slug not in out:
            out.append(slug)
    return out or ["other"]
