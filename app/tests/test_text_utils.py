"""Tests for text_utils module (Chinese text segmentation)."""

import pytest

from bili_assetizer.core.text_utils import segment_text, segment_query


class TestSegmentText:
    """Tests for segment_text function."""

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert segment_text("") == ""

    def test_whitespace_only(self) -> None:
        """Whitespace-only string returns empty string."""
        assert segment_text("   ") == ""
        assert segment_text("\t\n") == ""

    def test_none_input(self) -> None:
        """None input returns empty string."""
        assert segment_text(None) == ""  # type: ignore

    def test_chinese_text_segmented(self) -> None:
        """Chinese text is segmented into tokens."""
        result = segment_text("中国科学院")
        # jieba.cut_for_search produces fine-grained tokens
        # Exact output depends on jieba's dictionary, but should contain multiple tokens
        tokens = result.split()
        assert len(tokens) > 1
        # Should contain the original characters
        assert "中国" in result or "科学" in result

    def test_chinese_sentence(self) -> None:
        """Chinese sentence is properly segmented."""
        result = segment_text("处理器性能很好")
        tokens = result.split()
        # Should produce multiple tokens from this phrase
        assert len(tokens) >= 2

    def test_english_text_preserved(self) -> None:
        """English text passes through with word boundaries."""
        result = segment_text("hello world")
        # English words should be preserved
        assert "hello" in result
        assert "world" in result

    def test_mixed_chinese_english(self) -> None:
        """Mixed Chinese and English text handled correctly."""
        result = segment_text("Intel处理器CPU")
        # Should contain both English and Chinese tokens
        assert "Intel" in result or "intel" in result.lower()
        assert "CPU" in result or "cpu" in result.lower()
        # Chinese should be segmented
        tokens = result.split()
        assert len(tokens) >= 2

    def test_numbers_preserved(self) -> None:
        """Numbers are preserved in output."""
        result = segment_text("第12代处理器")
        assert "12" in result

    def test_punctuation_handling(self) -> None:
        """Punctuation is handled gracefully."""
        result = segment_text("你好，世界！")
        # Should still produce tokens
        assert len(result) > 0


class TestSegmentQuery:
    """Tests for segment_query function."""

    def test_empty_query(self) -> None:
        """Empty query returns empty string."""
        assert segment_query("") == ""

    def test_chinese_query_segmented(self) -> None:
        """Chinese query is segmented for matching."""
        result = segment_query("处理器")
        # Should produce segmented output
        assert len(result) > 0

    def test_same_as_segment_text(self) -> None:
        """segment_query produces same output as segment_text."""
        test_strings = [
            "中国科学院",
            "hello world",
            "Intel处理器",
            "性能测试",
        ]
        for s in test_strings:
            assert segment_query(s) == segment_text(s)


class TestSearchIntegration:
    """Integration tests verifying query matches indexed text."""

    def test_chinese_query_matches_indexed(self) -> None:
        """Chinese query tokens should appear in segmented text."""
        text = "这是一个关于处理器性能的视频"
        query = "处理器"

        segmented_text = segment_text(text)
        segmented_query = segment_query(query)

        # Query tokens should appear in the segmented text
        query_tokens = set(segmented_query.split())
        text_tokens = set(segmented_text.split())

        # At least one query token should match
        assert len(query_tokens & text_tokens) > 0

    def test_partial_word_match(self) -> None:
        """Partial word queries should match through segmentation."""
        text = "中国科学院计算技术研究所"
        query = "科学"

        segmented_text = segment_text(text)
        segmented_query = segment_query(query)

        # "科学" should appear as a token in both
        assert "科学" in segmented_text.split() or any(
            "科学" in t for t in segmented_text.split()
        )
