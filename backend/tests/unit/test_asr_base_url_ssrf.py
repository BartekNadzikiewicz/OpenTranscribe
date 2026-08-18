"""``base_url`` on an ASR provider config must not reach internal addresses.

The field's validator checked only the URL *scheme* while its docstring claimed
"SSRF protection". Any authenticated user could therefore save (or "test") a
provider pointed at ``http://opensearch:9200``, ``http://127.0.0.1:5180`` or the
cloud metadata endpoint, and read back whether the server reached it — a port
scanner for the deployment's internal network, driven from an ordinary account.

The fix reuses ``url_validation.is_safe_url``, the same check the media-source
path already applies.
"""

import pytest

from app.schemas.asr_settings import _validate_base_url_value


def test_public_provider_endpoint_is_accepted():
    assert _validate_base_url_value("https://api.elevenlabs.io") == "https://api.elevenlabs.io"


def test_empty_stays_empty():
    assert _validate_base_url_value(None) is None
    assert _validate_base_url_value("") == ""


def test_non_http_scheme_still_rejected():
    with pytest.raises(ValueError, match="http"):
        _validate_base_url_value("file:///etc/passwd")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:5180",  # loopback — OpenSearch/MinIO on the host
        "http://10.0.0.5",  # private range
        "http://192.168.1.10:9200",
        "http://169.254.169.254",  # cloud metadata
    ],
)
def test_internal_targets_are_refused(url):
    with pytest.raises(ValueError, match="not an allowed destination"):
        _validate_base_url_value(url)
