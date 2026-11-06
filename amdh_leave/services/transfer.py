"""ملفات النقل بين المركز والمؤسسات: تصدير مُنقّى، معاينة، واستيراد.

الصيغ المدعومة:
  * ``.amdhz`` — أرشيف ZIP يحوي ``data.db`` و``manifest.json`` و``attachments/`` (الموصى به،
    لأن المرفقات تنتقل مع البيانات كما هو مطلوب في حالة نقل الموظفين والأوامر).
  * ``.db`` — قاعدة SQLite عادية (بلا مرفقات) للتوافق مع الطريقة القديمة.

التنقية: لا تُصدَّر جداول المستخدمين (بصمات كلمات المرور) ولا سجل التدقيق ولا سجل
الاستيراد الخاص بالنسخة المُصدِّرة، وتُقصر البيانات على مؤسسة واحدة عند تحديدها.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from ..logging_setup import get_logger
from . import merge as M

LOG = get_logger("transfer")
FORMAT = "amdh-transfer-1"
MANIFEST_NAME = "manifest.json"
DATA_NAME = "data.db"
ATTACHMENTS_DIR = "attachments"
DROP_TABLES = ("app_users", "audit_log", "imports", "password_vault", "employee_opening_history")


# ---------------------------------------------------------------------------
# التصدير
# ---------------------------------------------------------------------------
def export_transfer(
    db,
    dest_path: str | Path,
    *,
    institution: str = "",
    include_attachments: bool = True,
    user: str = "",
    attachments_dir: Path | None = None,
    period: tuple[str, str] | None = None,
    center: str = "",
) -> dict:
    """ينشئ ملف نقل مُنقّى ويعيد بيان المحتوى (manifest)."""
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    institution = (institution or "").strip()
    attachments_dir = Path(attachments_dir) if attachments_dir else db.path.parent / "attachments"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    work_dir = Path(tempfile.mkdtemp(prefix="amdh_export_"))
    try:
        staging = work_dir / DATA_NAME
        # ملف النقل يجب أن يكون عادياً (غير مشفّر) حتى يُقرأ ويُدمج في أي نسخة؛
        # لذلك نُصدّر نسخة نصية من القاعدة المشفّرة بدل نسخها كما هي.
        db.export_plaintext(staging)
        counts = _sanitize(staging, institution, db.conn)
        manifest = {
            "format": FORMAT,
            "app_version": __import__("amdh_leave", fromlist=["__version__"]).__version__,
            "schema_version": db.schema_version,
            "institution": institution,
            "institution_code": (
                db.get_institution(institution).code
                if institution and db.get_institution(institution)
                else ""
            ),
            "center_institution": center or db.center_institution(),
            "generated_at": now,
            "generated_by": user or "—",
            "period_from": period[0] if period else "",
            "period_to": period[1] if period else "",
            "policy_fingerprint": M.policy_fingerprint(db),
            "counts": counts,
        }
        _write_manifest(staging, manifest)

        attachment_files = _collect_attachments(staging, attachments_dir, work_dir)
        manifest["counts"]["attachment_files"] = len(attachment_files)

        # الامتداد المطلوب يحكم الصيغة: .amdhz/.zip ⇒ أرشيف دائماً، .db ⇒ قاعدة فقط،
        # وغير ذلك تلقائي (أرشيف إن وُجدت مرفقات).
        suffix = dest_path.suffix.lower()
        wants_archive = suffix in {".amdhz", ".zip"}
        wants_plain = suffix == ".db"
        if wants_archive or (not wants_plain and include_attachments and attachment_files):
            manifest["data_checksum"] = M.file_checksum(staging)
            with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(staging, DATA_NAME)
                archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
                for stored_name, source_file in attachment_files:
                    archive.write(source_file, f"{ATTACHMENTS_DIR}/{stored_name}")
        else:
            shutil.copy2(staging, dest_path)
        manifest["path"] = str(dest_path)

        if institution:
            db.set_institution_export(institution, now)
        db.add_import(
            {
                "ts": now,
                "username": user or "—",
                "direction": "export",
                "scope": institution or "كل المؤسسات",
                "institution": institution,
                "source_file": dest_path.name,
                "checksum": M.file_checksum(dest_path),
                "source_schema": db.schema_version,
                "source_policy": manifest["policy_fingerprint"],
                "employees_added": counts.get("employees", 0),
                "leaves_added": counts.get("leaves", 0),
                "attachments": len(attachment_files),
                "report": json.dumps(manifest, ensure_ascii=False),
            },
            user,
        )
        db.log(
            user,
            "تصدير",
            "transfer",
            dest_path.name,
            f"{institution or 'كل المؤسسات'}: {counts.get('employees', 0)} موظف، "
            f"{counts.get('leaves', 0)} إجازة، {len(attachment_files)} مرفق",
        )
        LOG.info("صُدِّر ملف نقل: %s (%s)", dest_path.name, manifest["counts"])
        return manifest
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _sanitize(db_path: Path, institution: str, source_connection=None) -> dict:
    """يحذف ما لا يجب تصديره ويقصر البيانات على مؤسسة (عند تحديدها) ويعيد الأعداد."""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in DROP_TABLES:
            if table in tables:
                connection.execute(f"DELETE FROM {table}")
        # لا نُبقي تسجيل الدخول مفعّلاً بلا مستخدمين (حتى لا يُقفل الملف إن فُتح مباشرة)
        if "app_meta" in tables:
            connection.execute("INSERT OR REPLACE INTO app_meta(key, value) VALUES ('auth_enabled', '0')")
        if "transfer_manifest" in tables:
            connection.execute("DELETE FROM transfer_manifest")
        if institution:
            if "attachments" in tables:
                connection.execute(
                    "DELETE FROM attachments WHERE emp_id NOT IN "
                    "(SELECT emp_id FROM employees WHERE institution=?)",
                    (institution,),
                )
            connection.execute(
                "DELETE FROM leaves WHERE emp_id NOT IN (SELECT emp_id FROM employees WHERE institution=?)",
                (institution,),
            )
            connection.execute("DELETE FROM employees WHERE institution<>?", (institution,))
            connection.execute(
                "DELETE FROM employee_moves WHERE emp_id NOT IN (SELECT emp_id FROM employees)"
            )
            if "institutions" in tables:
                connection.execute("DELETE FROM institutions WHERE name<>?", (institution,))
        counts = {
            "employees": connection.execute(
                "SELECT COUNT(*) FROM employees WHERE deleted_at IS NULL OR deleted_at=''"
            ).fetchone()[0],
            "employees_deleted": connection.execute(
                "SELECT COUNT(*) FROM employees WHERE deleted_at IS NOT NULL AND deleted_at<>''"
            ).fetchone()[0],
            "leaves": connection.execute(
                "SELECT COUNT(*) FROM leaves WHERE deleted_at IS NULL OR deleted_at=''"
            ).fetchone()[0],
            "leaves_deleted": connection.execute(
                "SELECT COUNT(*) FROM leaves WHERE deleted_at IS NOT NULL AND deleted_at<>''"
            ).fetchone()[0],
            "attachments": (
                connection.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
                if "attachments" in tables
                else 0
            ),
            "moves": (
                connection.execute("SELECT COUNT(*) FROM employee_moves").fetchone()[0]
                if "employee_moves" in tables
                else 0
            ),
        }
        connection.commit()
        connection.execute("VACUUM")
        return counts
    finally:
        connection.close()


def _write_manifest(db_path: Path, manifest: dict) -> None:
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS transfer_manifest (key TEXT PRIMARY KEY, value TEXT)")
        for key, value in manifest.items():
            stored = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
            connection.execute(
                "INSERT OR REPLACE INTO transfer_manifest(key, value) VALUES (?,?)", (str(key), stored)
            )
        connection.commit()
    finally:
        connection.close()


def _collect_attachments(db_path: Path, attachments_dir: Path, work_dir: Path) -> list[tuple[str, Path]]:
    """يجمع ملفات المرفقات المشار إليها في قاعدة الملف (للأرشفة)."""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute("SELECT stored_name, filename FROM attachments").fetchall()
        except sqlite3.DatabaseError:
            return []
    finally:
        connection.close()
    files: list[tuple[str, Path]] = []
    for row in rows:
        stored = str(row["stored_name"] or "")
        if not stored:
            continue
        source = Path(attachments_dir) / stored
        if source.exists():
            files.append((stored, source))
        else:
            LOG.warning("مرفق مفقود على القرص: %s (%s)", row["filename"], stored)
    return files


# ---------------------------------------------------------------------------
# قراءة ملف النقل
# ---------------------------------------------------------------------------
def is_archive(path: Path) -> bool:
    return Path(path).suffix.lower() in {".amdhz", ".zip"}


def read_transfer_info(path: str | Path, key_hex: str = "") -> dict:
    """معلومات ملف النقل بلا فك أرشيف كامل: البيان + الأعداد."""
    path = Path(path)
    if is_archive(path):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if DATA_NAME not in names:
                raise ValueError("الأرشيف لا يحتوي ملف قاعدة بيانات (data.db).")
            manifest = {}
            if MANIFEST_NAME in names:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            info = {
                "archive": True,
                "manifest": manifest,
                "attachment_files": len([n for n in names if n.startswith(ATTACHMENTS_DIR + "/")]),
                "size": path.stat().st_size,
                "name": path.name,
                "checksum": M.file_checksum(path),
            }
            return info
    # قاعدة بيانات عادية: البيان مخزَّن في جدول transfer_manifest
    manifest = {}
    try:
        connection = _read_only(path)
        try:
            tables = {
                row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "transfer_manifest" in tables:
                for row in connection.execute("SELECT key, value FROM transfer_manifest"):
                    manifest[row[0]] = row[1]
        finally:
            connection.close()
    except Exception:  # noqa: BLE001
        manifest = {}
    return {
        "archive": False,
        "manifest": manifest,
        "attachment_files": 0,
        "size": path.stat().st_size,
        "name": path.name,
        "checksum": M.file_checksum(path),
    }


def _read_only(path: Path):
    import sqlite3

    from . import crypto

    if crypto.is_encrypted_database(path):
        raise ValueError("الملف مشفّر")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def prepare_source(path: str | Path, key_hex: str = "") -> PreparedTransfer:
    """يفك الأرشيف (إن لزم) إلى مجلد مؤقت ويعيد مسار القاعدة ومجلد المرفقات."""
    path = Path(path)
    if not is_archive(path):
        attachments = path.parent / ATTACHMENTS_DIR
        return PreparedTransfer(
            db_path=path,
            attachments_dir=attachments if attachments.exists() else None,
            manifest={},
            temp_dir=None,
        )
    temp_dir = Path(tempfile.mkdtemp(prefix="amdh_import_"))
    with zipfile.ZipFile(path) as archive:
        archive.extractall(temp_dir)
    manifest: dict = {}
    manifest_file = temp_dir / MANIFEST_NAME
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    attachments = temp_dir / ATTACHMENTS_DIR
    return PreparedTransfer(
        db_path=temp_dir / DATA_NAME,
        attachments_dir=attachments if attachments.exists() else None,
        manifest=manifest,
        temp_dir=temp_dir,
    )


class PreparedTransfer:
    def __init__(
        self, db_path: Path, attachments_dir: Path | None, manifest: dict, temp_dir: Path | None
    ) -> None:
        self.db_path = Path(db_path)
        self.attachments_dir = Path(attachments_dir) if attachments_dir else None
        self.manifest = manifest or {}
        self.temp_dir = Path(temp_dir) if temp_dir else None

    def cleanup(self) -> None:
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def __enter__(self) -> PreparedTransfer:
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()


def preview_transfer(target, path: str | Path, options: M.MergeOptions | None = None):
    """معاينة دمج ملف نقل (يفك الأرشيف مؤقتاً ثم ينظّف)."""
    with prepare_source(path, (options.key_hex if options else "")) as prepared:
        effective = options or M.MergeOptions()
        if not effective.institution:
            effective.institution = str(prepared.manifest.get("institution") or "")
        effective.source_attachments_dir = prepared.attachments_dir
        info = read_transfer_info(path, effective.key_hex)
        plan = M.build_plan(target, prepared.db_path, effective)
        plan.manifest = {**prepared.manifest, **plan.manifest}
        return plan, plan.report(), info


def apply_transfer(
    target,
    path: str | Path,
    options: M.MergeOptions | None = None,
    *,
    user: str = "",
    attachments_dir: Path | None = None,
) -> M.MergeReport:
    """يستورد ملف نقل (يفك الأرشيف مؤقتاً، ثم يُدمج ويُنظّف)."""
    with prepare_source(path, (options.key_hex if options else "")) as prepared:
        effective = options or M.MergeOptions()
        if not effective.institution:
            effective.institution = str(prepared.manifest.get("institution") or "")
        effective.source_attachments_dir = prepared.attachments_dir
        return M.merge(target, prepared.db_path, effective, user=user, attachments_dir=attachments_dir)
