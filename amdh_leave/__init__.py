"""نظام إدارة الإجازات التراكمية — حزمة AMDH.

الوحدات:
    config          الثوابت والمسارات والألوان الافتراضية
    models          نماذج البيانات (dataclasses)
    db              طبقة قاعدة البيانات والترحيلات
    rules           ضوابط أنواع الإجازات وسياسة الاحتساب
    services        منطق العمل (تواريخ، أرصدة، تحقق، نسخ احتياطي، تقارير)
    exporters       التصدير (Excel / PDF / HTML)
    ui              الواجهة الرسومية (PyQt6)
"""

from __future__ import annotations

__all__ = ["__version__", "APP_NAME"]

__version__ = "3.0.0"
APP_NAME = "نظام إدارة الإجازات التراكمية"
