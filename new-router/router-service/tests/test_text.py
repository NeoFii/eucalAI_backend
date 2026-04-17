"""Unit tests for router_service.utils.text."""

import pytest
from router_service.utils.text import (
    truncate_text,
    stringify_message_content,
    normalize_chat_or_text,
    normalize_text,
    extract_tools_from_text,
)


class TestTruncateText:
    def test_none(self):
        assert truncate_text(None) == ""

    def test_short_string(self):
        assert truncate_text("hello") == "hello"

    def test_long_string(self):
        result = truncate_text("a" * 3000, max_chars=100)
        assert len(result) == 104  # 100 + " ..."
        assert result.endswith(" ...")

    def test_dict_input(self):
        result = truncate_text({"key": "value"})
        assert "key" in result

    def test_whitespace_collapse(self):
        assert truncate_text("hello   world\n\nfoo") == "hello world foo"


class TestStringifyMessageContent:
    def test_none(self):
        assert stringify_message_content(None) == ""

    def test_string(self):
        assert stringify_message_content("hello") == "hello"

    def test_block_array(self):
        blocks = [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]
        assert stringify_message_content(blocks) == "hello world"

    def test_dict_with_content(self):
        assert stringify_message_content({"content": "hello"}) == "hello"

    def test_nested_list(self):
        result = stringify_message_content([{"text": "a"}, "b"])
        assert "a" in result


class TestNormalizeChatOrText:
    def test_list_passthrough(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert normalize_chat_or_text(msgs) == msgs

    def test_string_to_user_message(self):
        result = normalize_chat_or_text("hello")
        assert result == [{"role": "user", "content": "hello"}]

    def test_json_string(self):
        import json
        msgs = [{"role": "user", "content": "hi"}]
        result = normalize_chat_or_text(json.dumps(msgs))
        assert result == msgs

    def test_dict_single_message(self):
        msg = {"role": "user", "content": "hi"}
        assert normalize_chat_or_text(msg) == [msg]


class TestNormalizeText:
    def test_basic(self):
        assert normalize_text("  hello   world  ") == "hello world"

    def test_strip_prefix_tag(self):
        assert normalize_text("[tag] hello") == "hello"

    def test_none(self):
        assert normalize_text(None) == ""


class TestExtractToolsFromText:
    def test_toolcall_pattern(self):
        text = "toolCall(name='read_file') and toolCall(name='write_file')"
        result = extract_tools_from_text(text)
        assert "read_file" in result
        assert "write_file" in result

    def test_heuristic_match(self):
        result = extract_tools_from_text("use the browser to search")
        assert "browser" in result
        assert "search" in result

    def test_empty(self):
        assert extract_tools_from_text("") == ""
