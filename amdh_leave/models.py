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
    leaves: list["Leave"] = field(default_factory=list)

    # -- تحويل -------------------------------------------------------------
    @classmethod
    def from_mapping(cls, m) -> "Employee":
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
        }

    @property
    def is_deleted(self) -> bool:
        return bool(self.deleted_at)

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

    @classmethod
    def from_mapping(cls, m) -> "Leave":
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
    raw_days: int = 0        # أيام الخدمة الكلية
    outside: int = 0         # أيام مستبعدة من الخدمة
    net_days: int = 0        # أيام الدوام المحسوبة
    earned: int = 0          # الإجازات المستحقة
    taken: int = 0           # المأخوذة
    balance: int = 0         # الرصيد (قد يكون سالباً وهو مشروع)
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
    def from_mapping(cls, m) -> "AppUser":
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


@dataclass
class Holiday:
    id: int | None = None
    day: date | None = None
    name: str = ""


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
