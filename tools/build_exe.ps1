# بناء نسخة تنفيذية (.exe) لنظام إدارة الإجازات التراكمية
# الاستخدام:
#     pwsh -File tools/build_exe.ps1
#     pwsh -File tools/build_exe.ps1 -SkipTests

param(
    [switch]$SkipTests,
    [switch]$KeepBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== نظام إدارة الإجازات التراكمية — بناء نسخة تنفيذية ==" -ForegroundColor Cyan

# 1) التحقق من بايثون
$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { throw "لم يتم العثور على python في PATH" }
Write-Host ("بايثون: " + (python --version))

# 2) الاعتماديات
Write-Host "`n[1/5] تثبيت الاعتماديات..." -ForegroundColor Yellow
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements-dev.txt

# 3) الاختبارات
if (-not $SkipTests) {
    Write-Host "`n[2/5] تشغيل الاختبارات..." -ForegroundColor Yellow
    python -m pytest tests -q
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
python -m PyInstaller AMDH-Leave.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "فشل البناء" }

# 6) تجهيز مجلد التسليم
Write-Host "`n[5/5] تجهيز مجلد التسليم..." -ForegroundColor Yellow
$out = Join-Path $root "dist\AMDH-Leave"
Copy-Item "README.md" $out -Force
$dbTemplate = Join-Path $root "employees_leave.db"
if (Test-Path $dbTemplate) { Copy-Item $dbTemplate $out -Force }

if (-not $KeepBuild) {
    Remove-Item (Join-Path $root "build") -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "`nتم البناء بنجاح: $out\AMDH-Leave.exe" -ForegroundColor Green
Write-Host "ملاحظة: ضع قاعدة البيانات (employees_leave.db) بجانب الملف التنفيذي أو استخدم --data-dir" -ForegroundColor Gray
