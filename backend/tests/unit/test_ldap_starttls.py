"""StartTLS must actually reach the connection.

``use_tls`` was wired end to end — ``.env``, the DB-backed auth config and the
admin UI all set it — but the bind used
``AUTO_BIND_TLS_BEFORE_BIND if cfg.use_ssl else True``. StartTLS was therefore
requested only on connections that were *already* LDAPS, and never on plain 389
where it is the only thing that encrypts the bind. The admin UI defaults point
straight at that combination (SSL off, StartTLS on), so a deployment that
followed it sent every user's password in cleartext.
"""

from ldap3 import AUTO_BIND_TLS_BEFORE_BIND

from app.auth.ldap_auth import LdapConfig
from app.auth.ldap_auth import _auto_bind_mode


def _cfg(**kwargs) -> LdapConfig:
    base = {"server": "ldap.example.org", "port": 389, "use_ssl": False, "use_tls": False}
    base.update(kwargs)
    return LdapConfig(**base)


def test_starttls_on_plain_port_negotiates_tls_before_bind():
    """The regression: 389 + StartTLS must encrypt before credentials are sent."""
    assert _auto_bind_mode(_cfg(use_tls=True)) == AUTO_BIND_TLS_BEFORE_BIND


def test_ldaps_never_requests_starttls():
    """LDAPS is already TLS end-to-end; StartTLS over it is a protocol error
    (AD refuses the bind: 'automatic start tls before bind not successful').
    The original test here pinned the buggy behavior as 'unchanged' — caught
    on the first real LDAPS login against Active Directory (2026-08-18)."""
    assert _auto_bind_mode(_cfg(port=636, use_ssl=True)) is True


def test_ldaps_wins_over_a_stray_starttls_flag():
    """Both flags set (misconfigured UI): the LDAPS transport decides."""
    assert _auto_bind_mode(_cfg(port=636, use_ssl=True, use_tls=True)) is True


def test_plain_ldap_without_either_flag_stays_plain():
    """No silent upgrade: an operator who asked for neither still gets neither."""
    assert _auto_bind_mode(_cfg()) is True


def test_bad_filter_placeholder_logs_clearly_instead_of_keyerror():
    """(sAMAccountName={sAMAccountName}) — the attribute name typed into the
    braces — must not blow up as an opaque KeyError (seen in the field
    2026-08-18); the search returns None and the log names the fix."""
    from unittest.mock import MagicMock

    from app.auth.ldap_auth import _search_ldap_user

    cfg = _cfg(user_search_filter="(sAMAccountName={sAMAccountName})", search_base="dc=x")
    conn = MagicMock()
    assert _search_ldap_user(cfg, conn, "jan", "jan") is None
    conn.search.assert_not_called()
