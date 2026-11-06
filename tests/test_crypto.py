"""اختبارات خدمة التشفير (SQLCipher) وملف القفل."""

from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

from amdh_leave.services import crypto as C

PASSWORD = "سرّي-قوي-2026"
SALT = "aabbccddeeff00112233445566778899"


# ---------------------------------------------------------------------------
# اشتقاق المفتاح
# ---------------------------------------------------------------------------
def test_derive_key_is_deterministic_and_salt_sensitive():
    first = C.derive_key(PASSWORD, SALT)
    second = C.derive_key(PASSWORD, SALT)
    other_salt = C.derive_key(PASSWORD, "ff" * 16)
    other_password = C.derive_key("غيرها", SALT)
    assert first == second
    assert first != other_salt and first != other_password
    assert len(first) == C.KEY_BYTES * 2
    assert all(ch in "0123456789abcdef" for ch in first)


def test_derive_key_rejects_bad_input():
    with pytest.raises(C.CryptoError):
        C.derive_key("", SALT)
    with pytest.raises(C.CryptoError):
        C.derive_key(PASSWORD, "ليس-هيكس")


def test_key_pragma_uses_raw_key_format():
    assert C.key_pragma("abcd") == "\"x'abcd'\""


# ---------------------------------------------------------------------------
# ملف القفل
# ---------------------------------------------------------------------------
def test_lock_file_roundtrip(tmp_path):
    assert C.read_lock(tmp_path) is None
    assert C.is_encryption_enabled(tmp_path) is False

    path = C.write_lock(tmp_path, PASSWORD)
    assert path.exists() and path.name == C.LOCK_FILENAME
    data = C.read_lock(tmp_path)
    assert data["salt"] and data["verifier"] and data["enabled"] is True
    assert data["iterations"] == C.KDF_ITERATIONS
    # لا تُخزَّن كلمة المرور نفسها في الملف
    assert PASSWORD not in path.read_text(encoding="utf-8")
    assert C.check_password(tmp_path, PASSWORD) is True
    assert C.check_password(tmp_path, "خطأ") is False
    assert C.is_encryption_enabled(tmp_path) is True


def test_lock_file_removal(tmp_path):
    C.write_lock(tmp_path, PASSWORD)
    C.remove_lock(tmp_path)
    assert C.read_lock(tmp_path) is None
    C.remove_lock(tmp_path)          # لا خطأ عند عدم الوجود


def test_read_lock_ignores_corrupt_files(tmp_path):
    path = tmp_path / C.LOCK_FILENAME
    path.write_text("{ليس JSON", encoding="utf-8")
    assert C.read_lock(tmp_path) is None
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    assert C.read_lock(tmp_path) is None


# ---------------------------------------------------------------------------
# الكشف والتوفّر
# ---------------------------------------------------------------------------
def test_is_encrypted_database_detection(tmp_path, legacy_db):
    assert C.is_encrypted_database(legacy_db) is False       # قاعدة عادية
    assert C.is_encrypted_database(tmp_path / "missing.db") is False
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    assert C.is_encrypted_database(empty) is False
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is definitely not a sqlite database" * 5)
    assert C.is_encrypted_database(junk) is True


def test_available_flag_matches_module_presence(monkeypatch):
    monkeypatch.setattr(C, "sqlcipher_module", lambda: None)
    assert C.sqlcipher_available() is False
    monkeypatch.setattr(C, "sqlcipher_module", lambda: object())
    assert C.sqlcipher_available() is True


def test_install_hint_mentions_package():
    hint = C.install_hint()
    assert "sqlcipher3" in hint and "pip install" in hint


def test_open_connection_without_key_is_plain_sqlite(tmp_path):
    connection = C.open_connection(tmp_path / "plain.db")
    try:
        connection.execute("CREATE TABLE t(x)")
        connection.execute("INSERT INTO t VALUES (1)")
        assert connection.execute("SELECT x FROM t").fetchone()[0] == 1
    finally:
        connection.close()


def test_open_connection_with_key_raises_when_sqlcipher_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "sqlcipher_module", lambda: None)
    with pytest.raises(C.CryptoError) as error:
        C.open_connection(tmp_path / "x.db", "aabb")
    assert "sqlcipher3" in str(error.value)


def test_encrypt_and_decrypt_require_sqlcipher(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "sqlcipher_module", lambda: None)
    with pytest.raises(C.CryptoError):
        C.encrypt_database(tmp_path / "db.sqlite", PASSWORD)
    with pytest.raises(C.CryptoError):
        C.decrypt_database(tmp_path / "db.sqlite", PASSWORD)


def test_security_summary_shape(tmp_path, legacy_db):
    summary = C.security_summary(tmp_path, legacy_db)
    assert set(summary) == {"sqlcipher_available", "lock_file", "encryption_enabled",
                            "database_encrypted", "key_file", "mode", "lock_data"}
    assert summary["lock_file"] is False
    assert summary["database_encrypted"] is False
    C.write_lock(tmp_path, PASSWORD)
    summary = C.security_summary(tmp_path, legacy_db)
    assert summary["lock_file"] is True and summary["encryption_enabled"] is True


# ---------------------------------------------------------------------------
# مسار SQLCipher بمحاكي (اختبار منطق الاتصال والمفاتيح بلا الحزمة الحقيقية)
# ---------------------------------------------------------------------------
class _RecordingConnection:
    """يغلّف اتصال sqlite3 ويسجّل الأوامر لنتحقق من تمرير المفتاح."""

    def __init__(self, path: str, log: list[str]):
        self._real = sqlite3.connect(path)
        self._log = log

    def execute(self, sql, *args):
        self._log.append(sql)
        return self._real.execute(sql, *args)

    def close(self):
        self._real.close()

    def __getattr__(self, item):
        return getattr(self._real, item)


@pytest.fixture()
def fake_sqlcipher(monkeypatch):
    log: list[str] = []
    module = types.ModuleType("sqlcipher3")

    def connect(path):
        return _RecordingConnection(str(path), log)

    module.connect = connect
    monkeypatch.setitem(sys.modules, "sqlcipher3", module)
    monkeypatch.setattr(C, "sqlcipher_module", lambda: module)
    return log


def test_open_connection_with_key_applies_pragmas(tmp_path, fake_sqlcipher, legacy_db):
    key = C.derive_key(PASSWORD, SALT)
    connection = C.open_connection(legacy_db, key)
    try:
        assert any(sql.startswith("PRAGMA key") for sql in fake_sqlcipher)
        key_statement = [sql for sql in fake_sqlcipher if sql.startswith("PRAGMA key")][0]
        assert key in key_statement and key_statement.endswith("\"x'" + key + "'\"")
        assert any("cipher_page_size" in sql for sql in fake_sqlcipher)
        assert connection.execute("SELECT count(*) FROM employees").fetchone()[0] == 1
    finally:
        connection.close()


def test_open_connection_reports_wrong_password(tmp_path, monkeypatch):
    """أي فشل في أول استعلام بعد المفتاح يُترجم إلى رسالة كلمة مرور خاطئة."""
    class _Broken:
        def __init__(self):
            self.closed = False

        def execute(self, sql, *args):
            if sql.startswith("PRAGMA"):
                return self
            raise sqlite3.DatabaseError("file is not a database")

        def fetchone(self):
            raise sqlite3.DatabaseError("file is not a database")

        def close(self):
            self.closed = True

    module = types.ModuleType("sqlcipher3")
    module.connect = lambda _path: _Broken()
    monkeypatch.setattr(C, "sqlcipher_module", lambda: module)
    with pytest.raises(C.CryptoError) as error:
        C.open_connection(tmp_path / "x.db", "aabb")
    assert "كلمة المرور" in str(error.value)
