<#
تثبيت دعم تشفير قاعدة البيانات (SQLCipher) لنظام إدارة الإجازات التراكمية.

الاستخدام:
    powershell -File tools\install_sqlcipher.ps1
#>

$ErrorActionPreference = "Continue"

Write-Host "== تثبيت دعم SQLCipher ==" -ForegroundColor Cyan
$py = "py"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
    else {
        Write-Host "خطأ: لم يتم العثور على Python في النظام." -ForegroundColor Red
        exit 1
    }
}

Write-Host "`nتثبيت sqlcipher3 ..." -ForegroundColor Yellow
& $py -m pip install "sqlcipher3==0.6.4"

& $py -c "import sqlcipher3; print('OK: sqlcipher3'); print(sqlcipher3.sqlite_version if hasattr(sqlcipher3, 'sqlite_version') else '')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nتعذّر تثبيت SQLCipher تلقائياً." -ForegroundColor Red
    Write-Host "جرّب يدوياً:  py -m pip install sqlcipher3==0.6.4" -ForegroundColor Gray
    Write-Host "البرنامج يعمل بشكل طبيعي بلا تشفير إلى أن تُثبَّت الحزمة." -ForegroundColor Gray
    exit 1
}

Write-Host "`nتم التثبيت. افتح البرنامج ← الإعدادات ← الأمان والتشفير ← إدارة التشفير" -ForegroundColor Cyan
Write-Host "احفظ كلمة مرور القاعدة في مكان آمن — لا يمكن استرجاعها." -ForegroundColor Yellow
