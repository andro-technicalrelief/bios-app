"""General utility helpers."""
import re
from typing import List


def slugify(text: str) -> str:
    """Create a simple slug from text."""
    if text is None:
        return ""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def safe_split(text: str, sep: str) -> List[str]:
    if text is None:
        return []
    return [t.strip() for t in str(text).split(sep) if t.strip()]


def titlecase(text: str) -> str:
    if text is None:
        return ""
    return text.strip().title()
