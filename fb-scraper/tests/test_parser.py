"""Test parse HTML mẫu Facebook — parser và helpers."""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from parsers.fb_parser import extract_post_url, parse_reaction_count, parse_timestamp
from utils.helpers import clean_text, extract_post_id, url_to_page_name


class TestParseReactionCount(unittest.TestCase):
    """Test parse số reactions từ các format của Facebook."""

    def test_plain_number(self) -> None:
        self.assertEqual(parse_reaction_count("1234"), 1234)

    def test_comma_separated(self) -> None:
        self.assertEqual(parse_reaction_count("1,234"), 1234)

    def test_k_suffix(self) -> None:
        self.assertEqual(parse_reaction_count("1.2K"), 1200)

    def test_k_suffix_whole(self) -> None:
        self.assertEqual(parse_reaction_count("5K"), 5000)

    def test_m_suffix(self) -> None:
        self.assertEqual(parse_reaction_count("2M"), 2_000_000)

    def test_empty_string(self) -> None:
        self.assertEqual(parse_reaction_count(""), 0)

    def test_non_numeric(self) -> None:
        self.assertEqual(parse_reaction_count("abc"), 0)

    def test_text_with_number(self) -> None:
        # "1,234 người đã react" → 1234
        self.assertEqual(parse_reaction_count("1,234 người đã react"), 1234)

    def test_zero(self) -> None:
        self.assertEqual(parse_reaction_count("0"), 0)


class TestParseTimestamp(unittest.TestCase):
    """Test parse timestamp từ nhiều format."""

    def test_relative_minutes_vi(self) -> None:
        result = parse_timestamp("5 phút trước")
        self.assertIsInstance(result, datetime)
        diff = (datetime.now() - result).total_seconds()
        self.assertAlmostEqual(diff, 5 * 60, delta=10)

    def test_relative_hours_vi(self) -> None:
        result = parse_timestamp("2 giờ trước")
        self.assertIsInstance(result, datetime)
        diff = (datetime.now() - result).total_seconds()
        self.assertAlmostEqual(diff, 2 * 3600, delta=30)

    def test_relative_days_vi(self) -> None:
        result = parse_timestamp("3 ngày trước")
        self.assertIsInstance(result, datetime)

    def test_relative_hours_en(self) -> None:
        result = parse_timestamp("2 hours ago")
        self.assertIsInstance(result, datetime)

    def test_absolute_date_vn_format(self) -> None:
        result = parse_timestamp("15/03/2024")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.month, 3)
        self.assertEqual(result.year, 2024)

    def test_absolute_datetime_vn(self) -> None:
        result = parse_timestamp("15/03/2024 14:30")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_empty(self) -> None:
        self.assertIsNone(parse_timestamp(""))

    def test_unparseable(self) -> None:
        self.assertIsNone(parse_timestamp("xyz abc 123 ???"))

    def test_yesterday_vi(self) -> None:
        result = parse_timestamp("Hôm qua")
        self.assertIsInstance(result, datetime)

    def test_yesterday_en(self) -> None:
        result = parse_timestamp("Yesterday at 14:30")
        self.assertIsInstance(result, datetime)


class TestExtractPostUrl(unittest.TestCase):
    """Test trích xuất URL bài viết từ HTML."""

    def test_standard_posts_url(self) -> None:
        html = '<a href="https://www.facebook.com/groups/123/posts/456789">Post</a>'
        url = extract_post_url(html)
        self.assertIn("/posts/456789", url)
        self.assertTrue(url.startswith("https://"))

    def test_story_fbid_url(self) -> None:
        html = (
            '<a href="https://www.facebook.com/permalink.php'
            '?story_fbid=123456&id=789">Post</a>'
        )
        url = extract_post_url(html)
        self.assertIn("story_fbid=123456", url)

    def test_relative_posts_url(self) -> None:
        html = '<a href="/groups/123/posts/999">Post</a>'
        url = extract_post_url(html)
        self.assertTrue(url.startswith("https://www.facebook.com"))
        self.assertIn("/posts/999", url)

    def test_no_url(self) -> None:
        self.assertEqual(extract_post_url("<div>No URL here</div>"), "")

    def test_strips_tracking_params(self) -> None:
        html = (
            '<a href="https://www.facebook.com/groups/123/posts/456'
            '&__cft__[0]=az...">Post</a>'
        )
        url = extract_post_url(html)
        self.assertNotIn("__cft__", url)


class TestCleanText(unittest.TestCase):
    """Test clean_text helper."""

    def test_trims_whitespace(self) -> None:
        self.assertEqual(clean_text("  hello   world  "), "hello world")

    def test_empty_string(self) -> None:
        self.assertEqual(clean_text(""), "")

    def test_unicode_normalization(self) -> None:
        result = clean_text("Xin chào thế giới 🌏")
        self.assertIn("Xin chào", result)
        self.assertIn("🌏", result)

    def test_removes_control_chars(self) -> None:
        result = clean_text("hello\x00world\x1f")
        self.assertNotIn("\x00", result)
        self.assertNotIn("\x1f", result)

    def test_preserves_newlines(self) -> None:
        result = clean_text("line1\nline2")
        self.assertIn("\n", result)

    def test_multiple_spaces_to_one(self) -> None:
        self.assertEqual(clean_text("a    b"), "a b")


class TestUrlToPageName(unittest.TestCase):
    """Test url_to_page_name helper."""

    def test_group_url(self) -> None:
        url = "https://www.facebook.com/groups/12345"
        self.assertEqual(url_to_page_name(url), "group_12345")

    def test_page_url(self) -> None:
        url = "https://www.facebook.com/vnexpress"
        self.assertEqual(url_to_page_name(url), "vnexpress")

    def test_url_with_trailing_slash(self) -> None:
        url = "https://www.facebook.com/vnexpress/"
        self.assertEqual(url_to_page_name(url), "vnexpress")

    def test_special_chars_replaced(self) -> None:
        url = "https://www.facebook.com/my-page.name"
        name = url_to_page_name(url)
        self.assertNotIn("-", name)
        self.assertNotIn(".", name)

    def test_max_length(self) -> None:
        url = "https://www.facebook.com/" + "a" * 100
        self.assertLessEqual(len(url_to_page_name(url)), 50)


class TestExtractPostId(unittest.TestCase):
    """Test extract_post_id helper."""

    def test_posts_url(self) -> None:
        url = "https://www.facebook.com/groups/123/posts/456789"
        self.assertEqual(extract_post_id(url), "456789")

    def test_story_fbid(self) -> None:
        url = "https://www.facebook.com/permalink.php?story_fbid=9876&id=123"
        self.assertEqual(extract_post_id(url), "9876")

    def test_fbid_param(self) -> None:
        url = "https://www.facebook.com/photo?fbid=111222333"
        self.assertEqual(extract_post_id(url), "111222333")

    def test_empty_url(self) -> None:
        self.assertEqual(extract_post_id(""), "")

    def test_no_id_in_url(self) -> None:
        self.assertEqual(extract_post_id("https://www.facebook.com/"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
