"""نماذج البيانات (dataclasses) المستخدمة في كل الطبقات."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .services.dates import parse_iso


# ---------------------------------------------------------------------------
# الموظف
# ---------------------------------------------------------------------------
@dataclass
class Employee:
    emp_id: str
    name: str = ""
    job_title: str = ""
    workplace: str = ""
    institution: str = ""
    gender: str = "ذكر"
    start_date: date | None = None
    end_date: date | None = None
    notes: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    deleted_at: str = ""
    deleted_by: str = ""
    uid: str = ""
    previous_institution: str = ""
    moved_on: date | None = None
    # الرصيد الافتتاحي: المتبقي كما في تاريخ الاحتساب اليدوي
    opening_balance_set: bool = False
    opening_balance: int = 0
    opening_balance_date: date | None = None
    opening_balance_by: str = ""
    opening_balance_note: str = ""
    opening_updated_at: str = ""
    opening_updated_by: str = ""
    leaves: list[Leave] = field(default_factory=list)

    # -- تحويل -------------------------------------------------------------
    @classmethod
    def from_mapping(cls, m) -> Employee:
        return cls(
            emp_id=str(m["emp_id"]),
            name=m.get("name") or "",
            job_title=m.get("job_title") or "",
            workplace=m.get("workplace") or "",
            institution=m.get("institution") or "",
            gender=m.get("gender") or "ذكر",
            start_date=parse_iso(m.get("start_date")),
            end_date=parse_iso(m.get("end_date")),
            notes=m.get("notes") or "",
            status=m.get("status") or "active",
            created_at=m.get("created_at") or "",
            updated_at=m.get("updated_at") or "",
            deleted_at=m.get("deleted_at") or "",
            deleted_by=m.get("deleted_by") or "",
            uid=m.get("uid") or "",
            previous_institution=m.get("previous_institution") or "",
            moved_on=parse_iso(m.get("moved_on")),
            opening_balance_set=bool(m.get("opening_balance_set")),
            opening_balance=int(m.get("opening_balance") or 0),
            opening_balance_date=parse_iso(m.get("opening_balance_date")),
            opening_balance_by=m.get("opening_balance_by") or "",
            opening_balance_note=m.get("opening_balance_note") or "",
            opening_updated_at=m.get("opening_updated_at") or "",
            opening_updated_by=m.get("opening_updated_by") or "",
        )

    def to_fields(self) -> dict:
        return {
            "name": self.name,
            "job_title": self.job_title,
            "workplace": self.workplace,
            "institution": self.institution,
            "gender": self.gender,
            "start_date": self.start_date.strftime("%Y-%m-%d") if self.start_date else "",
            "end_date": self.end_date.strftime("%Y-%m-%d") if self.end_date else "",
            "notes": self.notes,
            "status": self.status,
            "previous_institution": self.previous_institution,
            "moved_on": self.moved_on.strftime("%Y-%m-%d") if self.moved_on else "",
            "opening_balance_set": int(bool(self.opening_balance_set)),
            "opening_balance": int(self.opening_balance or 0),
            "opening_balance_date": (
                self.opening_balance_date.strftime("%Y-%m-%d") if self.opening_balance_date else ""
            ),
            "opening_balance_by": self.opening_balance_by,
            "opening_balance_note": self.opening_balance_note,
            "opening_updated_at": self.opening_updated_at,
            "opening_updated_by": self.opening_updated_by,
        }

    @property
    def is_deleted(self) -> bool:
        return bool(self.deleted_at)

    @property
    def has_opening_balance(self) -> bool:
        return bool(self.opening_balance_set and self.opening_balance_date)

    @property
    def label(self) -> str:
        return f"{self.name} ({self.emp_id})" if self.name else self.emp_id


# ---------------------------------------------------------------------------
# الإجازة
# ---------------------------------------------------------------------------
@dataclass
class Leave:
    id: int | None = None
    emp_id: str = ""
    type: str = ""
    start_date: date | None = None
    end_date: date | None = None
    amount: int = 0
    unit: str = "يوم"
    days_actual: int = 0
    working_days: int = 0
    count_mode: str = "calendar"
    order: str = ""
    order_date: date | None = None
    outside_balance: bool = False
    reason: str = ""
    added_date: str = ""
    status: str = "approved"
    approved_by: str = ""
    approved_at: str = ""
    created_by: str = ""
    modified_at: str = ""
    modified_by: str = ""
    deleted_at: str = ""
    deleted_by: str = ""
    is_adjustment: bool = False
    manual_days: bool = False
    uid: str = ""
    institution: str = ""

    @classmethod
    def from_mapping(cls, m) -> Leave:
        return cls(
            id=m.get("id"),
            emp_id=str(m.get("emp_id") or ""),
            type=m.get("type") or "",
            start_date=parse_iso(m.get("start_date") or m.get("from_date")),
            end_date=parse_iso(m.get("end_date")),
            amount=int(m.get("amount") or 0),
            unit=m.get("unit") or "يوم",
            days_actual=int(m.get("days_actual") or 0),
            working_days=int(m.get("working_days") or 0),
            count_mode=m.get("count_mode") or "calendar",
            order=m.get("order") or m.get("order_num") or "",
            order_date=parse_iso(m.get("order_date")),
            outside_balance=bool(m.get("outside_balance")),
            reason=m.get("reason") or "",
            added_date=m.get("added_date") or "",
            status=m.get("status") or "approved",
            approved_by=m.get("approved_by") or "",
            approved_at=m.get("approved_at") or "",
            created_by=m.get("created_by") or "",
            modified_at=m.get("modified_at") or "",
            modified_by=m.get("modified_by") or "",
            deleted_at=m.get("deleted_at") or "",
            deleted_by=m.get("deleted_by") or "",
            is_adjustment=bool(m.get("is_adjustment")),
            manual_days=bool(m.get("manual_days")),
            uid=m.get("uid") or "",
            institution=m.get("institution") or "",
        )

    def to_fields(self) -> dict:
        return {
            "type": self.type,
            "start_date": self.start_date.strftime("%Y-%m-%d") if self.start_date else "",
            "end_date": self.end_date.strftime("%Y-%m-%d") if self.end_date else "",
            "from_date": self.start_date.strftime("%Y-%m-%d") if self.start_date else "",
            "amount": self.amount,
            "unit": self.unit,
            "days_actual": self.days_actual,
            "working_days": self.working_days,
            "count_mode": self.count_mode,
            "order": self.order,
            "order_date": self.order_date.strftime("%Y-%m-%d") if self.order_date else "",
            "outside_balance": int(self.outside_balance),
            "reason": self.reason,
            "added_date": self.added_date,
            "status": self.status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "is_adjustment": int(self.is_adjustment),
            "manual_days": int(self.manual_days),
            "uid": self.uid,
            "institution": self.institution,
        }

    @property
    def is_deleted(self) -> bool:
        return bool(self.deleted_at)

    @property
    def effective_days(self) -> int:
        """الأيام المؤثرة في الحساب (موجبة أو سالبة للتسويات)."""
        return int(self.days_actual or 0)


# ---------------------------------------------------------------------------
# الرصيد
# ---------------------------------------------------------------------------
@dataclass
class Balance:
    raw_days: int = 0  # أيام الخدمة الكلية
    outside: int = 0  # أيام مستبعدة من الخدمة
    net_days: int = 0  # أيام الدوام المحسوبة
    earned: int = 0  # الإجازات المستحقة بعد تاريخ الافتتاحي
    taken: int = 0  # المأخوذة بعد تاريخ الافتتاحي
    balance: int = 0  # الرصيد (قد يكون سالباً وهو مشروع)
    opening_balance: int = 0  # الرصيد الافتتاحي (المتبقي كما في تاريخه)
    opening_date: date | None = None
    earned_after: int = 0
    taken_after: int = 0
    service_days_after: int = 0
    net_days_after: int = 0
    has_opening: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def is_negative(self) -> bool:
        return self.balance < 0


@dataclass
class YearLine:
    index: int
    start: date | None
    end: date | None
    service_days: int = 0
    outside_days: int = 0
    net_days: int = 0
    earned: int = 0
    taken: int = 0
    expired: int = 0
    carry_in: int = 0
    carry_out: int = 0
    is_current: bool = False


@dataclass
class Statement:
    employee: Employee
    balance: Balance
    lines: list[YearLine] = field(default_factory=list)
    policy_note: str = ""
    opening_balance: int = 0
    opening_date: date | None = None
    opening_by: str = ""
    opening_note: str = ""


@dataclass
class Settlement:
    employee: Employee
    balance_days: int = 0
    service_days: int = 0
    earned: int = 0
    taken: int = 0
    day_value: float | None = None
    amount: float | None = None


# ---------------------------------------------------------------------------
# المستخدمون والتدقيق والمرفقات والعطل
# ---------------------------------------------------------------------------
@dataclass
class AppUser:
    username: str
    display_name: str = ""
    role: str = "viewer"
    institution: str = ""
    password_hash: str = ""
    salt: str = ""
    iterations: int = 200_000
    active: bool = True
    created_at: str = ""
    last_login: str = ""

    @classmethod
    def from_mapping(cls, m) -> AppUser:
        return cls(
            username=str(m.get("username") or ""),
            display_name=m.get("display_name") or "",
            role=m.get("role") or "viewer",
            institution=m.get("institution") or "",
            password_hash=m.get("password_hash") or "",
            salt=m.get("salt") or "",
            iterations=int(m.get("iterations") or 200_000),
            active=bool(m.get("active", 1)),
            created_at=m.get("created_at") or "",
            last_login=m.get("last_login") or "",
        )


@dataclass
class Attachment:
    id: int | None = None
    leave_id: int | None = None
    emp_id: str = ""
    filename: str = ""
    stored_name: str = ""
    added_at: str = ""
    added_by: str = ""
    uid: str = ""
    leave_uid: str = ""
    sha256: str = ""
    institution: str = ""

    @classmethod
    def from_mapping(cls, m) -> Attachment:
        return cls(
            id=m.get("id"),
            leave_id=m.get("leave_id"),
            emp_id=str(m.get("emp_id") or ""),
            filename=m.get("filename") or "",
            stored_name=m.get("stored_name") or "",
            added_at=m.get("added_at") or "",
            added_by=m.get("added_by") or "",
            uid=m.get("uid") or "",
            leave_uid=m.get("leave_uid") or "",
            sha256=m.get("sha256") or "",
            institution=m.get("institution") or "",
        )


@dataclass
class Institution:
    name: str
    code: str = ""
    kind: str = "مستشفى"
    manager: str = ""
    phone: str = ""
    address: str = ""
    notes: str = ""
    is_center: bool = False
    username: str = ""
    active: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_import_at: str = ""
    last_export_at: str = ""
    last_import_user: str = ""
    last_import_file: str = ""
    last_import_counts: str = ""
    employees: int = 0

    @classmethod
    def from_mapping(cls, m) -> Institution:
        return cls(
            name=str(m.get("name") or ""),
            code=m.get("code") or "",
            kind=m.get("kind") or "مستشفى",
            manager=m.get("manager") or "",
            phone=m.get("phone") or "",
            address=m.get("address") or "",
            notes=m.get("notes") or "",
            is_center=bool(m.get("is_center")),
            username=m.get("username") or "",
            active=bool(m.get("active", 1)),
            created_at=m.get("created_at") or "",
            updated_at=m.get("updated_at") or "",
            last_import_at=m.get("last_import_at") or "",
            last_export_at=m.get("last_export_at") or "",
            last_import_user=m.get("last_import_user") or "",
            last_import_file=m.get("last_import_file") or "",
            last_import_counts=m.get("last_import_counts") or "",
            employees=int(m.get("employees") or 0),
        )

    def to_fields(self) -> dict:
        return {
            "name": self.name,
            "code": self.code,
            "kind": self.kind,
            "manager": self.manager,
            "phone": self.phone,
            "address": self.address,
            "notes": self.notes,
            "is_center": int(self.is_center),
            "username": self.username,
            "active": int(self.active),
        }


@dataclass
class EmployeeMove:
    id: int | None = None
    emp_id: str = ""
    from_institution: str = ""
    to_institution: str = ""
    moved_on: date | None = None
    recorded_at: str = ""
    source_file: str = ""
    note: str = ""

    @classmethod
    def from_mapping(cls, m) -> EmployeeMove:
        return cls(
            id=m.get("id"),
            emp_id=str(m.get("emp_id") or ""),
            from_institution=m.get("from_institution") or "",
            to_institution=m.get("to_institution") or "",
            moved_on=parse_iso(m.get("moved_on")),
            recorded_at=m.get("recorded_at") or "",
            source_file=m.get("source_file") or "",
            note=m.get("note") or "",
        )


@dataclass
class ImportRecord:
    id: int | None = None
    ts: str = ""
    username: str = ""
    direction: str = "import"
    scope: str = ""
    institution: str = ""
    source_file: str = ""
    checksum: str = ""
    source_schema: int = 0
    source_policy: str = ""
    period_from: str = ""
    period_to: str = ""
    employees_added: int = 0
    employees_updated: int = 0
    employees_unchanged: int = 0
    employees_conflict: int = 0
    leaves_added: int = 0
    leaves_updated: int = 0
    leaves_unchanged: int = 0
    moves: int = 0
    attachments: int = 0
    warnings: int = 0
    report: str = ""

    @classmethod
    def from_mapping(cls, m) -> ImportRecord:
        record = cls()
        for field_name in cls.__dataclass_fields__:  # type: ignore[attr-defined]
            if field_name in m and m[field_name] is not None:
                setattr(record, field_name, m[field_name])
        return record


@dataclass
class Holiday:
    id: int | None = None
    day: date | None = None
    name: str = ""
    recurring: bool = False


@dataclass
class AuditEntry:
    id: int | None = None
    ts: str = ""
    username: str = ""
    action: str = ""
    entity: str = ""
    entity_id: str = ""
    details: str = ""


@dataclass
class Issue:
    """نتيجة تحقق: level = error (يمنع) أو warning (لا يمنع) أو info."""

    level: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.level == "error"
