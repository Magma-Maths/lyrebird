"""Shared fixtures and mock GitHub client for tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

from lyrebird.config import Config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def config():
    """Standard test config."""
    return Config(
        public_repo="testorg/public-repo",
        private_repo="testorg/private-repo",
        bot_login="lyrebird[bot]",
        resolution_labels={
            "completed": ("resolution:completed", "This has been fixed and will be available in the next update. Thanks for the report.", "completed"),
            "not-planned": ("resolution:not-planned", "Closing as not planned.", "not_planned"),
            "cannot-reproduce": (
                "resolution:cannot-reproduce",
                "We could not reproduce this.",
                "not_planned",
            ),
            "custom": ("resolution:custom", "", None),
        },
        area_assignees={
            "Lattices": "assaferan",
            "Algebras": "jvoight",
        },
    )


@pytest.fixture
def mock_client():
    """Mock PyGithub client with convenient helpers."""
    client = MagicMock()
    return client


def make_mock_issue(
    number: int = 1,
    node_id: str = "I_abc123",
    title: str = "Test issue",
    body: str = "Issue body",
    state: str = "open",
    labels: list[str] | None = None,
    html_url: str | None = None,
    user_login: str = "reporter",
    milestone=None,
):
    """Create a mock PyGithub Issue object."""
    issue = MagicMock()
    issue.number = number
    issue.node_id = node_id
    issue.title = title
    issue.body = body
    issue.state = state
    issue.assignees = []
    issue.html_url = html_url or f"https://github.com/testorg/repo/issues/{number}"

    label_mocks = []
    for name in (labels or []):
        lbl = MagicMock()
        lbl.name = name
        label_mocks.append(lbl)
    issue.get_labels.return_value = label_mocks

    issue.user = MagicMock()
    issue.user.login = user_login
    issue.milestone = milestone

    # Repository mock
    repo = MagicMock()
    type(issue).repository = PropertyMock(return_value=repo)

    return issue


def make_mock_comment(
    comment_id: int = 100,
    body: str = "comment body",
    html_url: str = "https://github.com/testorg/repo/issues/1#issuecomment-100",
    user_login: str = "commenter",
):
    """Create a mock PyGithub IssueComment object."""
    comment = MagicMock()
    comment.id = comment_id
    comment.body = body
    comment.html_url = html_url
    comment.user = MagicMock()
    comment.user.login = user_login
    return comment


def make_mock_milestone(
    number: int = 1,
    title: str = "v1.0",
    description: str = "First release",
    due_on: str | None = "2026-06-01T00:00:00Z",
    state: str = "open",
):
    """Create a mock PyGithub Milestone object."""
    from datetime import datetime, timezone

    milestone = MagicMock()
    milestone.number = number
    milestone.title = title
    milestone.description = description
    milestone.state = state
    if due_on:
        milestone.due_on = datetime.fromisoformat(due_on.replace("Z", "+00:00"))
    else:
        milestone.due_on = None
    milestone.updated_at = datetime.now(timezone.utc)
    return milestone


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    path = FIXTURES_DIR / name
    with open(path) as f:
        return json.load(f)


def make_public_issue_payload(
    number: int = 42,
    node_id: str = "I_kwDOTest",
    title: str = "Bug report",
    body: str = "Something is broken",
    state: str = "open",
    user_login: str = "reporter",
    labels: list[dict] | None = None,
    milestone: dict | None = None,
) -> dict:
    """Build a minimal public issue payload dict."""
    return {
        "number": number,
        "node_id": node_id,
        "title": title,
        "body": body,
        "state": state,
        "html_url": f"https://github.com/testorg/public-repo/issues/{number}",
        "user": {"login": user_login},
        "created_at": "2025-01-01T00:00:00Z",
        "labels": labels or [],
        "milestone": milestone,
    }


def make_comment_payload(
    comment_id: int = 999,
    body: str = "A comment",
    user_login: str = "commenter",
    issue_number: int = 42,
    issue_node_id: str = "I_kwDOTest",
) -> dict:
    """Build a minimal comment event payload."""
    return {
        "issue": make_public_issue_payload(number=issue_number, node_id=issue_node_id),
        "comment": {
            "id": comment_id,
            "body": body,
            "html_url": f"https://github.com/testorg/public-repo/issues/{issue_number}#issuecomment-{comment_id}",
            "user": {"login": user_login},
        },
        "sender": {"login": user_login, "type": "User"},
    }


def setup_missing_mapping(config, mock_client, private_issue_number: int = 99):
    """Wire mock_client so resolve_mapping() returns None and create_issue
    returns a mock private issue with the given number.

    Returns (mock_pub_repo, mock_priv_repo, mock_pub_issue, mock_priv_issue).
    """
    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = make_mock_issue(number=42)
    mock_pub_issue.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []
    mock_priv_repo.get_milestones.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = private_issue_number
    mock_priv_issue.state = "open"
    mock_priv_issue.assignees = []
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    mock_client.get_repo.side_effect = lambda name: (
        mock_pub_repo if name == config.public_repo else mock_priv_repo
    )
    mock_pub_repo.get_issue.return_value = mock_pub_issue
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    return mock_pub_repo, mock_priv_repo, mock_pub_issue, mock_priv_issue


def make_private_issue_body(
    public_number: int = 42,
    public_node_id: str = "I_kwDOTest",
    public_body: str = "Something is broken",
) -> str:
    """Build a standard private issue body with markers."""
    return (
        f"**Public issue**: https://github.com/testorg/public-repo/issues/{public_number}\n"
        f"**Author**: @reporter\n"
        f"\n"
        f"<!-- BEGIN PUBLIC BODY -->\n"
        f"{public_body}\n"
        f"<!-- END PUBLIC BODY -->\n"
        f"\n"
        f"<!-- public_issue_url: https://github.com/testorg/public-repo/issues/{public_number} -->\n"
        f"<!-- public_issue_node_id: {public_node_id} -->"
    )
