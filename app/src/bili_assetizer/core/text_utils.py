"""Text utilities for Chinese text segmentation using jieba."""

import jieba


def segment_text(text: str) -> str:
    """Segment text for FTS5 indexing using jieba.cut_for_search().

    This function tokenizes Chinese text into searchable segments.
    For example, "中国科学院" becomes "中国 科学 科学院 学院".

    English text and punctuation pass through naturally, with jieba
    preserving word boundaries.

    Args:
        text: The text to segment.

    Returns:
        Space-separated tokens suitable for FTS5 indexing.
        Returns empty string for empty/whitespace-only input.
    """
    if not text or not text.strip():
        return ""

    # cut_for_search produces finer-grained tokens for better search recall
    tokens = jieba.cut_for_search(text)
    return " ".join(tokens)


def segment_query(query: str) -> str:
    """Segment a query string for FTS5 searching.

    Uses the same segmentation as segment_text() to ensure query tokens
    match the indexed tokens.

    Args:
        query: The search query string.

    Returns:
        Space-separated tokens for FTS5 MATCH.
        Returns empty string for empty/whitespace-only input.
    """
    return segment_text(query)
