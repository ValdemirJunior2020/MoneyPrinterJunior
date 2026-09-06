import re

SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def sanitize_search_query(value: str, max_words: int = 18) -> str:
    text = value.translate(SMART_QUOTES)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"[\n\r\t]+", " ", text)
    text = re.sub(r"[^\w\s\-,'\".:()]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip(" .,:;-\"")
    words = text.split()
    if len(words) > max_words:
        words = words[:max_words]
    return " ".join(words)
