# بناء نسخة تنفيذية (.exe) لنظام إدارة الإجازات التراكمية
# الاستخدام:
#     powershell -File tools\build_exe.ps1
#     powershell -File tools\build_exe.ps1 -SkipTests

param(
    [switch]$SkipTests,
    [switch]$KeepBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== نظام إدارة الإجازات التراكمية — بناء نسخة تنفيذية ==" -ForegroundColor Cyan

# 1) التحقق من بايثون (نُفضّل مشغّل py لأنه يتجاوز اختصار متجر ويندوز)
$py = "py"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
    else { throw "لم يتم العثور على py أو python في PATH" }
}
$version = (& $py --version 2>&1) -join " "
if ($LASTEXITCODE -ne 0) { throw "تعذّر تشغيل بايثون ($py): $version" }
Write-Host ("بايثون: " + $version)

# 2) الاعتماديات
Write-Host "`n[1/5] تثبيت الاعتماديات..." -ForegroundColor Yellow
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r requirements-dev.txt

# 3) الاختبارات
if (-not $SkipTests) {
    Write-Host "`n[2/5] تشغيل الاختبارات..." -ForegroundColor Yellow
    & $py -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "فشلت الاختبارات — توقف البناء" }
} else {
    Write-Host "`n[2/5] تم تخطي الاختبارات" -ForegroundColor DarkYellow
}

# 4) نسخة احتياطية من قاعدة البيانات قبل البناء
Write-Host "`n[3/5] نسخة احتياطية من البيانات..." -ForegroundColor Yellow
$db = Join-Path $root "employees_leave.db"
if (Test-Path $db) {
    $stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $dest = Join-Path $root "backups\build_$stamp.db"
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item $db $dest -Force
    Write-Host ("   نسخة: " + $dest)
} else {
    Write-Host "   لا توجد قاعدة بيانات بعد (سيتم إنشاؤها عند أول تشغيل)"
}

# 5) البناء
Write-Host "`n[4/5] بناء النسخة التنفيذية..." -ForegroundColor Yellow
& $py -m PyInstaller AMDH-Leave.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "فشل البناء" }

# 6) تجهيز مجلد التسليم (بلا قاعدة بيانات حقيقية — البيانات تُنشأ عند أول تشغيل)
Write-Host "`n[5/5] تجهيز مجلد التسليم..." -ForegroundColor Yellow
$out = Join-Path $root "dist\AMDH-Leave"
Copy-Item "README.md" $out -Force

if (-not $KeepBuild) {
    Remove-Item (Join-Path $root "build") -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "`nتم البناء بنجاح: $out\AMDH-Leave.exe" -ForegroundColor Green
Write-Host "ملاحظة: البيانات تُحفظ في مجلد data بجانب الـ EXE (أو --data-dir)." -ForegroundColor Gray
Write-Host "لا تنسخ قاعدة بياناتك الحقيقية إلى مجلد التوزيع." -ForegroundColor Yellow
