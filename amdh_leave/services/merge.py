"""محرّك الدمج بين نسخ المؤسسات ونسخة المركز — غير مُدمّر وقائم على الهوية الثابتة.

المبادئ:
  1. **لا حذف أبداً**: لا تُمسح إجازات موجودة في الهدف؛ الدمج إضافي/تحديثي فقط.
  2. **الرقم الوظيفي هو الهوية**: الموظف واحد مهما تنقّل بين المؤسسات، والتنقّل يُسجَّل
     في ``employee_moves`` مع تحديث مؤسسته الحالية (فيبقى رصيده واحداً).
  3. **uid لكل إجازة**: هوية ثابتة تُنشأ عند التسجيل وتنتقل مع كل نسخة، فيتعرّف النظام
     على الإجازة نفسها في النسختين (لا تكرار ولا ازدواج).
  4. **نقل الحذف الناعم**: إجازة حُذفت في المستشفى تُحذف (ناعماً) في المركز أيضاً.
  5. **الأحدث يفوز**: عند اختلاف محتوى السجل نفسه تُقارن أوقات التعديل، وتُسجَّل الحالة
     في تقرير التعارضات مع الطرف الذي فاز.
  6. **نقل المرفقات**: تُنسخ ملفات الأوامر مع بصمة sha256 لمنع التكرار والتحقق من السلامة.
  7. **معاينة كاملة قبل التنفيذ**: بناء «خطة» بلا أي كتابة، ثم تنفيذها في معاملة واحدة.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..db import SCHEMA_VERSION
from ..logging_setup import get_logger
from . import crypto
from . import dates as D

LOG = get_logger("merge")

EMPLOYEE_CONTENT = (
    "name",
    "job_title",
    "workplace",
    "gender",
    "start_date",
    "end_date",
    "notes",
    "status",
    "opening_balance_set",
    "opening_balance",
    "opening_balance_date",
    "opening_balance_by",
    "opening_balance_note",
    "secondment_to",
    "secondment_start",
    "secondment_end",
    "secondment_order",
)
LEAVE_CONTENT = (
    "type",
    "start_date",
    "end_date",
    "amount",
    "unit",
    "days_actual",
    "working_days",
    "count_mode",
    "order_num",
    "order_date",
    "outside_balance",
    "reason",
    "status",
    "is_adjustment",
    "manual_days",
)
ALLOWED_LEAVE_FIELDS = LEAVE_CONTENT + (
    "uid",
    "institution",
    "deleted_at",
    "deleted_by",
    "created_by",
    "approved_by",
    "approved_at",
)
LEAVE_NUMERIC = {"amount", "days_actual", "working_days", "outside_balance", "is_adjustment", "manual_days"}
EMPLOYEE_TIMESTAMPS = ("created_at", "updated_at", "opening_updated_at")
LEAVE_TIMESTAMPS = ("added_date", "modified_at")


# ---------------------------------------------------------------------------
# الخيارات والتقرير
# ---------------------------------------------------------------------------
@dataclass
class MergeOptions:
    institution: str = ""  # المؤسسة المعلنة للملف (تُستنتج إن كانت فارغة)
    allow_other_institutions: bool = False
    prefer: str = "newest"  # newest | source | target
    transfer_attachments: bool = True
    dry_run: bool = False
    key_hex: str = ""  # لفك تشفير ملف مصدر مشفّر
    source_attachments_dir: Path | None = None


@dataclass
class MergeReport:
    source_file: str = ""
    checksum: str = ""
    institution: str = ""
    source_schema: int = 0
    source_app_version: str = ""
    generated_at: str = ""
    period_from: str = ""
    period_to: str = ""
    employees_added: int = 0
    employees_updated: int = 0
    employees_unchanged: int = 0
    employees_skipped: int = 0
    leaves_added: int = 0
    leaves_updated: int = 0
    leaves_unchanged: int = 0
    leaves_deleted_in_source: int = 0
    moves: int = 0
    attachments_added: int = 0
    attachments_skipped: int = 0
    institutions_created: list[str] = field(default_factory=list)
    conflict_list: list[dict] = field(default_factory=list)
    move_list: list[dict] = field(default_factory=list)
    skipped_list: list[dict] = field(default_factory=list)
    overlap_list: list[dict] = field(default_factory=list)
    attachment_list: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_institutions: list[str] = field(default_factory=list)

    @property
    def employees_total(self) -> int:
        return self.employees_added + self.employees_updated + self.employees_unchanged

    @property
    def leaves_total(self) -> int:
        return self.leaves_added + self.leaves_updated + self.leaves_unchanged

    @property
    def conflicts(self) -> int:
        return len(self.conflict_list)

    def to_dict(self) -> dict:
        data = {key: value for key, value in self.__dict__.items()}
        data["conflicts"] = self.conflicts
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> MergeReport:
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError:
            return cls()
        report = cls()
        for key, value in data.items():
            if key in report.__dict__:
                setattr(report, key, value)
        return report

    def summary_lines(self) -> list[str]:
        lines = [
            f"الملف: {Path(self.source_file).name}"
            + (f" (بصمة {self.checksum[:10]}…)" if self.checksum else ""),
            f"المؤسسة: {self.institution or 'غير محددة'}",
            f"إصدار مخطط الملف: {self.source_schema or '—'}"
            + (f" | أُنشئ في {self.generated_at}" if self.generated_at else ""),
            "",
            f"الموظفون: أُضيف {self.employees_added} | حُدِّث {self.employees_updated} | "
            f"بلا تغيير {self.employees_unchanged} | تُجوهل {self.employees_skipped}",
            f"الإجازات: أُضيفت {self.leaves_added} | حُدِّثت {self.leaves_updated} | "
            f"بلا تغيير {self.leaves_unchanged}"
            + (f" | حذف ناعم نُقل {self.leaves_deleted_in_source}" if self.leaves_deleted_in_source else ""),
            f"انتقالات مؤسسات: {self.moves} | مرفقات نُقلت: {self.attachments_added} "
            f"(موجودة مسبقاً: {self.attachments_skipped})",
        ]
        if self.institutions_created:
            lines.append("مؤسسات أُنشئت: " + "، ".join(self.institutions_created))
        if self.conflict_list:
            lines.append(f"تعارضات: {len(self.conflict_list)} (فاز الأحدث — التفاصيل في التقرير)")
        if self.overlap_list:
            lines.append(f"تقاطعات زمنية محتملة: {len(self.overlap_list)}")
        if self.skipped_list:
            lines.append(f"سجلات تُجوهلت: {len(self.skipped_list)}")
        if self.warnings:
            lines.append("")
            lines.extend("⚠️ " + warning for warning in self.warnings)
        return lines


# ---------------------------------------------------------------------------
# قراءة المصدر
# ---------------------------------------------------------------------------
def _open_source(path: Path, key_hex: str = "") -> sqlite3.Connection:
    path = Path(path)
    if key_hex:
        connection = crypto.open_connection(path, key_hex)
    else:
        if crypto.is_encrypted_database(path):
            raise ValueError("ملف المصدر مشفّر — أدخل كلمة المرور أو استخدم ملفاً غير مشفّر.")
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    if table not in _tables(connection):
        return []
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source_info(path: Path, key_hex: str = "") -> dict:
    """معلومات الملف دون أي كتابة: المؤسسة، الأعداد، الإصدار، البصمة، الضوابط."""
    path = Path(path)
    info: dict = {
        "path": str(path),
        "name": path.name,
        "size": path.stat().st_size,
        "checksum": file_checksum(path),
        "encrypted": crypto.is_encrypted_database(path),
        "manifest": {},
        "counts": {},
        "schema": 0,
        "policy": {},
        "institutions": [],
    }
    connection = _open_source(path, key_hex)
    try:
        tables = _tables(connection)
        if "employees" not in tables:
            raise ValueError("الملف لا يحتوي جدول الموظفين — ليس نسخة من هذا النظام.")
        info["schema"] = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if "transfer_manifest" in tables:
            info["manifest"] = {
                row[0]: row[1] for row in connection.execute("SELECT key, value FROM transfer_manifest")
            }
        if "app_meta" in tables:
            meta = {row[0]: row[1] for row in connection.execute("SELECT key, value FROM app_meta")}
            info["policy"] = {
                key: meta.get(key)
                for key in ("days_per_leave", "max_annual", "basis", "weekend", "enforce_annual_cap")
            }
        employees = _rows(connection, "employees")
        leaves = _rows(connection, "leaves")
        info["counts"] = {
            "employees": len([e for e in employees if not e.get("deleted_at")]),
            "employees_deleted": len([e for e in employees if e.get("deleted_at")]),
            "leaves": len([lv for lv in leaves if not lv.get("deleted_at")]),
            "leaves_deleted": len([lv for lv in leaves if lv.get("deleted_at")]),
            "attachments": len(_rows(connection, "attachments")),
        }
        info["institutions"] = sorted(
            {
                str(row.get("institution") or "").strip()
                for row in employees + leaves
                if str(row.get("institution") or "").strip()
            }
        )
        if info["manifest"].get("institution"):
            declared = info["manifest"]["institution"]
            if declared not in info["institutions"]:
                info["institutions"].append(declared)
    finally:
        connection.close()
    return info


def policy_fingerprint(db) -> str:
    policy = db.policy(refresh=True)
    payload = {
        "days_per_leave": policy.days_per_leave,
        "max_annual": policy.max_annual,
        "basis": policy.basis,
        "weekend": list(policy.weekend),
        "enforce_annual_cap": policy.enforce_annual_cap,
        "rules": {name: rule.to_mapping() for name, rule in sorted(policy.rules.items())},
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# الخطة
# ---------------------------------------------------------------------------
@dataclass
class MergePlan:
    options: MergeOptions
    source_file: str = ""
    checksum: str = ""
    institution: str = ""
    source_schema: int = 0
    source_app_version: str = ""
    generated_at: str = ""
    period_from: str = ""
    period_to: str = ""
    manifest: dict = field(default_factory=dict)
    source_institutions: list[str] = field(default_factory=list)
    employees_add: list[dict] = field(default_factory=list)
    employees_update: list[tuple[str, dict, dict]] = field(default_factory=list)
    employees_unchanged: list[str] = field(default_factory=list)
    employees_skipped: list[dict] = field(default_factory=list)
    moves: list[dict] = field(default_factory=list)
    leaves_add: list[dict] = field(default_factory=list)
    leaves_update: list[tuple[int, dict, dict]] = field(default_factory=list)
    leaves_unchanged: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    overlaps: list[dict] = field(default_factory=list)
    attachments_add: list[dict] = field(default_factory=list)
    attachments_skipped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> MergeReport:
        return MergeReport(
            source_file=self.source_file,
            checksum=self.checksum,
            institution=self.institution,
            source_schema=self.source_schema,
            source_app_version=self.source_app_version,
            generated_at=self.generated_at,
            period_from=self.period_from,
            period_to=self.period_to,
            employees_added=len(self.employees_add),
            employees_updated=len(self.employees_update),
            employees_unchanged=len(self.employees_unchanged),
            employees_skipped=len(self.employees_skipped),
            leaves_added=len(self.leaves_add),
            leaves_updated=len(self.leaves_update),
            leaves_unchanged=len(self.leaves_unchanged),
            leaves_deleted_in_source=len(
                [lv for lv in self.leaves_add + [u[1] for u in self.leaves_update] if lv.get("deleted_at")]
            ),
            moves=len(self.moves),
            attachments_added=len(self.attachments_add),
            attachments_skipped=len(self.attachments_skipped),
            institutions_created=[],
            conflict_list=self.conflicts,
            move_list=self.moves,
            skipped_list=self.employees_skipped,
            overlap_list=self.overlaps,
            attachment_list=self.attachments_add,
            warnings=self.warnings,
            source_institutions=self.source_institutions,
        )


def _stamp(value) -> str:
    return str(value or "")


def _newer(source_stamp: str, target_stamp: str) -> bool:
    return _stamp(source_stamp) >= _stamp(target_stamp)


def _differs(source: dict, target: dict, fields: tuple[str, ...]) -> list[str]:
    changed = []
    for name in fields:
        left, right = source.get(name), target.get(name)
        if isinstance(left, bool) or isinstance(right, bool):
            left, right = int(bool(left)), int(bool(right))
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if float(left) != float(right):
                changed.append(name)
        elif _stamp(left) != _stamp(right):
            changed.append(name)
    return changed


def build_plan(target, source_path: Path, options: MergeOptions | None = None) -> MergePlan:
    """يبني خطة الدمج كاملة بلا أي كتابة في قاعدة الهدف."""
    options = options or MergeOptions()
    source_path = Path(source_path)
    plan = MergePlan(options=options, source_file=str(source_path), checksum=file_checksum(source_path))
    connection = _open_source(source_path, options.key_hex)
    try:
        tables = _tables(connection)
        if "employees" not in tables:
            raise ValueError("الملف لا يحتوي جدول الموظفين — ليس نسخة من هذا النظام.")
        plan.source_schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if "transfer_manifest" in tables:
            plan.manifest = {
                row[0]: row[1] for row in connection.execute("SELECT key, value FROM transfer_manifest")
            }
        plan.source_app_version = plan.manifest.get("app_version", "")
        plan.generated_at = plan.manifest.get("generated_at", "")
        plan.period_from = plan.manifest.get("period_from", "")
        plan.period_to = plan.manifest.get("period_to", "")
        source_employees = _rows(connection, "employees")
        source_leaves = _rows(connection, "leaves")
        source_attachments = _rows(connection, "attachments") if "attachments" in tables else []
    finally:
        connection.close()

    # المؤسسة المعلنة
    declared = options.institution or plan.manifest.get("institution", "")
    institutions = {str(row.get("institution") or "").strip() for row in source_employees + source_leaves}
    institutions.discard("")
    plan.source_institutions = sorted(institutions)
    if not declared:
        declared = next(iter(plan.source_institutions), "")
    plan.institution = declared

    # تحذيرات أولية
    if plan.source_schema and plan.source_schema < SCHEMA_VERSION:
        plan.warnings.append(
            f"الملف من إصدار مخطط أقدم ({plan.source_schema}) — ستُنقل البيانات المتاحة فقط، "
            "ويُستحسن تحديث نسخة المؤسسة إلى الإصدار الحالي."
        )
    if plan.source_schema > SCHEMA_VERSION:
        plan.warnings.append(f"الملف من إصدار أحدث ({plan.source_schema}) — حدّث نسخة المركز أولاً.")
    source_policy = plan.manifest.get("policy_fingerprint", "")
    if source_policy and source_policy != policy_fingerprint(target):
        plan.warnings.append(
            "ضوابط الاحتساب في الملف تختلف عن ضوابط المركز (معدل الاستحقاق/العطل/طريقة العد) — "
            "وحّد الضوابط في كل النسخ قبل الاعتماد على الأرصدة."
        )
    seen = target.checksum_seen(plan.checksum)
    if seen:
        plan.warnings.append(
            f"هذا الملف نفسه استُورد سابقاً ({seen.ts} بواسطة {seen.username}) — "
            "لن تتكرر البيانات، لكن راجع إن كان مقصوداً."
        )

    target_employees = target.raw_employees()
    target_leaves = target.raw_leaves()
    policy = target.policy(refresh=True)

    def opening_conflicts(emp_id: str, date_text: str) -> list[str]:
        cutoff = D.parse_iso(date_text)
        if not cutoff:
            return []
        found: list[str] = []
        for leave in target_leaves.values():
            if str(leave.get("emp_id") or "") != emp_id:
                continue
            if leave.get("deleted_at"):
                continue
            start = D.parse_iso(leave.get("start_date"))
            end = D.parse_iso(leave.get("end_date")) or start
            if not start:
                continue
            rule = policy.rule(str(leave.get("type") or ""))
            if (rule.consumes_balance or leave.get("is_adjustment")) and start <= cutoff:
                found.append(f"{leave.get('type')} {D.to_iso(start)}")
            elif rule.service_exclusion and start <= cutoff <= (end or start):
                found.append(f"{leave.get('type')} {D.to_iso(start)}")
        return found

    target_hashes = target.attachment_hashes()
    target_attachment_uids = {row["uid"] for row in target.raw_attachments() if row.get("uid")}
    today = date.today()
    file_date = plan.generated_at[:10] or str(today)

    # --- الموظفون -----------------------------------------------------
    for source in source_employees:
        emp_id = str(source.get("emp_id") or "").strip()
        if not emp_id:
            continue
        source_inst = str(source.get("institution") or "").strip()
        source_sec = str(source.get("secondment_to") or "").strip()
        if (
            declared
            and source_inst
            and source_inst != declared
            and source_sec != declared
            and not options.allow_other_institutions
        ):
            plan.employees_skipped.append(
                {"emp_id": emp_id, "name": source.get("name") or "", "reason": f"مؤسسة أخرى ({source_inst})"}
            )
            continue
        existing = target_employees.get(emp_id)
        if existing and source.get("opening_balance_set"):
            conflicts = opening_conflicts(emp_id, str(source.get("opening_balance_date") or ""))
            if conflicts:
                source = dict(source)
                for field_name in (
                    "opening_balance_set",
                    "opening_balance",
                    "opening_balance_date",
                    "opening_balance_by",
                    "opening_balance_note",
                    "opening_updated_at",
                    "opening_updated_by",
                ):
                    source[field_name] = existing.get(field_name)
                plan.conflicts.append(
                    {
                        "kind": "opening_balance",
                        "emp_id": emp_id,
                        "name": source.get("name") or "",
                        "fields": ["opening_balance_date"],
                        "winner": "المركز (رصيده الحالي)",
                        "detail": "الرصيد الافتتاحي الوارد يتعارض مع إجازات موجودة قبل تاريخه: "
                        + "، ".join(conflicts[:5]),
                    }
                )
        if not existing:
            record = dict(source)
            record.setdefault("uid", uuid.uuid4().hex)
            plan.employees_add.append(record)
            continue
        # نقل بين مؤسسات؟
        if source_inst and source_inst != str(existing.get("institution") or "").strip():
            moved_on = source.get("moved_on") or file_date
            plan.moves.append(
                {
                    "emp_id": emp_id,
                    "name": source.get("name") or (existing.get("name") or ""),
                    "from_institution": existing.get("institution") or "",
                    "to_institution": source_inst,
                    "moved_on": moved_on,
                    "source_file": source_path.name,
                    "note": "نُقل حسب ملف " + (declared or "المؤسسة"),
                }
            )
            updated = dict(existing)
            updated["institution"] = source_inst
            updated["previous_institution"] = existing.get("institution") or ""
            updated["moved_on"] = moved_on
            for name in EMPLOYEE_CONTENT:
                if name == "institution":
                    continue
                if _stamp(source.get(name)) and _stamp(source.get(name)) != _stamp(existing.get(name)):
                    updated[name] = source.get(name)
            updated["uid"] = existing.get("uid") or source.get("uid") or uuid.uuid4().hex
            plan.employees_update.append((emp_id, updated, dict(existing)))
            continue

        changed = _differs(source, existing, EMPLOYEE_CONTENT)
        source_deleted = bool(source.get("deleted_at"))
        target_deleted = bool(existing.get("deleted_at"))
        if source_deleted != target_deleted:
            changed.append("deleted_at")
        if not changed:
            plan.employees_unchanged.append(emp_id)
            continue
        source_wins = options.prefer == "source" or (
            options.prefer == "newest" and _newer(source.get("updated_at"), existing.get("updated_at"))
        )
        if options.prefer == "target":
            source_wins = False
        winner = source if source_wins else existing
        record = dict(existing)
        for name in EMPLOYEE_CONTENT + ("deleted_at", "deleted_by"):
            record[name] = winner.get(name)
        record["uid"] = existing.get("uid") or source.get("uid") or uuid.uuid4().hex
        plan.employees_update.append((emp_id, record, dict(existing)))
        if not source_wins:
            plan.conflicts.append(
                {
                    "kind": "employee",
                    "emp_id": emp_id,
                    "name": source.get("name") or "",
                    "fields": changed,
                    "winner": "المركز (أحدث)",
                    "detail": "بيانات الموظف تختلف، وبيانات المركز أحدث — أُبقيت بيانات المركز.",
                }
            )

    # --- الإجازات -----------------------------------------------------
    target_leaves_by_uid = target_leaves
    for source in source_leaves:
        emp_id = str(source.get("emp_id") or "").strip()
        if not emp_id:
            continue
        source_inst = str(source.get("institution") or "").strip()
        if declared and source_inst and source_inst != declared and not options.allow_other_institutions:
            continue  # تابعة لموظف مُتجاهل
        uid = str(source.get("uid") or "").strip()
        if not uid:
            uid = uuid.uuid4().hex
            source["uid"] = uid
        record = {name: source.get(name) for name in ALLOWED_LEAVE_FIELDS if name in source}
        record["emp_id"] = emp_id
        record["added_date"] = source.get("added_date") or ""
        record["uid"] = uid
        record["institution"] = source_inst or declared
        existing = target_leaves_by_uid.get(uid)
        if not existing:
            # احتمال تكرار قديم بلا uid: نفس النوع والتاريخ والأمر
            duplicate = _find_duplicate(target_leaves_by_uid, record)
            if duplicate:
                plan.leaves_unchanged.append(uid)
                plan.conflicts.append(
                    {
                        "kind": "duplicate_leave",
                        "emp_id": emp_id,
                        "name": "",
                        "fields": ["uid"],
                        "winner": "المركز (موجودة مسبقاً)",
                        "detail": f"إجازة {record.get('type')} بتاريخ {record.get('start_date')} "
                        "موجودة في المركز بمعرّف مختلف — لم تُكرَّر.",
                    }
                )
                continue
            plan.leaves_add.append(record)
            continue
        changed = _differs(record, existing, LEAVE_CONTENT)
        if str(existing.get("deleted_at") or "") != str(record.get("deleted_at") or ""):
            changed.append("deleted_at")
        if not changed:
            plan.leaves_unchanged.append(uid)
            continue
        source_stamp = source.get("modified_at") or source.get("added_date")
        target_stamp = existing.get("modified_at") or existing.get("added_date")
        source_wins = options.prefer == "source" or (
            options.prefer == "newest" and _newer(source_stamp, target_stamp)
        )
        if options.prefer == "target":
            source_wins = False
        if source_wins:
            plan.leaves_update.append((int(existing["id"]), record, dict(existing)))
            if record.get("deleted_at") and not existing.get("deleted_at"):
                plan.conflicts.append(
                    {
                        "kind": "soft_delete",
                        "emp_id": emp_id,
                        "name": "",
                        "fields": ["deleted_at"],
                        "winner": "المؤسسة (حذف ناعم)",
                        "detail": f"إجازة {record.get('type')} بتاريخ {record.get('start_date')} "
                        "حُذفت في ملف المؤسسة → طُبِّق الحذف في المركز.",
                    }
                )
        else:
            plan.leaves_unchanged.append(uid)
            plan.conflicts.append(
                {
                    "kind": "leave",
                    "emp_id": emp_id,
                    "name": "",
                    "fields": changed,
                    "winner": "المركز (أحدث)",
                    "detail": f"إجازة {record.get('type')} بتاريخ {record.get('start_date')} "
                    "تختلف، ونسخة المركز أحدث — أُبقيت نسخة المركز.",
                }
            )

    # --- التقاطعات الزمنية ------------------------------------------
    plan.overlaps = _find_overlaps(plan, target_leaves_by_uid)

    # --- المرفقات -----------------------------------------------------
    if options.transfer_attachments:
        for row in source_attachments:
            uid = str(row.get("uid") or "")
            if uid and uid in target_attachment_uids:
                plan.attachments_skipped.append(row)
                continue
            sha = str(row.get("sha256") or "")
            if sha and sha in target_hashes:
                plan.attachments_skipped.append(row)
                continue
            plan.attachments_add.append(row)
    return plan


def _find_duplicate(target_leaves: dict[str, dict], record: dict) -> dict | None:
    """يكشف إجازة مكافئة موجودة بمعرّف مختلف (نسخ قديمة بلا uid)."""
    for existing in target_leaves.values():
        if (
            str(existing.get("emp_id")) == str(record.get("emp_id"))
            and str(existing.get("type")) == str(record.get("type"))
            and str(existing.get("start_date")) == str(record.get("start_date"))
            and str(existing.get("order_num") or "") == str(record.get("order_num") or "")
            and int(existing.get("days_actual") or 0) == int(record.get("days_actual") or 0)
        ):
            return existing
    return None


def _find_overlaps(plan: MergePlan, target_leaves: dict[str, dict]) -> list[dict]:
    """إجازات جديدة تتقاطع زمنياً مع إجازات موجودة لنفس الموظف (تنبيه للمراجعة)."""
    existing_by_emp: dict[str, list[dict]] = {}
    for row in target_leaves.values():
        if row.get("deleted_at"):
            continue
        existing_by_emp.setdefault(str(row.get("emp_id")), []).append(row)
    overlaps: list[dict] = []
    for record in plan.leaves_add:
        emp_id = str(record.get("emp_id"))
        start = D.parse_iso(record.get("start_date"))
        end = D.parse_iso(record.get("end_date")) or start
        if not start:
            continue
        for other in existing_by_emp.get(emp_id, []):
            other_start = D.parse_iso(other.get("start_date"))
            other_end = D.parse_iso(other.get("end_date")) or other_start
            if D.overlaps(start, end, other_start, other_end):
                overlaps.append(
                    {
                        "emp_id": emp_id,
                        "new_type": record.get("type"),
                        "new_start": record.get("start_date"),
                        "new_end": record.get("end_date"),
                        "existing_type": other.get("type"),
                        "existing_start": other.get("start_date"),
                        "existing_end": other.get("end_date"),
                    }
                )
                break
    return overlaps


# ---------------------------------------------------------------------------
# التنفيذ
# ---------------------------------------------------------------------------
def execute_plan(
    target, plan: MergePlan, *, user: str = "", attachments_dir: Path | None = None
) -> MergeReport:
    """ينفّذ الخطة في معاملة واحدة (كل شيء أو لا شيء)."""
    report = plan.report()
    attachments_dir = Path(attachments_dir) if attachments_dir else target.path.parent / "attachments"
    source_attachments_dir = None
    if plan.options.source_attachments_dir:
        source_attachments_dir = Path(plan.options.source_attachments_dir)
    elif plan.source_file:
        candidate = Path(plan.source_file).parent / "attachments"
        source_attachments_dir = candidate if candidate.exists() else None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with target.transaction() as c:
        # --- المؤسسات -------------------------------------------------
        names = set(plan.source_institutions)
        if plan.institution:
            names.add(plan.institution)
        names.update(str(record.get("institution") or "") for record in plan.employees_add)
        for name in sorted(names):
            name = name.strip()
            if not name:
                continue
            row = c.execute("SELECT 1 FROM institutions WHERE name=?", (name,)).fetchone()
            if not row:
                c.execute(
                    """INSERT INTO institutions(name, kind, created_at, updated_at)
                             VALUES (?,?,?,?)""",
                    (name, "مؤسسة", now, now),
                )
                report.institutions_created.append(name)

        # --- الموظفون -------------------------------------------------
        for record in plan.employees_add:
            columns = [
                "emp_id",
                "name",
                "job_title",
                "workplace",
                "institution",
                "gender",
                "start_date",
                "end_date",
                "notes",
                "status",
                "created_at",
                "updated_at",
                "deleted_at",
                "deleted_by",
                "uid",
                "previous_institution",
                "moved_on",
                "opening_balance_set",
                "opening_balance",
                "opening_balance_date",
                "opening_balance_by",
                "opening_balance_note",
                "opening_updated_at",
                "opening_updated_by",
                "secondment_to",
                "secondment_start",
                "secondment_end",
                "secondment_order",
            ]
            c.execute(
                f"INSERT INTO employees ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
                [_employee_value(record, column, now) for column in columns],
            )
        for emp_id, record, _old in plan.employees_update:
            columns = [
                "name",
                "job_title",
                "workplace",
                "institution",
                "gender",
                "start_date",
                "end_date",
                "notes",
                "status",
                "updated_at",
                "deleted_at",
                "deleted_by",
                "uid",
                "previous_institution",
                "moved_on",
                "opening_balance_set",
                "opening_balance",
                "opening_balance_date",
                "opening_balance_by",
                "opening_balance_note",
                "opening_updated_at",
                "opening_updated_by",
                "secondment_to",
                "secondment_start",
                "secondment_end",
                "secondment_order",
            ]
            c.execute(
                f"UPDATE employees SET {','.join(f'{column}=?' for column in columns)} WHERE emp_id=?",
                [_employee_value(record, column, now) for column in columns] + [emp_id],
            )
        for move in plan.moves:
            c.execute(
                """INSERT INTO employee_moves
                         (emp_id, from_institution, to_institution, moved_on, recorded_at,
                          source_file, note) VALUES (?,?,?,?,?,?,?)""",
                (
                    move["emp_id"],
                    move["from_institution"],
                    move["to_institution"],
                    move["moved_on"],
                    now,
                    move["source_file"],
                    move["note"],
                ),
            )

        # --- الإجازات -------------------------------------------------
        for record in plan.leaves_add:
            columns = ["emp_id"] + list(ALLOWED_LEAVE_FIELDS) + ["added_date"]
            c.execute(
                f"INSERT INTO leaves ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
                [_leave_value(record, column, now) for column in columns],
            )
        for leave_id, record, _old in plan.leaves_update:
            columns = list(ALLOWED_LEAVE_FIELDS)
            c.execute(
                f"UPDATE leaves SET {','.join(f'{column}=?' for column in columns)} WHERE id=?",
                [_leave_value(record, column, now) for column in columns] + [leave_id],
            )

        # --- المرفقات -------------------------------------------------
        for row in plan.attachments_add:
            stored = _copy_attachment(row, source_attachments_dir, attachments_dir)
            if stored is None:
                report.warnings.append(f"لم يُعثر على ملف المرفق «{row.get('filename')}» — نُقل السجل بلا ملف.")
                stored_name, sha = str(row.get("stored_name") or ""), str(row.get("sha256") or "")
            else:
                stored_name, sha = stored
            leave_uid = str(row.get("leave_uid") or "")
            leave_row = c.execute("SELECT id FROM leaves WHERE uid=?", (leave_uid,)).fetchone()
            target.add_attachment_row(
                c,
                leave_id=leave_row[0] if leave_row else None,
                emp_id=str(row.get("emp_id") or ""),
                filename=str(row.get("filename") or ""),
                stored_name=stored_name,
                sha256=sha,
                leave_uid=leave_uid,
                institution=str(row.get("institution") or plan.institution),
                uid=str(row.get("uid") or uuid.uuid4().hex),
                user=user,
            )

        # --- تسجيل العملية --------------------------------------------
        c.execute(
            """UPDATE institutions SET last_import_at=?, last_import_user=?,
                     last_import_file=?, last_import_counts=? WHERE name=?""",
            (
                now,
                user,
                Path(plan.source_file).name,
                json.dumps(
                    {
                        "employees_added": report.employees_added,
                        "employees_updated": report.employees_updated,
                        "leaves_added": report.leaves_added,
                        "leaves_updated": report.leaves_updated,
                        "conflicts": report.conflicts,
                    },
                    ensure_ascii=False,
                ),
                plan.institution,
            ),
        )

    record_id = target.add_import(
        {
            "ts": now,
            "username": user or "—",
            "direction": "import",
            "scope": plan.institution or "غير محددة",
            "institution": plan.institution,
            "source_file": Path(plan.source_file).name,
            "checksum": plan.checksum,
            "source_schema": plan.source_schema,
            "source_policy": plan.manifest.get("policy_fingerprint", ""),
            "period_from": plan.period_from,
            "period_to": plan.period_to,
            "employees_added": report.employees_added,
            "employees_updated": report.employees_updated,
            "employees_unchanged": report.employees_unchanged,
            "employees_conflict": report.conflicts,
            "leaves_added": report.leaves_added,
            "leaves_updated": report.leaves_updated,
            "leaves_unchanged": report.leaves_unchanged,
            "moves": report.moves,
            "attachments": report.attachments_added,
            "warnings": len(report.warnings),
            "report": report.to_json(),
        },
        user,
    )
    LOG.info(
        "اكتمل الدمج #%s من %s: %s موظفاً، %s إجازة، %s انتقال",
        record_id,
        plan.institution,
        report.employees_added,
        report.leaves_added,
        report.moves,
    )
    target.log(
        user,
        "استيراد",
        "database",
        Path(plan.source_file).name,
        f"مؤسسة {plan.institution}: +{report.employees_added} موظف، "
        f"+{report.leaves_added} إجازة، {report.moves} انتقال",
    )
    return report


def _employee_value(record: dict, column: str, now: str):
    """قيمة عمود موظف مع النوع الصحيح (لا نصوص في أعمدة نصية/زمنية)."""
    if column == "emp_id":
        return str(record.get("emp_id") or "")
    if column == "opening_updated_at":
        return record.get(column) or ""
    if column in EMPLOYEE_TIMESTAMPS:
        return record.get(column) or now
    value = record.get(column)
    if value is None:
        return ""
    if column in {"is_center", "active"}:
        return int(bool(value))
    return value


def _leave_value(record: dict, column: str, now: str):
    """قيمة عمود إجازة مع النوع الصحيح."""
    if column == "emp_id":
        return str(record.get("emp_id") or "")
    if column in LEAVE_TIMESTAMPS:
        return record.get(column) or now
    value = record.get(column)
    if column in LEAVE_NUMERIC:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    if value is None:
        return ""
    return value


def _copy_attachment(row: dict, source_dir: Path | None, target_dir: Path) -> tuple[str, str] | None:
    """ينسخ ملف المرفق إلى مجلد مرفقات الهدف ويعيد (الاسم المخزّن، بصمة sha256)."""
    stored_name = str(row.get("stored_name") or "")
    if not stored_name or source_dir is None:
        return None
    source_file = Path(source_dir) / stored_name
    if not source_file.exists():
        return None
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    digest = file_sha256(source_file)
    if str(row.get("sha256") or "") and str(row.get("sha256")) != digest:
        LOG.warning("بصمة المرفق %s لا تطابق المحتوى", row.get("filename"))
    suffix = source_file.suffix.lower()
    new_name = f"{uuid.uuid4().hex}{suffix}"
    shutil.copy2(source_file, target_dir / new_name)
    return new_name, digest


# ---------------------------------------------------------------------------
# واجهات مبسّطة
# ---------------------------------------------------------------------------
def preview(target, source_path: Path, options: MergeOptions | None = None) -> tuple[MergePlan, MergeReport]:
    plan = build_plan(target, source_path, options)
    return plan, plan.report()


def merge(
    target,
    source_path: Path,
    options: MergeOptions | None = None,
    *,
    user: str = "",
    attachments_dir: Path | None = None,
) -> MergeReport:
    plan = build_plan(target, source_path, options)
    return execute_plan(target, plan, user=user, attachments_dir=attachments_dir)


# ---------------------------------------------------------------------------
# تصدير التقرير
# ---------------------------------------------------------------------------
def report_rows(report: MergeReport) -> tuple[list[str], list[list]]:
    """صفوف ملخّص التقرير (للعرض أو التصدير إلى Excel)."""
    headers = ["البند", "القيمة"]
    rows = [
        ["الملف المستورد", Path(report.source_file).name],
        ["بصمة الملف (sha256)", report.checksum],
        ["المؤسسة", report.institution or "غير محددة"],
        ["إصدار مخطط الملف", str(report.source_schema or "—")],
        ["إصدار البرنامج في الملف", report.source_app_version or "—"],
        ["وقت إنشاء الملف", report.generated_at or "—"],
        ["الفترة المشمولة", f"{report.period_from or '—'} → {report.period_to or '—'}"],
        ["موظفون أُضيفوا", report.employees_added],
        ["موظفون حُدِّثوا", report.employees_updated],
        ["موظفون بلا تغيير", report.employees_unchanged],
        ["موظفون تُجوهلوا", report.employees_skipped],
        ["إجازات أُضيفت", report.leaves_added],
        ["إجازات حُدِّثت", report.leaves_updated],
        ["إجازات بلا تغيير", report.leaves_unchanged],
        ["حذف ناعم نُقل", report.leaves_deleted_in_source],
        ["انتقالات مؤسسات", report.moves],
        ["مرفقات نُقلت", report.attachments_added],
        ["مرفقات موجودة مسبقاً", report.attachments_skipped],
        ["تعارضات", report.conflicts],
        ["تقاطعات زمنية", len(report.overlap_list)],
        ["مؤسسات أُنشئت", "، ".join(report.institutions_created) or "—"],
        ["تحذيرات", " | ".join(report.warnings) or "—"],
    ]
    return headers, rows


def conflict_rows(report: MergeReport) -> tuple[list[str], list[list]]:
    headers = ["النوع", "الرقم الوظيفي", "التفصيل", "الذي اعتُمد"]
    rows = []
    for item in report.conflict_list:
        kind = {
            "employee": "بيانات موظف",
            "leave": "بيانات إجازة",
            "soft_delete": "حذف ناعم",
            "duplicate_leave": "تكرار إجازة",
        }.get(str(item.get("kind")), str(item.get("kind") or ""))
        detail = item.get("detail") or ""
        fields = item.get("fields") or []
        if fields and not detail:
            detail = "حقول مختلفة: " + "، ".join(str(field) for field in fields)
        rows.append([kind, item.get("emp_id", ""), detail, item.get("winner", "")])
    return headers, rows


def move_rows(report: MergeReport) -> tuple[list[str], list[list]]:
    headers = ["الرقم الوظيفي", "الاسم", "من مؤسسة", "إلى مؤسسة", "تاريخ النقل", "الملف"]
    rows = [
        [
            item.get("emp_id", ""),
            item.get("name", ""),
            item.get("from_institution", ""),
            item.get("to_institution", ""),
            item.get("moved_on", ""),
            item.get("source_file", ""),
        ]
        for item in report.move_list
    ]
    return headers, rows


def overlap_rows(report: MergeReport) -> tuple[list[str], list[list]]:
    headers = ["الرقم الوظيفي", "إجازة واردة", "من", "إلى", "تتقاطع مع", "من", "إلى"]
    rows = [
        [
            item.get("emp_id", ""),
            item.get("new_type", ""),
            item.get("new_start", ""),
            item.get("new_end", ""),
            item.get("existing_type", ""),
            item.get("existing_start", ""),
            item.get("existing_end", ""),
        ]
        for item in report.overlap_list
    ]
    return headers, rows


def export_report_excel(path: str | Path, report: MergeReport) -> Path:
    """يصدّر تقرير الاستيراد إلى Excel بأوراق: الملخص، التعارضات، الانتقالات، التقاطعات."""
    path = Path(path)
    from ..exporters import excel as X

    if not X.HAS_XLSX:
        raise RuntimeError("مكتبة openpyxl غير مثبتة.")
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = openpyxl.Workbook()
    sheets = [
        ("الملخص", report_rows(report), [34, 60]),
        ("التعارضات", conflict_rows(report), [16, 16, 70, 22]),
        ("الانتقالات", move_rows(report), [16, 26, 22, 22, 16, 26]),
        ("التقاطعات", overlap_rows(report), [16, 16, 14, 14, 16, 14, 14]),
        (
            "المتجاهلون",
            (
                ["الرقم الوظيفي", "الاسم", "السبب"],
                [
                    [item.get("emp_id", ""), item.get("name", ""), item.get("reason", "")]
                    for item in report.skipped_list
                ],
            ),
            [16, 26, 40],
        ),
    ]
    first = True
    for title, (headers, rows), widths in sheets:
        sheet = workbook.active if first else workbook.create_sheet()
        sheet.title = title
        sheet.sheet_view.rightToLeft = True
        sheet.append(headers)
        for row in rows:
            sheet.append(list(row))
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="7DD3C8")
            cell.fill = PatternFill("solid", fgColor="1C2D3E")
            cell.alignment = Alignment(horizontal="center")
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        sheet.freeze_panes = "A2"
        first = False
    workbook.save(path)
    return path
