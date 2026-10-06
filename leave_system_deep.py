#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نظام إدارة الإجازات التراكمية — مشغّل الإصدار 3.

هذا الملف مجرد مشغّل؛ الكود الفعلي موزّع في حزمة ``amdh_leave`` المجاورة:
    amdh_leave/config.py      الثوابت والمسارات
    amdh_leave/db.py          قاعدة البيانات والترحيلات
    amdh_leave/rules.py       ضوابط أنواع الإجازات وسياسة الاحتساب
    amdh_leave/services/      منطق العمل (أرصدة، تحقق، نسخ احتياطي، تقارير)
    amdh_leave/exporters/     التصدير (Excel / PDF / HTML)
    amdh_leave/ui/            الواجهة الرسومية

النسخة الأحادية السابقة (ملف واحد) محفوظة في:
    legacy/leave_system_deep_v1_original.py

يمكن تشغيل البرنامج من أي مجلد (كل المسارات مطلقة).
"""

from __future__ import annotations

import os
import sys

# ضمان إمكانية الاستيراد عند التشغيل المباشر (نقر مزدوج) من أي مكان
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amdh_leave.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
