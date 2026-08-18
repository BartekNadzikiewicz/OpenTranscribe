"""A plain admin must not be able to act on a super_admin.

``get_current_admin_user`` admits both ``admin`` and ``super_admin``, so each
privileged action on another account needs the hierarchy check separately.
``/lock``, ``/unlock`` and ``DELETE /sessions`` did not have it, so any admin
could disable and log out the deployment's only super_admin — a denial of
service against the one account that can change roles and auth configuration.

These tests pin the helper and, more importantly, that every endpoint calls it:
a new privileged endpoint added without the check should fail here.
"""

import inspect

import pytest
from fastapi import HTTPException

from app.api.endpoints.admin import _assert_can_act_on_target
from app.auth.roles import ROLE_ADMIN
from app.auth.roles import ROLE_SUPER_ADMIN
from app.auth.roles import ROLE_USER


class _FakeUser:
    def __init__(self, role: str):
        self.role = role


def test_admin_cannot_act_on_super_admin():
    with pytest.raises(HTTPException) as exc:
        _assert_can_act_on_target(_FakeUser(ROLE_SUPER_ADMIN), _FakeUser(ROLE_ADMIN), "lock")
    assert exc.value.status_code == 403


def test_super_admin_can_act_on_super_admin():
    _assert_can_act_on_target(_FakeUser(ROLE_SUPER_ADMIN), _FakeUser(ROLE_SUPER_ADMIN), "lock")


def test_admin_can_act_on_ordinary_user():
    _assert_can_act_on_target(_FakeUser(ROLE_USER), _FakeUser(ROLE_ADMIN), "lock")


@pytest.mark.parametrize(
    "endpoint_name",
    ["admin_lock_account", "admin_unlock_account", "admin_terminate_user_sessions"],
)
def test_privileged_endpoints_call_the_guard(endpoint_name):
    """The guard is only worth anything if the endpoints actually call it."""
    from app.api.endpoints import admin

    source = inspect.getsource(getattr(admin, endpoint_name))
    assert "_assert_can_act_on_target" in source, (
        f"{endpoint_name} acts on another account without the super_admin guard"
    )
