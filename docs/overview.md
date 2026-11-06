# نظرة عامة

نظام إدارة الرصيد التراكمي للإجازات (AMDH-Leave) هو تطبيق مكتبي لإدارة إجازات الموظفين في المؤسسات الصحية.

## البنية

```
amdh_leave/
  db/              # قاعدة البيانات (مقسمة إلى وحدات)
    schema.py      # مخطط الجداول والفهارس
    migrations.py  # الترحيلات والتعبئة
    queries.py     # الاستعلامات والعمليات
  services/        # منطق العمل
    balance.py     # حساب الرصيد
    merge.py       # دمج البيانات
    crypto.py      # التشفير
    reports.py     # التقارير
  exporters/       # التصدير
    excel.py       # Excel
    pdf.py         # PDF
  ui/              # الواجهة الرسومية
    main_window.py # النافذة الرئيسية
    dashboard.py   # لوحة المؤشرات
  models.py        # نماذج البيانات
  rules.py         # قواعد الإجازات
  config.py        # الإعدادات
```

## التقنيات

- **Python 3.10+** مع type hints
- **PyQt6** للواجهة الرسومية
- **SQLite** مع SQLCipher للتشفير
- **openpyxl** لـ Excel
- **reportlab** لـ PDF بالعربية
