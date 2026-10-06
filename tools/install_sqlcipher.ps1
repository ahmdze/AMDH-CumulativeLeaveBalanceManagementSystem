<#
تثبيت دعم تشفير قاعدة البيانات (SQLCipher) لنظام إدارة الإجازات التراكمية.

الاستخدام:
    pwsh -File tools/install_sqlcipher.ps1
#>

$ErrorActionPreference = "Continue"

Write-Host "== تثبيت دعم SQLCipher ==" -ForegroundColor Cyan
try {
    python --version
} catch {
    Write-Host "خطأ: لم يتم العثور على Python في النظام." -ForegroundColor Red
    exit 1
}

$packages = @("sqlcipher3-binary", "sqlcipher3", "pysqlcipher3")
$installed = $false

foreach ($package in $packages) {
    Write-Host "`nمحاولة تثبيت $package ..." -ForegroundColor Yellow
    
    # 1. Install the package
    python -m pip install $package

    # 2. Test if Python can import it
    $pythonCode = @'
import sys, importlib
ok = False
for name in ('sqlcipher3', 'sqlcipher3.dbapi2', 'pysqlcipher3.dbapi2'):
try:
    importlib.import_module(name)
    ok = True
    print('OK:', name)
    break
except Exception:
    pass
sys.exit(0 if ok else 1)
'@

    $pythonCode | python

    # 3. Check Python exit status
    if ($LASTEXITCODE -eq 0) {
        Write-Host "تم التثبيت والتحقق بنجاح: $package" -ForegroundColor Green
        $installed =$true
        break
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
Write-Host "رمز آمن - لا يمكن استرجاعها." -ForegroundColor Yellow