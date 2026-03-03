"""Tests for lyrebird.dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lyrebird import dispatch
from lyrebird.dispatch import route


def test_route_public_issue_opened(config, mock_client):
    payload = {"issue": {"number": 1}}
    mock_handler = MagicMock()
    with patch.dict(dispatch.PUBLIC_ROUTES, {("issues", "opened"): mock_handler}):
        route(mock_client, config, "issues", "opened", payload, source="public")
    mock_handler.assert_called_once_with(mock_client, config, payload)


def test_route_public_comment_created(config, mock_client):
    payload = {"issue": {"number": 1}, "comment": {"body": "hi"}}
    mock_handler = MagicMock()
    with patch.dict(dispatch.PUBLIC_ROUTES, {("issue_comment", "created"): mock_handler}):
        route(mock_client, config, "issue_comment", "created", payload, source="public")
    mock_handler.assert_called_once_with(mock_client, config, payload)


def test_route_unknown_event(config, mock_client):
    # Should not raise, just skip
    route(mock_client, config, "pull_request", "opened", {}, source="public")


def test_route_private_issue_closed(config, mock_client):
    payload = {"issue": {"number": 1}}
    mock_handler = MagicMock()
    with patch.dict(dispatch.PRIVATE_ROUTES, {("issues", "closed"): mock_handler}):
        route(mock_client, config, "issues", "closed", payload, source="private")
    mock_handler.assert_called_once_with(mock_client, config, payload)


def test_route_private_comment_slash_public(config, mock_client):
    payload = {
        "issue": {"number": 1},
        "comment": {"body": "/public hello"},
    }
    with patch("lyrebird.dispatch.slash_public") as mod:
        route(mock_client, config, "issue_comment", "created", payload, source="private")
        mod.handle.assert_called_once_with(mock_client, config, payload)


def test_route_private_comment_slash_public_close(config, mock_client):
    payload = {
        "issue": {"number": 1},
        "comment": {"body": "/public-close completed done"},
    }
    with patch("lyrebird.dispatch.slash_public_close") as mod:
        route(mock_client, config, "issue_comment", "created", payload, source="private")
        mod.handle.assert_called_once_with(mock_client, config, payload)


def test_route_private_comment_not_slash(config, mock_client):
    payload = {
        "issue": {"number": 1},
        "comment": {"body": "just a normal comment"},
    }
    # Should not call any handler — no error
    route(mock_client, config, "issue_comment", "created", payload, source="private")
