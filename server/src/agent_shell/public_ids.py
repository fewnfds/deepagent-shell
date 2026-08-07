from __future__ import annotations

import re
import unicodedata


def default_public_id(prefix: str, name: str) -> str:
    """Build the stable public root id shown by authoring forms."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z]+", "-", normalized.lower()).strip("-")
    return f"{prefix}-{slug or 'config'}"

