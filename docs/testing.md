# الاختبارات

## تشغيل الاختبارات

```bash
python -m pytest tests/ -v
```

## التغطية

```bash
python -m pytest tests/ --cov=amdh_leave --cov-report=html
```

## الفحص الساكن

```bash
ruff check amdh_leave/
ruff format --check amdh_leave/
```

## هيكل الاختبارات

- `test_db.py`: قاعدة البيانات
- `test_balance.py`: حساب الرصيد
- `test_merge.py`: الدمج
- `test_crypto.py`: التشفير
- `test_security.py`: الأمان
- `test_exporters.py`: التصدير
- `test_institutions.py`: المؤسسات
- `test_reports.py`: التقارير
- `test_static_analysis.py`: الفحص الساكن
