# التثبيت

## المتطلبات

- Python 3.10+
- Windows 10/11

## تثبيت التطوير

```bash
git clone https://github.com/your-org/AMDH-Calculator.git
cd AMDH-Calculator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## تشغيل الاختبارات

```bash
python -m pytest tests/ -v
```

## بناء التطبيق

```bash
pyinstaller AMDH-Leave.spec
```

## توثيق API

```bash
pip install -r requirements-docs.txt
mkdocs serve
```
