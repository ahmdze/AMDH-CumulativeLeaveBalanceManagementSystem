"""اختبارات الأمان: كلمات المرور، الأدوار، والصلاحيات."""

from __future__ import annotations

from amdh_leave.models import AppUser
from amdh_leave.services import security as S


def test_hash_and_verify_password():
    digest, salt, iterations = S.hash_password("سرّي123")
    assert len(digest) == 64 and len(salt) == 32
    assert iterations == S.ITERATIONS
    assert S.verify_password("سرّي123", digest, salt, iterations) is True
    assert S.verify_password("خطأ", digest, salt, iterations) is False


def test_same_password_different_salt():
    first = S.hash_password("same")
    second = S.hash_password("same")
    assert first[0] != second[0]
    assert first[1] != second[1]


def test_verify_with_missing_data():
    assert S.verify_password("x", "", "") is False
    assert S.verify_password("x", "abc", "zz") is False


def test_password_strength():
    assert S.password_strength("123")[0] is False
    assert S.password_strength("1234")[0] is False      # أرقام فقط
    assert S.password_strength("abcd")[0] is True
    assert S.password_strength("Admin2026")[0] is True


def test_permission_matrix():
    admin = S.make_session(None, False)
    assert admin.is_admin and admin.can("purge") and admin.can("manage_users")
    assert admin.can("delete_employee") and admin.can("edit_policy")
    assert admin.can("view_holidays") and admin.can("manage_holidays")

    editor = S.make_session(AppUser(username="e", role="editor"), True)
    assert editor.can("edit_leave") and editor.can("edit_employee") and editor.can("export")
    assert editor.can("view_holidays") and editor.can("manage_holidays")
    assert editor.can("delete_employee") and editor.can("delete_leave") and editor.can("purge")
    assert editor.can("edit_policy") and editor.can("backup_restore")
    assert editor.can("manage_encryption") and editor.can("db_operations")
    assert not editor.can("manage_users") and not editor.can("manage_institutions")
    assert not editor.can("view_audit") and not editor.can("edit_rules")
    assert editor.read_only is False

    viewer = S.make_session(AppUser(username="v", role="viewer"), True)
    assert viewer.can("export") and viewer.can("view_holidays")
    assert not viewer.can("edit_leave") and not viewer.can("edit_employee")
    assert viewer.read_only is True


def test_unknown_role_falls_back_to_viewer():
    session = S.make_session(AppUser(username="x", role="superuser"), True)
    assert session.role == "viewer"
    assert not session.can("edit_leave")


def test_institution_scoping():
    admin = S.make_session(AppUser(username="a", role="admin", institution="صحة ب"), True)
    assert admin.scoped_institution == ""      # المدير يرى كل المؤسسات
    editor = S.make_session(AppUser(username="e", role="editor", institution="صحة ب"), True)
    assert editor.scoped_institution == "صحة ب"
    plain = S.make_session(AppUser(username="e2", role="editor"), True)
    assert plain.scoped_institution == ""


def test_session_identity_labels():
    session = S.make_session(AppUser(username="sara", display_name="سارة"), True)
    assert session.username == "sara"
    assert session.display_name == "سارة"
    local = S.make_session(None, False)
    assert local.username == "—" and local.auth_enabled is False
