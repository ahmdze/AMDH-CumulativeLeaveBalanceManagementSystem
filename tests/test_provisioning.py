"""اختبارات تجهيز نسخة المؤسسة (قاعدة مُنقّاة + مفتاح + حزمة)."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from amdh_leave import config
from amdh_leave.db import Database
from amdh_leave.services import crypto
from amdh_leave.services import institutions as INST
from amdh_leave.services import provisioning as P
from amdh_leave.services import security as sec


@pytest.fixture()
def center(tmp_path):
    pytest.importorskip("sqlcipher3")
    paths = config.Paths(tmp_path / "center").ensure()
    db = Database(paths.db_path, paths.backups_dir)
    db.save_institution({"name": "مركز الدائرة", "code": "C0", "kind": "مركز الدائرة"}, "admin")
    db.set_center_institution("مركز الدائرة")
    db.save_institution({"name": "مستشفى الكرامة", "code": "H1", "kind": "مستشفى"}, "admin")
    db.add_employee("1001", {"name": "موظف", "institution": "مستشفى الكرامة",
                             "start_date": "2015-01-01"}, "admin")
    db.add_leave("1001", {"type": "اعتيادية", "start_date": "2026-01-01",
                          "end_date": "2026-01-10", "amount": 10, "unit": "يوم",
                          "days_actual": 10, "status": "approved"}, "admin")
    institution = db.get_institution("مستشفى الكرامة")
    account, password = INST.create_user_for_institution(db, institution, user="admin")
    db.set_meta({"auth_enabled": "1"})
    yield SimpleNamespace(paths=paths, db=db, institution=institution,
                          username=account.username, password=password)
    db.close()


def test_delete_institution_removes_linked_user(tmp_path):
    db = Database(tmp_path / "d.db", tmp_path / "b")
    db.save_institution({"name": "مؤسسة أ", "code": "A"}, "admin")
    institution = db.get_institution("مؤسسة أ")
    account, _password = INST.create_user_for_institution(db, institution, user="admin")
    ok, message = db.delete_institution("مؤسسة أ", user="admin")
    assert ok and "مستخدم" in message
    assert db.get_institution("مؤسسة أ") is None
    assert db.get_user(account.username) is None
    db.close()


def test_center_institution_cannot_be_deleted(tmp_path):
    db = Database(tmp_path / "d.db", tmp_path / "b")
    db.save_institution({"name": "المركز", "kind": "مركز الدائرة"}, "admin")
    db.set_center_institution("المركز")
    ok, message = db.delete_institution("المركز")
    assert not ok and "مركز" in message
    db.close()


def test_build_institution_package(center, tmp_path):
    center.db.add_vault_entry(kind="master", label="سري", password="MasterSecret")
    result = P.build_institution_folder(
        center, "مستشفى الكرامة", tmp_path / "AMDH_H1",
        admin_password="Ahmed1996", user_password=center.password,
        include_program=False, make_zip=True)
    data = tmp_path / "AMDH_H1" / "data"
    assert (data / ".amdh_dbkey").exists()
    assert result["zip"].exists()
    assert result["counts"]["employees"] == 1
    assert result["counts"]["leaves"] == 1

    with pytest.raises(sqlite3.DatabaseError):
        plain = sqlite3.connect(str(data / config.DB_FILENAME))
        plain.execute("select count(*) from employees").fetchone()
        plain.close()

    key = crypto.read_key_file(data)
    copy = Database(data / config.DB_FILENAME, data / "backups", key_hex=key)
    try:
        users = {user.username: user for user in copy.list_users()}
        assert set(users) == {"admin", center.username}
        assert users["admin"].role == "admin"
        assert users[center.username].role == "editor"
        assert users[center.username].institution == "مستشفى الكرامة"
        assert sec.verify_password("Ahmed1996", users["admin"].password_hash,
                                   users["admin"].salt, users["admin"].iterations)
        assert sec.verify_password(center.password, users[center.username].password_hash,
                                   users[center.username].salt, users[center.username].iterations)
        assert copy.policy(refresh=True).auth_enabled is True
        assert copy.center_institution() == "مركز الدائرة"
        assert [item.name for item in copy.list_institutions()] == ["مركز الدائرة", "مستشفى الكرامة"]
        assert [employee.emp_id for employee in copy.list_employees()] == ["1001"]
        assert copy.list_audit(limit=10) == []
        assert copy.list_vault() == []
    finally:
        copy.close()
