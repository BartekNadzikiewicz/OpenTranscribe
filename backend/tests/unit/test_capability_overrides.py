"""Tests for CAPABILITY_OVERRIDES env-driven self-hosted capability gating."""

import pytest

from app.core.capabilities import (
    COMMUNITY_CAPABILITIES,
    DEPLOYMENT_DISABLED_CAPABILITIES,
    get_capabilities,
)


def test_override_disables_known_key(monkeypatch):
    monkeypatch.setenv("CAPABILITY_OVERRIDES", "chat.rag=false")
    caps = get_capabilities(None)
    assert caps["chat.rag"] is False


def _baseline() -> dict:
    """Community defaults with this deployment's disabled surfaces applied."""
    caps = dict(COMMUNITY_CAPABILITIES)
    caps.update(DEPLOYMENT_DISABLED_CAPABILITIES)
    return caps


def test_unknown_key_is_ignored(monkeypatch):
    monkeypatch.setenv("CAPABILITY_OVERRIDES", "definitely.not.a.key=false")
    assert get_capabilities(None) == _baseline()


@pytest.mark.parametrize("key", sorted(DEPLOYMENT_DISABLED_CAPABILITIES))
def test_disabled_surfaces_are_off_without_any_env(monkeypatch, key):
    """The regression that motivated this: a `.env` missing the line left the
    feature ON in production. The image itself must carry the decision."""
    monkeypatch.delenv("CAPABILITY_OVERRIDES", raising=False)
    assert get_capabilities(None)[key] is False


def test_env_can_still_re_enable_deliberately(monkeypatch):
    monkeypatch.setenv("CAPABILITY_OVERRIDES", "url_ingest=true")
    assert get_capabilities(None)["url_ingest"] is True


def test_malformed_entry_is_ignored(monkeypatch):
    """A key with no `=value` changes nothing — the baseline stands."""
    monkeypatch.setenv("CAPABILITY_OVERRIDES", "search")
    assert get_capabilities(None) == _baseline()
    assert get_capabilities(None)["search"] is True


def test_no_override_keeps_defaults(monkeypatch):
    monkeypatch.delenv("CAPABILITY_OVERRIDES", raising=False)
    assert get_capabilities(None) == _baseline()


def test_redaction_user_router_is_gated():
    """`redaction.user` must gate the API, not only the settings panel.

    The detector list is user-settable through this router, and choosing the
    "llm" detector ships raw transcript text to an external provider — hiding
    the panel while the endpoint stayed reachable was presentation, not
    authorization.
    """
    import inspect

    from app.api import router as api_router_module

    source = inspect.getsource(api_router_module)
    marker = "redaction_settings.user_router"
    start = source.index(marker)
    registration = source[start : start + 400]
    assert 'capability="redaction.user"' in registration


def test_process_url_route_gated_on_url_ingest():
    """/files/process-url must declare the url_ingest capability gate.

    The key existed in the registry but nothing enforced it — a deployment
    setting ``url_ingest=false`` still accepted URL ingestion requests.
    """
    import inspect

    from app.api.endpoints.files.url_processing import router as url_router

    route = next(r for r in url_router.routes if r.path == "/process-url")
    gated_keys = []
    for dep in route.dependencies:
        try:
            gated_keys.append(inspect.getclosurevars(dep.dependency).nonlocals.get("key"))
        except TypeError:
            continue
    assert "url_ingest" in gated_keys
