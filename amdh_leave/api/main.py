"""تطبيق FastAPI الرئيسي.

نقطة تشغيل API REST مع مصادقة Bearer Token الموقّع (HMAC-SHA256) ومزامنة شبكية مباشرة.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .. import config
from ..db import Database
from ..services import merge as M
from ..services import transfer as T
from ..services.security import Session, create_api_token, make_session, verify_api_token, verify_password

security = HTTPBearer(auto_error=False)

# قاعدة البيانات — تُفتح عند بدء التشغيل
db: Database | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


def get_db() -> Database:
    """اعتماد قاعدة البيانات."""
    if db is None:
        raise HTTPException(status_code=503, detail="قاعدة البيانات غير متاحة")
    return db


def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    database: Database = Depends(get_db),
) -> Session:
    """التحقق من Bearer Token الموقّع وإرجاع جلسة المستخدم الكاملة."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="مطلوب مصادقة")
    token = credentials.credentials
    payload = verify_api_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="رمز الجلسة غير صالح أو منتهي الصلاحية")
    username = str(payload.get("sub") or "")
    user = database.get_user(username)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="مستخدم غير معروف أو غير مفعّل")
    return make_session(user, auth_enabled=True)


def get_current_user(session: Session = Depends(get_current_session)) -> str:
    """إرجاع اسم المستخدم المصادق عليه."""
    return session.username


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """فتح وإغلاق قاعدة البيانات عند بدء/إنهاء التطبيق."""
    global db
    data_dir = Path(__file__).parent.parent.parent / "data"
    db_path = data_dir / "employees_leave.db"
    if not db_path.exists():
        db_path = Path("employees_leave.db")
    db = Database(db_path, backup_dir=data_dir / "backups")
    _register_routers(_app)
    yield
    if db is not None:
        db.close()
        db = None


def _register_routers(app: FastAPI) -> None:
    """تسجيل جميع routers مع التطبيق."""
    try:
        from . import balance as _bal
        from . import dashboard as _dash
        from . import employees as _emp
        from . import export_ as _exp
        from . import holidays as _hol
        from . import institutions as _inst
        from . import leaves as _lv
        from . import reports as _rpt

        app.include_router(_emp.router, prefix="/api", tags=["الموظفين"])
        app.include_router(_lv.router, prefix="/api", tags=["الإجازات"])
        app.include_router(_bal.router, prefix="/api", tags=["الأرصدة"])
        app.include_router(_rpt.router, prefix="/api", tags=["التقارير"])
        app.include_router(_dash.router, prefix="/api", tags=["لوحة المؤشرات"])
        app.include_router(_hol.router, prefix="/api", tags=["العطل"])
        app.include_router(_inst.router, prefix="/api", tags=["المؤسسات"])
        app.include_router(_exp.router, prefix="/api", tags=["التصدير"])
    except ImportError:
        pass


app = FastAPI(
    title=config.APP_NAME,
    description="API REST لنظام إدارة الرصيد التراكمي للإجازات والمزامنة الشبكية المباشرة",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """صفحة الجذر مع روابط endpoints الرئيسية."""
    return {
        "app": config.APP_NAME,
        "version": "1.0.0",
        "docs": "http://127.0.0.1:8000/docs",
        "redoc": "http://127.0.0.1:8000/redoc",
        "health": "/api/health",
        "login": "/api/auth/login (POST)",
        "transfer_upload": "/api/transfer/upload (POST)",
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": config.APP_NAME}


@app.post("/api/auth/login")
async def login(
    username: str | None = None,
    password: str | None = None,
    body: LoginRequest | None = None,
    database: Database = Depends(get_db),
):
    """تسجيل الدخول (يدعم JSON body أو Query params) وإرجاع Bearer Token موقّع."""
    u = username or (body.username if body else "")
    p = password or (body.password if body else "")
    if not u or not p:
        raise HTTPException(status_code=400, detail="يرجى إدخال اسم المستخدم وكلمة المرور")
    user = database.get_user(u)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
    if not verify_password(p, user.password_hash, user.salt, user.iterations):
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
    database.touch_login(u)
    token = create_api_token(user.username, role=user.role, institution=user.institution)
    return {
        "token": token,
        "username": user.username,
        "role": user.role,
        "institution": user.institution,
        "display_name": user.display_name,
    }


@app.post("/api/transfer/upload", tags=["المؤسسات"])
async def upload_transfer(
    file: UploadFile = File(...),
    database: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """استلام ودمج ملف نقل (.amdhz / .db) مرسل من مؤسسة فرعية عبر الشبكة المحلية (LAN Sync)."""
    if not (session.can("import_transfer") or session.can("export_transfer")):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية رفع أو استيراد ملفات النقل")
    suffix = Path(file.filename or "transfer.amdhz").suffix.lower() or ".amdhz"
    if suffix not in {".amdhz", ".zip", ".db"}:
        raise HTTPException(status_code=400, detail="صيغة الملف غير مدعومة (يُقبل .amdhz أو .db)")

    temp_dir = Path(tempfile.mkdtemp(prefix="amdh_lan_upload_"))
    try:
        saved_path = temp_dir / (Path(file.filename or f"upload{suffix}").name)
        with open(saved_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
        options = M.MergeOptions(institution=session.scoped_institution or "")
        report = T.apply_transfer(
            database,
            saved_path,
            options,
            user=session.username,
            attachments_dir=database.path.parent / "attachments",
        )
        return {
            "status": "ok",
            "institution": report.institution,
            "employees_added": report.employees_added,
            "employees_updated": report.employees_updated,
            "leaves_added": report.leaves_added,
            "leaves_updated": report.leaves_updated,
            "moves": report.moves,
            "attachments_added": report.attachments_added,
            "conflicts": report.conflicts,
            "summary": report.summary_lines(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"فشل دمج ملف النقل: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("amdh_leave.api.main:app", host="127.0.0.1", port=8000, reload=True)
