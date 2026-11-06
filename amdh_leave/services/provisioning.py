"""تجهيز نسخة مؤسسة: قاعدة بيانات مُنقّاة + مفتاح تشفير + حزمة تشغيل.

النسخة الناتجة:
    AMDH-<code>/
      AMDH-Leave.exe + _internal/       (نسخة من برنامج المركز)
      data/employees_leave.db           (بيانات المؤسسة + admin + مستخدمها)
      data/.amdh_dbkey                  (مفتاح فتح تلقائي)
      بيانات_الدخول.txt / تعليمات_التشغيل.txt / VERSION.txt
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from .. import config
from ..logging_setup import get_logger
from ..services import crypto, security as sec

LOG = get_logger("provisioning")
SKIP_NAMES = {"employees_leave.db", "employees_leave.db-wal", "employees_leave.db-shm",
              ".amdh_lock.json", ".amdh_dbkey", ".amdh_instance.lock"}


def _staging_copy(center_db, dest: Path) -> Path:
    """نسخة نصية من قاعدة المركز (تعمل سواء كانت مشفّرة أو لا)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    center_db.export_plaintext(dest)
    return dest


def build_institution_database(center_db, institution: str, dest: Path, *,
                               admin_password: str, user_password: str,
                               user_role: str = "editor") -> dict:
    """يبني قاعدة مؤسسة مُنقّاة (نصية) بمستخدم admin ومستخدم مؤسسة."""
    institution = str(institution or "").strip()
    record = center_db.get_institution(institution)
    if record is None:
        raise ValueError("المؤسسة غير موجودة في المركز.")
    if record.is_center or center_db.center_institution() == institution:
        raise ValueError("لا يمكن تجهيز نسخة لمؤسسة المركز نفسها.")
    if not record.username:
        raise ValueError("أنشئ مستخدم المؤسسة أولاً من نافذة المؤسسات.")
    if not admin_password:
        raise ValueError("كلمة مرور admin للصيانة مطلوبة.")
    if not user_password:
        raise ValueError("كلمة مرور مستخدم المؤسسة مطلوبة.")

    dest = Path(dest)
    temp = dest.with_name(dest.name + ".building")
    if temp.exists():
        temp.unlink()
    _staging_copy(center_db, temp)
    connection = sqlite3.connect(str(temp))
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        # قصر البيانات على موظفي المؤسسة (مع إجازاتهم ومرفقاتهم وتاريخ انتقالهم)
        connection.execute(
            "DELETE FROM leaves WHERE emp_id NOT IN "
            "(SELECT emp_id FROM employees WHERE institution=?)", (institution,))
        connection.execute("DELETE FROM employees WHERE institution<>?", (institution,))
        connection.execute(
            "DELETE FROM attachments WHERE emp_id NOT IN (SELECT emp_id FROM employees)")
        connection.execute(
            "DELETE FROM employee_moves WHERE emp_id NOT IN (SELECT emp_id FROM employees)")

        center_name = center_db.center_institution()
        if center_name:
            connection.execute("DELETE FROM institutions WHERE name NOT IN (?,?)",
                               (center_name, institution))
            connection.execute("UPDATE institutions SET is_center=1 WHERE name=?", (center_name,))
        else:
            connection.execute("DELETE FROM institutions WHERE name<>?", (institution,))
        if not connection.execute("SELECT 1 FROM institutions WHERE name=?",
                                  (institution,)).fetchone():
            connection.execute(
                "INSERT INTO institutions(name, code, kind, is_center, active, created_at, "
                "updated_at) VALUES (?,?,?,?,1,?,?)",
                (institution, record.code, record.kind,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        # المستخدمون: admin للصيانة + مستخدم المؤسسة المقيّد
        connection.execute("DELETE FROM app_users")
        admin_hash, admin_salt, admin_iter = sec.hash_password(admin_password)
        user_hash, user_salt, user_iter = sec.hash_password(user_password)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        connection.execute(
            "INSERT INTO app_users(username, display_name, role, institution, password_hash, "
            "salt, iterations, active, created_at) VALUES (?,?,?,?,?,?,?,1,?)",
            ("admin", "مدير النظام", "admin", "", admin_hash, admin_salt, admin_iter, now))
        connection.execute(
            "INSERT INTO app_users(username, display_name, role, institution, password_hash, "
            "salt, iterations, active, created_at) VALUES (?,?,?,?,?,?,?,1,?)",
            (record.username, institution, user_role, institution, user_hash, user_salt,
             user_iter, now))
        connection.execute("UPDATE institutions SET username=? WHERE name=?",
                           (record.username, institution))

        # لا يُصدَّر تدقيق المركز ولا سجل الاستيراد ولا خزنة كلمات المرور المركزية
        for table in ("audit_log", "imports", "transfer_manifest", "password_vault",
                      "employee_opening_history"):
            try:
                connection.execute(f"DELETE FROM {table}")
            except sqlite3.DatabaseError:
                pass
        connection.execute("INSERT OR REPLACE INTO app_meta(key, value) VALUES ('auth_enabled','1')")
        connection.execute("INSERT OR REPLACE INTO app_meta(key, value) VALUES "
                           "('center_institution',?)", (center_name,))
        connection.execute("INSERT OR REPLACE INTO app_meta(key, value) VALUES "
                           "('provisioned_institution',?)", (institution,))
        connection.execute("INSERT OR REPLACE INTO app_meta(key, value) VALUES "
                           "('provisioned_at',?)", (now,))
        connection.commit()
        connection.execute("VACUUM")
        counts = {
            "employees": connection.execute(
                "SELECT COUNT(*) FROM employees WHERE deleted_at IS NULL OR deleted_at=''"
            ).fetchone()[0],
            "leaves": connection.execute(
                "SELECT COUNT(*) FROM leaves WHERE deleted_at IS NULL OR deleted_at=''"
            ).fetchone()[0],
            "attachments": connection.execute("SELECT COUNT(*) FROM attachments").fetchone()[0],
        }
    finally:
        connection.close()

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    temp.replace(dest)
    return counts


def build_institution_folder(ctx, institution: str, destination: Path, *,
                             admin_password: str, user_password: str,
                             include_program: bool = True,
                             make_zip: bool = True) -> dict:
    """ينشئ مجلد حزمة المؤسسة (وZIP اختياري) ويعيد بيانات الدخول والمسارات."""
    institution = str(institution or "").strip()
    record = ctx.db.get_institution(institution)
    if record is None:
        raise ValueError("المؤسسة غير موجودة.")
    if not getattr(sys, "frozen", False) and include_program:
        raise RuntimeError("تجهيز نسخة كاملة يتطلب تشغيل النسخة التنفيذية (EXE).")

    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"المجلد غير فارغ: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    if include_program:
        _copy_program(destination)

    data_dir = destination / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / config.DB_FILENAME
    counts = build_institution_database(
        ctx.db, institution, db_path, admin_password=admin_password,
        user_password=user_password)

    # مرفقات المؤسسة فقط
    _copy_attachments(ctx, institution, data_dir / "attachments")

    key_hex = os.urandom(32).hex()
    crypto.encrypt_with_key(db_path, key_hex, keep_backup=False)

    _write_texts(destination, record, counts, user_password, include_program)
    zip_path = None
    if make_zip:
        zip_path = destination.with_suffix(".zip")
        _zip_folder(destination, zip_path)
    LOG.warning("جُهّزت نسخة المؤسسة %s في %s", institution, destination)
    return {"folder": destination, "zip": zip_path, "counts": counts,
            "username": record.username, "password": user_password, "key": key_hex}


# ---------------------------------------------------------------------------
# نسخ ملفات البرنامج والمرفقات والنصوص
# ---------------------------------------------------------------------------
def _copy_program(destination: Path) -> None:
    root = Path(sys.executable).resolve().parent
    exe = Path(sys.executable)
    shutil.copy2(exe, destination / exe.name)
    internal = root / "_internal"
    if internal.is_dir():
        shutil.copytree(internal, destination / "_internal",
                        ignore=shutil.ignore_patterns(*SKIP_NAMES))
    readme = root / "README.md"
    if readme.exists():
        shutil.copy2(readme, destination / "README.md")


def _copy_attachments(ctx, institution: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    rows = ctx.db.conn.execute(
        "SELECT a.stored_name FROM attachments a JOIN employees e ON e.emp_id=a.emp_id "
        "WHERE e.institution=?", (institution,)).fetchall()
    source_dir = Path(ctx.paths.attachments_dir)
    for row in rows:
        stored = str(row[0] or "")
        if not stored:
            continue
        source = source_dir / stored
        if source.exists():
            shutil.copy2(source, destination / stored)


def _write_texts(destination: Path, record, counts: dict, user_password: str,
                 include_program: bool) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    credentials = (
        f"المؤسسة: {record.name}\n"
        f"الرمز: {record.code}\n"
        f"اسم المستخدم: {record.username}\n"
        f"كلمة المرور: {user_password}\n"
        f"تاريخ التسليم: {now}\n\n"
        "ملاحظة: هذا حساب «مدخل بيانات» مقيّد بموظفي المؤسسة فقط.\n"
        "حساب الصيانة (admin) كلمة مروره لدى مركز الدائرة، ولا تُكتب هنا.\n"
        "احتفظ بهذه الورقة في مكان آمن، وغيّر كلمة المرور إن أمكن.\n")
    (destination / "بيانات_الدخول.txt").write_text(credentials, encoding="utf-8")

    instructions = (
        f"نظام إدارة الرصيد التراكمي للإجازات — نسخة مؤسسة: {record.name}\n"
        "=" * 58 + "\n"
        "1) انسخ/فكّ ضغط المجلد إلى قرص محلي (مثال: C:\\AMDH\\" + (record.code or "INST") + ").\n"
        "   لا تضعه في Program Files حتى لا تُمنع الكتابة.\n"
        f"2) شغّل {('AMDH-Leave.exe' if include_program else 'البرنامج')} "
        "(أو تشغيل.bat).\n"
        "3) سجّل الدخول باسم المستخدم وكلمة المرور الموجودة في بيانات_الدخول.txt.\n"
        "4) لا تحذف مجلد data ولا ملف data/.amdh_dbkey: هما بيانات المؤسسة ومفتاحها.\n"
        "   النسخ الاحتياطية مشفّرة، ومفتاحها في مجلد data؛ فقدانه يعني فقدان الوصول.\n"
        "5) في نهاية كل شهر: «تصدير للمركز» ← اختر الشهر ← احفظ ملف .amdhz ← سلّمه للمركز.\n"
        "6) حساب admin للصيانة فقط؛ لا تشارك كلمة مروره مع موظفي المؤسسة.\n"
        "7) عند التحديث: استبدل AMDH-Leave.exe و_internal فقط، وأبقِ data كما هي.\n")
    (destination / "تعليمات_التشغيل.txt").write_text(instructions, encoding="utf-8")

    version = (
        f"APP_VERSION={config.APP_VERSION}\n"
        f"APP_RELEASE={config.APP_RELEASE}\n"
        f"INSTITUTION={record.name}\n"
        f"CODE={record.code}\n"
        f"EMPLOYEES={counts.get('employees', 0)}\n"
        f"LEAVES={counts.get('leaves', 0)}\n"
        f"ATTACHMENTS={counts.get('attachments', 0)}\n"
        f"CREATED_AT={now}\n")
    (destination / "VERSION.txt").write_text(version, encoding="utf-8")

    if include_program:
        launcher = (
            "@echo off\r\n"
            "cd /d \"%~dp0\"\r\n"
            "start \"\" \"AMDH-Leave.exe\" --data-dir \"%~dp0data\"\r\n")
        (destination / "تشغيل.bat").write_text(launcher, encoding="utf-8")


def _zip_folder(folder: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in folder.rglob("*"):
            if path.is_file() and path != zip_path:
                archive.write(path, path.relative_to(folder).as_posix())
