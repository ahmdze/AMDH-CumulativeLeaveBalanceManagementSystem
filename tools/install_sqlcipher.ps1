<#
تثبيت دعم تشفير قاعدة البيانات (SQLCipher) لنظام إدارة الإجازات التراكمية.

الاستخدام:
    pwsh -File tools/install_sqlcipher.ps1

ما يفعله:
  1. يتحقق من إصدار بايثون.
  2. يثبّت sqlcipher3-binary (وإن فشل يجرّب sqlcipher3 ثم pysqlcipher3).
  3. يتحقق من نجاح الاستيراد ويطبع النتيجة.

ملاحظة: التشفير اختياري تماماً — البرنامج يعمل بلا هذه الحزمة، وتبقى ميزة
«تشفير قاعدة البيانات» معطّلة مع رسالة إرشادية داخل البرنامج.
#>

$ErrorActionPreference = "Stop"

Write-Host "== تثبيت دعم SQLCipher ==" -ForegroundColor Cyan
Write-Host ("بايثون: " + (python --version))

$packages = @("sqlcipher3-binary", "sqlcipher3", "pysqlcipher3")
$installed = $false

foreach ($package in $packages) {
    Write-Host "`nمحاولة تثبيت $package ..." -ForegroundColor Yellow
    python -m pip install --upgrade $package
    if ($LASTEXITCODE -eq 0) {
        $check = python -c "import importlib,sys; ok=False
for name in ('sqlcipher3','sqlcipher3.dbapi2','pysqlcipher3.dbapi2'):
    try:
        importlib.import_module(name); ok=True; print('OK:', name); break
    except ImportError: pass
sys.exit(0 if ok else 1)"
        if ($LASTEXITCODE -eq 0) {
            $installed = $true
            Write-Host "تم التثبيت بنجاح: $package" -ForegroundColor Green
            break
        }
    }
}

if (-not $installed) {
    Write-Host "`nتعذّر تثبيت SQLCipher تلقائياً." -ForegroundColor Red
    Write-Host "جرّب يدوياً:" -ForegroundColor Gray
    Write-Host "  python -m pip install sqlcipher3-binary" -ForegroundColor Gray
    Write-Host "  (لينكس) sudo apt install libsqlcipher-dev && pip install sqlcipher3" -ForegroundColor Gray
    Write-Host "البرنامج يعمل بشكل طبيعي بلا تشفير إلى أن تُثبَّت الحزمة." -ForegroundColor Gray
    exit 1
}

Write-Host "`nافتح البرنامج ← الإعدادات ← الأمان والتشفير ← إدارة التشفير" -ForegroundColor Cyan
Write-Host "تنبيه: احفظ كلمة المرور في مكان آمن — لا يمكن استرجاعها." -ForegroundColor Yellow
