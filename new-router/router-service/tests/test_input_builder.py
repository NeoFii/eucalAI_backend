"""Unit tests for router_service.utils.input_builder (v3 enhanced)."""

import pytest
from router_service.utils.input_builder import (
    shared_record_from_chat_messages,
    build_full_llm_input_for_chat_messages,
    build_proto_semantic_text,
    build_tool_canonical_text_from_text,
)


class TestSharedRecordFromChatMessages:
    def test_basic_messages(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello world"},
        ]
        record = shared_record_from_chat_messages(messages)
        assert record["task"] == "Hello world"
        assert record["source"] == "chat_messages"
        assert "helpful" in record["instruction"]

    def test_tool_calls_in_assistant(self):
        """v3: assistant messages with tool_calls should be recognized."""
        messages = [
            {"role": "user", "content": "Search for files"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "function": {"name": "read_file", "arguments": "{}"}},
                    {"type": "function", "function": {"name": "search", "arguments": "{}"}},
                ],
            },
        ]
        record = shared_record_from_chat_messages(messages)
        assert "read_file" in record["action_space"]
        assert "search" in record["action_space"]

    def test_tool_role_messages(self):
        """v3: tool role messages should be processed."""
        messages = [
            {"role": "user", "content": "Read the config"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "function": {"name": "read_file", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "tc1", "content": "file contents here"},
        ]
        record = shared_record_from_chat_messages(messages)
        assert record["has_lastStep"] is True

    def test_empty_messages(self):
        record = shared_record_from_chat_messages([])
        assert record["task"] == "N/A"

    def test_block_array_content(self):
        """Content as block array [{"type": "text", "text": "..."}]."""
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "hello from blocks"}]},
        ]
        record = shared_record_from_chat_messages(messages)
        assert "hello from blocks" in record["task"]


class TestBuildFullLlmInput:
    def test_basic(self):
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hi"},
        ]
        chat, debug = build_full_llm_input_for_chat_messages(messages)
        assert len(chat) == 2
        assert chat[0]["role"] == "system"
        assert chat[1]["role"] == "user"

    def test_tool_calls_placeholder(self):
        """v3: assistant with tool_calls but no content gets placeholder."""
        messages = [
            {"role": "user", "content": "Do something"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "function": {"name": "exec_cmd", "arguments": "{}"}},
                ],
            },
        ]
        chat, debug = build_full_llm_input_for_chat_messages(messages)
        assert any("[Calling tools:" in m["content"] for m in chat)
        assert any("exec_cmd" in m["content"] for m in chat)

    def test_tool_role_mapped(self):
        """v3: tool role messages mapped to assistant with [Tool result] prefix."""
        messages = [
            {"role": "user", "content": "Read file"},
            {"role": "tool", "tool_call_id": "tc1", "content": "file data here"},
        ]
        chat, debug = build_full_llm_input_for_chat_messages(messages)
        tool_msg = [m for m in chat if "[Tool result]" in m["content"]]
        assert len(tool_msg) == 1
        assert tool_msg[0]["role"] == "assistant"

    def test_empty_fallback(self):
        chat, debug = build_full_llm_input_for_chat_messages([])
        assert chat == [{"role": "user", "content": "N/A"}]

    def test_unknown_role_mapped_to_user(self):
        messages = [{"role": "function", "content": "result"}]
        chat, _ = build_full_llm_input_for_chat_messages(messages)
        assert chat[0]["role"] == "user"


class TestProtoSemanticText:
    def test_from_chat_messages(self):
        messages = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "follow up"},
        ]
        result = build_proto_semantic_text(messages)
        assert result == "follow up"

    def test_from_string(self):
        assert build_proto_semantic_text("hello world") == "hello world"

    def test_from_empty_list(self):
        result = build_proto_semantic_text([])
        assert result == "[]"


class TestCanonicalText:
    def test_basic(self):
        result = build_tool_canonical_text_from_text("hello")
        assert result == "User: hello"

    def test_empty(self):
        result = build_tool_canonical_text_from_text("")
        assert result == "User: N/A"
