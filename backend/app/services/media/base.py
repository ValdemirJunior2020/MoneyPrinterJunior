from dataclasses import dataclass, asdict


@dataclass
class MediaCandidate:
    provider: str
    title: str
    url: str
    original_url: str
    author: str = ""
    license: str = ""
    description: str = ""
    subject: str = ""
    media_type: str = "image"
    score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
