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


def test_ldaps_path_is_unchanged():
    assert _auto_bind_mode(_cfg(port=636, use_ssl=True)) == AUTO_BIND_TLS_BEFORE_BIND


def test_plain_ldap_without_either_flag_stays_plain():
    """No silent upgrade: an operator who asked for neither still gets neither."""
    assert _auto_bind_mode(_cfg()) is True
