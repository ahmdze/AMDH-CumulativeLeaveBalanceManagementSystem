"""ضوابط أنواع الإجازات وسياسة الاحتساب (قابلة للتعديل من الواجهة)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from . import config


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "نعم", "on"}


def _as_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# قاعدة نوع الإجازة
# ---------------------------------------------------------------------------
@dataclass
class LeaveRule:
    type: str
    consumes_balance: bool = True  # يُخصم من الرصيد السنوي
    service_exclusion: bool = False  # يُستبعد من أيام الخدمة (مثل إجازة 5 سنوات)
    count_mode: str = "calendar"  # calendar | working
    quota_days: int = 0  # 0 = بلا سقف
    quota_period: str = "none"  # none | year | service
    requires_order: bool = False
    is_adjustment: bool = False
    gender: str = ""  # "" = للجميع
    order_index: int = 0
    active: bool = True
    notes: str = ""

    @classmethod
    def from_mapping(cls, m) -> LeaveRule:
        return cls(
            type=str(m.get("type") or ""),
            consumes_balance=_as_bool(m.get("consumes_balance"), True),
            service_exclusion=_as_bool(m.get("service_exclusion"), False),
            count_mode=(m.get("count_mode") or "calendar"),
            quota_days=_as_int(m.get("quota_days"), 0),
            quota_period=(m.get("quota_period") or "none"),
            requires_order=_as_bool(m.get("requires_order"), False),
            is_adjustment=_as_bool(m.get("is_adjustment"), False),
            gender=(m.get("gender") or ""),
            order_index=_as_int(m.get("order_index"), 0),
            active=_as_bool(m.get("active"), True),
            notes=m.get("notes") or "",
        )

    def to_mapping(self) -> dict:
        return {
            "type": self.type,
            "consumes_balance": int(self.consumes_balance),
            "service_exclusion": int(self.service_exclusion),
            "count_mode": self.count_mode,
            "quota_days": self.quota_days,
            "quota_period": self.quota_period,
            "requires_order": int(self.requires_order),
            "is_adjustment": int(self.is_adjustment),
            "gender": self.gender,
            "order_index": self.order_index,
            "active": int(self.active),
            "notes": self.notes,
        }

    @property
    def count_mode_label(self) -> str:
        return config.COUNT_MODE_LABELS.get(self.count_mode, self.count_mode)

    @property
    def quota_label(self) -> str:
        if not self.quota_days:
            return "بلا سقف"
        return f"{self.quota_days} يوم {config.QUOTA_PERIOD_LABELS.get(self.quota_period, '')}".strip()


def default_rules() -> dict[str, LeaveRule]:
    return {r["type"]: LeaveRule.from_mapping(r) for r in config.DEFAULT_RULES}


_FALLBACK_RULE = LeaveRule(type="غير محددة")


# ---------------------------------------------------------------------------
# السياسة العامة
# ---------------------------------------------------------------------------
@dataclass
class Policy:
    days_per_leave: int = config.DAYS_PER_LEAVE
    max_annual: int = config.MAX_ANNUAL
    enforce_annual_cap: bool = False  # لا يُفرض السقف إلا بتفعيل صريح
    basis: str = config.BASIS_CONTINUOUS
    expiry_years: int = 0
    carryover_cap: int = 0
    allow_negative_balance: bool = True
    warn_negative_balance: bool = False
    warn_leaving_soon_days: int = 5
    low_balance_days: int = 5
    first_day_of_week: int = 5
    auth_enabled: bool = False
    session_timeout_minutes: int = 0
    backup_on_start: bool = True
    backup_on_exit: bool = True
    backup_keep: int = 30
    backup_before_import: bool = True
    weekend: tuple[int, ...] = config.DEFAULT_WEEKEND
    holidays: set[date] = field(default_factory=set)
    rules: dict[str, LeaveRule] = field(default_factory=default_rules)
    read_only: bool = False  # للمستخدم المطّلع فقط

    # -- بناء من app_meta ---------------------------------------------------
    @classmethod
    def from_meta(
        cls, meta: dict, rules: dict[str, LeaveRule] | None = None, holidays: set[date] | None = None
    ) -> Policy:
        d = config.DEFAULT_POLICY
        weekend_raw = str(meta.get("weekend", ",".join(str(x) for x in config.DEFAULT_WEEKEND)))
        weekend: list[int] = []
        for part in weekend_raw.split(","):
            part = part.strip()
            if part.isdigit() and 0 <= int(part) <= 6:
                weekend.append(int(part))
        return cls(
            days_per_leave=max(1, _as_int(meta.get("days_per_leave"), d["days_per_leave"])),
            max_annual=max(0, _as_int(meta.get("max_annual"), d["max_annual"])),
            enforce_annual_cap=_as_bool(meta.get("enforce_annual_cap"), False),
            basis=(meta.get("basis") or d["basis"]),
            expiry_years=max(0, _as_int(meta.get("expiry_years"), d["expiry_years"])),
            carryover_cap=max(0, _as_int(meta.get("carryover_cap"), d["carryover_cap"])),
            allow_negative_balance=_as_bool(meta.get("allow_negative_balance"), True),
            warn_negative_balance=_as_bool(meta.get("warn_negative_balance"), False),
            warn_leaving_soon_days=max(
                0, _as_int(meta.get("warn_leaving_soon_days"), d["warn_leaving_soon_days"])
            ),
            low_balance_days=_as_int(meta.get("low_balance_days"), d["low_balance_days"]),
            first_day_of_week=_as_int(meta.get("first_day_of_week"), d["first_day_of_week"]),
            auth_enabled=_as_bool(meta.get("auth_enabled"), False),
            session_timeout_minutes=max(
                0, _as_int(meta.get("session_timeout_minutes"), d.get("session_timeout_minutes", 0))
            ),
            backup_on_start=_as_bool(meta.get("backup_on_start"), True),
            backup_on_exit=_as_bool(meta.get("backup_on_exit"), True),
            backup_keep=max(1, _as_int(meta.get("backup_keep"), d["backup_keep"])),
            backup_before_import=_as_bool(meta.get("backup_before_import"), True),
            weekend=tuple(sorted(weekend)) or config.DEFAULT_WEEKEND,
            holidays=holidays or set(),
            rules=rules if rules is not None else default_rules(),
        )

    def to_meta(self) -> dict[str, str]:
        return {
            "days_per_leave": str(self.days_per_leave),
            "max_annual": str(self.max_annual),
            "enforce_annual_cap": "1" if self.enforce_annual_cap else "0",
            "basis": self.basis,
            "expiry_years": str(self.expiry_years),
            "carryover_cap": str(self.carryover_cap),
            "allow_negative_balance": "1" if self.allow_negative_balance else "0",
            "warn_negative_balance": "1" if self.warn_negative_balance else "0",
            "warn_leaving_soon_days": str(self.warn_leaving_soon_days),
            "low_balance_days": str(self.low_balance_days),
            "first_day_of_week": str(self.first_day_of_week),
            "auth_enabled": "1" if self.auth_enabled else "0",
            "session_timeout_minutes": str(self.session_timeout_minutes),
            "backup_on_start": "1" if self.backup_on_start else "0",
            "backup_on_exit": "1" if self.backup_on_exit else "0",
            "backup_keep": str(self.backup_keep),
            "backup_before_import": "1" if self.backup_before_import else "0",
            "weekend": ",".join(str(x) for x in self.weekend),
        }

    # -- استعلامات ---------------------------------------------------------
    def rule(self, leave_type: str) -> LeaveRule:
        return self.rules.get(leave_type, replace(_FALLBACK_RULE, type=leave_type))

    def compute_balance_for(self, employee, today: date | None = None):
        """دالة مختصرة لحساب رصيد موظف وفق هذه السياسة."""
        from .services import balance as B

        return B.compute_balance(employee, getattr(employee, "leaves", []), self, today=today)

    def types_for_gender(self, gender: str, include_adjustment: bool = False) -> list[str]:
        gender = gender or "ذكر"
        items = [
            r
            for r in self.rules.values()
            if r.active and (r.gender in ("", gender)) and (include_adjustment or not r.is_adjustment)
        ]
        items.sort(key=lambda r: (r.is_adjustment, r.order_index, r.type))
        return [r.type for r in items]

    def is_adjustment(self, leave_type: str) -> bool:
        return self.rule(leave_type).is_adjustment

    @property
    def adjustment_type(self) -> str:
        for name, r in self.rules.items():
            if r.is_adjustment:
                return name
        return config.ADJUSTMENT_TYPE

    @property
    def annual_rate_note(self) -> str:
        return f"يوم إجازة لكل {self.days_per_leave} أيام دوام  |  المعدل السنوي {self.max_annual} يوم"

    def with_rule(self, rule: LeaveRule) -> Policy:
        rules = dict(self.rules)
        rules[rule.type] = rule
        return replace(self, rules=rules)
