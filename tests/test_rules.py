"""اختبارات الضوابط والسياسة (rules/Policy)."""

from __future__ import annotations

from dataclasses import replace

from amdh_leave import config
from amdh_leave.rules import LeaveRule, Policy, default_rules


def test_default_rules_cover_all_legacy_types():
    rules = default_rules()
    for name in ("اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات", "كارت الزمنية",
                 "قبل الوضع", "بعد الوضع", "أمومة"):
        assert name in rules
    assert config.ADJUSTMENT_TYPE not in rules


def test_policy_roundtrip_through_meta(policy):
    meta = policy.to_meta()
    restored = Policy.from_meta(meta, policy.rules)
    assert restored.days_per_leave == policy.days_per_leave
    assert restored.weekend == policy.weekend
    assert restored.basis == policy.basis
    assert restored.enforce_annual_cap == policy.enforce_annual_cap
    assert restored.auth_enabled == policy.auth_enabled


def test_policy_from_meta_defaults_on_garbage():
    restored = Policy.from_meta({"days_per_leave": "غير رقم", "weekend": "abc", "basis": ""})
    assert restored.days_per_leave == config.DAYS_PER_LEAVE
    assert restored.weekend == config.DEFAULT_WEEKEND
    assert restored.basis == config.BASIS_CONTINUOUS
    assert restored.allow_negative_balance is True


def test_types_for_gender_filters_female_only():
    policy = Policy.from_meta({}, default_rules())
    male = policy.types_for_gender("ذكر")
    female = policy.types_for_gender("أنثى")
    assert "أمومة" not in male
    assert {"قبل الوضع", "بعد الوضع", "أمومة"} <= set(female)
    assert "اعتيادية" in male and "اعتيادية" in female


def test_types_for_gender_hides_legacy_adjustment():
    rules = default_rules()
    rules[config.ADJUSTMENT_TYPE] = LeaveRule(type=config.ADJUSTMENT_TYPE,
                                              is_adjustment=True, active=True)
    policy = Policy.from_meta({}, rules)
    assert config.ADJUSTMENT_TYPE not in policy.types_for_gender("ذكر")
    assert config.ADJUSTMENT_TYPE not in policy.types_for_gender("ذكر", include_adjustment=False)


def test_inactive_rules_are_hidden():
    rules = default_rules()
    rules["مرضية"] = replace(rules["مرضية"], active=False)
    policy = Policy.from_meta({}, rules)
    assert "مرضية" not in policy.types_for_gender("ذكر")


def test_unknown_type_falls_back_to_safe_rule():
    policy = Policy.from_meta({}, default_rules())
    rule = policy.rule("نوع غير معروف")
    assert isinstance(rule, LeaveRule)
    assert rule.type == "نوع غير معروف"
    assert rule.consumes_balance is True


def test_quota_label_and_count_mode_label():
    rule = LeaveRule(type="مرضية", quota_days=30, quota_period="year", count_mode="working")
    assert "30" in rule.quota_label
    assert rule.count_mode_label == config.COUNT_MODE_LABELS["working"]
    assert LeaveRule(type="x").quota_label == "بلا سقف"
