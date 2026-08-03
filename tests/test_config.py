"""Tests for environment parsing in load_config()."""

from __future__ import annotations

import pytest

from lyrebird.config import load_config


@pytest.fixture(autouse=True)
def base_env(monkeypatch):
    """Minimal valid environment with the optional maps unset."""
    monkeypatch.setenv("PUBLIC_REPO", "testorg/public-repo")
    monkeypatch.setenv("PRIVATE_REPO", "testorg/private-repo")
    monkeypatch.delenv("RESOLUTION_LABELS", raising=False)
    monkeypatch.delenv("AREA_ASSIGNEES", raising=False)


def test_area_assignees_parsed_from_env(monkeypatch):
    monkeypatch.setenv(
        "AREA_ASSIGNEES", '{"Lattices": "assaferan", "Algebras": "jvoight"}'
    )

    config = load_config()

    assert config.assignee_for_area("Lattices") == "assaferan"
    assert config.assignee_for_area("Algebras") == "jvoight"


def test_malformed_area_assignees_disables_only_that_feature(monkeypatch):
    """A broken map must not take down every other private-issue behaviour."""
    monkeypatch.setenv("AREA_ASSIGNEES", '{"Lattices": ')

    config = load_config()

    assert config.area_assignees == {}
    assert config.resolution_label_name("completed") == "resolution:completed"


def test_null_area_assignee_is_ignored(monkeypatch):
    monkeypatch.setenv("AREA_ASSIGNEES", '{"Lattices": null}')

    config = load_config()

    assert config.area_assignees == {}


def test_empty_area_assignee_is_ignored(monkeypatch):
    monkeypatch.setenv("AREA_ASSIGNEES", '{"Lattices": "", "Algebras": "jvoight"}')

    config = load_config()

    assert config.area_assignees == {"Algebras": "jvoight"}


def test_non_object_area_assignees_disables_feature(monkeypatch):
    monkeypatch.setenv("AREA_ASSIGNEES", '["Lattices"]')

    config = load_config()

    assert config.area_assignees == {}


def test_unset_area_assignees_is_empty():
    config = load_config()

    assert config.area_assignees == {}
