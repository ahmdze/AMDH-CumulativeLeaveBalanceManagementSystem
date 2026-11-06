"""تطبيق FastAPI الرئيسي.

نقطة تشغيل API REST مع مصادقة Bearer Token.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .. import config
from ..db import Database
from ..services.security import verify_password

security = HTTPBearer(auto_error=False)

# قاعدة البيانات — تُفتح عند بدء التشغيل
db: Database | None = None


def get_db() -> Database:
    """اعتماد قاعدة البيانات."""
    if db is None:
        raise HTTPException(status_code=503, detail="قاعدة البيانات غير متاحة")
    return db


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """التحقق من Bearer Token وإرجاع اسم المستخدم."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="مطلوب مصادقة")
    token = credentials.credentials
    database = get_db()
    user = database.get_user(token)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="مستخدم غير معروف أو غير مفعّل")
    return user.username


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """فتح وإغلاق قاعدة البيانات عند بدء/إنهاء التطبيق."""
    global db
    data_dir = Path(__file__).parent.parent.parent / "data"
    db_path = data_dir / "employees_leave.db"
    if not db_path.exists():
        db_path = Path("employees_leave.db")
    db = Database(db_path, backup_dir=data_dir / "backups")
    # استيراد endpoints داخل lifespan لتجنب الاستيراد الدائري
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
    description="API REST لنظام إدارة الرصيد التراكمي للإجازات",
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
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": config.APP_NAME}


@app.post("/api/auth/login")
async def login(username: str, password: str):
    """تسجيل الدخول وإرجاع Bearer Token."""
    database = get_db()
    user = database.get_user(username)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
    if not verify_password(password, user.password_hash, user.salt, user.iterations):
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
    database.touch_login(username)
    return {"token": username, "role": user.role, "display_name": user.display_name}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("amdh_leave.api.main:app", host="127.0.0.1", port=8000, reload=True)
