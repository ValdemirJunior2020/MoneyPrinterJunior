import re
from dataclasses import dataclass

BANNED_DEFAULT = {
    "sports", "football", "basketball", "casino", "gambling", "porn", "pornography",
    "celebrity", "trailer", "gaming", "gameplay", "election", "campaign rally",
}


def tokens(value: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", value.lower()) if len(t) > 2}


def relevance_score(query: str, title: str, description: str, source: str, subject: str = "") -> float:
    q = tokens(query)
    hay = tokens(" ".join([title, description, subject]))
    if not q:
        return 0.0
    overlap = len(q & hay) / len(q)
    source_bonus = {"wikimedia": 0.12, "internet_archive": 0.08, "pexels": 0.05}.get(source, 0)
    combined = " ".join([title, description, subject]).lower()
    penalty = 0.65 if any(term in combined and term not in query.lower() for term in BANNED_DEFAULT) else 0.0
    return max(0.0, min(1.0, overlap + source_bonus - penalty))
