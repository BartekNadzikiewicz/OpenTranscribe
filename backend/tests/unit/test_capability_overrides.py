"""Tests for CAPABILITY_OVERRIDES env-driven self-hosted capability gating."""

from app.core.capabilities import COMMUNITY_CAPABILITIES, get_capabilities


def test_override_disables_known_key(monkeypatch):
    monkeypatch.setenv("CAPABILITY_OVERRIDES", "chat.rag=false")
    caps = get_capabilities(None)
    assert caps["chat.rag"] is False


def test_unknown_key_is_ignored(monkeypatch):
    monkeypatch.setenv("CAPABILITY_OVERRIDES", "definitely.not.a.key=false")
    assert get_capabilities(None) == dict(COMMUNITY_CAPABILITIES)


def test_malformed_entry_is_ignored(monkeypatch):
    monkeypatch.setenv("CAPABILITY_OVERRIDES", "chat.rag")
    assert get_capabilities(None)["chat.rag"] is True


def test_no_override_keeps_defaults(monkeypatch):
    monkeypatch.delenv("CAPABILITY_OVERRIDES", raising=False)
    assert get_capabilities(None) == dict(COMMUNITY_CAPABILITIES)
