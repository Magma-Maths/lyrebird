"""Tests for lyrebird.mapping — pure parsing/building functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.mapping import (
    BEGIN_PUBLIC_BODY,
    END_PUBLIC_BODY,
    build_mapping_comment,
    build_mirrored_comment_body,
    build_private_issue_body,
    build_private_issue_title,
    build_tombstone_comment_body,
    find_mapping_in_comments,
    parse_mapping_comment,
    parse_private_body_markers,
    parse_public_comment_id,
    update_private_body_public_section,
)
from tests.conftest import make_public_issue_payload


def test_parse_mapping_comment_valid(config):
    text = (
        "Internal tracking: testorg/private-repo#7\n\n"
        "<!-- mapping: public_issue_node_id=I_abc123 private_issue_number=7 -->"
    )
    result = parse_mapping_comment(text)
    assert result == ("I_abc123", 7)


def test_parse_mapping_comment_missing():
    assert parse_mapping_comment("no marker here") is None


def test_parse_mapping_comment_invalid():
    assert parse_mapping_comment("<!-- mapping: garbage -->") is None


def test_build_mapping_comment(config):
    text = build_mapping_comment(config, "I_abc", 5)
    assert "testorg/private-repo#5" in text
    assert "public_issue_node_id=I_abc" in text
    assert "private_issue_number=5" in text
    # Should round-trip
    parsed = parse_mapping_comment(text)
    assert parsed == ("I_abc", 5)


def test_build_private_issue_title():
    payload = make_public_issue_payload(number=42, title="Bug report")
    assert build_private_issue_title(payload) == "[public #42] Bug report"


def test_build_private_issue_body(config):
    payload = make_public_issue_payload(
        number=42, node_id="I_kwDOTest", body="Something is broken"
    )
    body = build_private_issue_body(config, payload)
    assert "https://github.com/testorg/public-repo/issues/42" in body
    assert "@reporter" in body
    assert BEGIN_PUBLIC_BODY in body
    assert END_PUBLIC_BODY in body
    assert "Something is broken" in body
    assert "<!-- public_issue_node_id: I_kwDOTest -->" in body
    assert "<!-- public_issue_url: https://github.com/testorg/public-repo/issues/42 -->" in body


def test_parse_private_body_markers():
    body = (
        "stuff\n"
        "<!-- public_issue_url: https://github.com/org/repo/issues/5 -->\n"
        "<!-- public_issue_node_id: I_abc -->\n"
    )
    result = parse_private_body_markers(body)
    assert result == ("https://github.com/org/repo/issues/5", "I_abc")


def test_parse_private_body_markers_missing():
    assert parse_private_body_markers("no markers") is None


def test_update_private_body_public_section():
    original = (
        "Header\n"
        "<!-- BEGIN PUBLIC BODY -->\n"
        "old content\n"
        "<!-- END PUBLIC BODY -->\n"
        "Footer"
    )
    updated = update_private_body_public_section(original, "new content")
    assert "new content" in updated
    assert "old content" not in updated
    assert "Header" in updated
    assert "Footer" in updated
    assert BEGIN_PUBLIC_BODY in updated
    assert END_PUBLIC_BODY in updated


def test_update_private_body_no_delimiters():
    body = "no delimiters here"
    assert update_private_body_public_section(body, "new") == body


def test_build_mirrored_comment_body():
    body = build_mirrored_comment_body(
        author="alice",
        permalink="https://example.com/comment",
        body="hello world",
        public_comment_id=123,
    )
    assert "From @alice" in body
    assert "hello world" in body
    assert "<!-- public_comment_id: 123 -->" in body


def test_build_tombstone_comment_body():
    body = build_tombstone_comment_body(
        author="alice",
        permalink="https://example.com/comment",
        timestamp="2025-01-01T00:00:00Z",
        public_comment_id=123,
    )
    assert "deleted on public" in body
    assert "<!-- public_comment_id: 123 -->" in body


def test_parse_public_comment_id():
    body = "stuff\n<!-- public_comment_id: 456 -->"
    assert parse_public_comment_id(body) == 456


def test_parse_public_comment_id_missing():
    assert parse_public_comment_id("no marker") is None


def test_find_mapping_in_comments():
    c1 = MagicMock()
    c1.body = "just a normal comment"
    c2 = MagicMock()
    c2.body = (
        "Internal tracking: org/repo#3\n\n"
        "<!-- mapping: public_issue_node_id=I_abc private_issue_number=3 -->"
    )
    result = find_mapping_in_comments([c1, c2])
    assert result == ("I_abc", 3)


def test_find_mapping_in_comments_none():
    c1 = MagicMock()
    c1.body = "normal comment"
    assert find_mapping_in_comments([c1]) is None
    assert find_mapping_in_comments([]) is None
