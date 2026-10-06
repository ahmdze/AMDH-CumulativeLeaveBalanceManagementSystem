"""السجلّات (logging) ومعالج الأخطاء العام."""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "amdh"
_configured = False


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> Path | None:
    """تهيئة السجل إلى ملف دوّار + الطرفية. يعيد مسار الملف."""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    if _configured:
        return getattr(logger, "_amdh_path", None)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    log_path: Path | None = None
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "app.log"
        handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    except OSError:
        log_path = None

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    logger.propagate = False
    logger._amdh_path = log_path  # type: ignore[attr-defined]
    _configured = True
    logger.info("=== بدء التشغيل ===")
    return log_path


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)


def log_path() -> Path | None:
    return getattr(logging.getLogger(_LOGGER_NAME), "_amdh_path", None)


def log_exception(context: str = "") -> str:
    """يسجّل الاستثناء الحالي ويعيد نصه."""
    text = traceback.format_exc()
    get_logger("error").error("%s\n%s", context, text)
    return text


def install_excepthook(on_error=None) -> None:
    """يعرض حوار خطأ ودّي بدل إغلاق البرنامج بصمت."""
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        get_logger("error").error("استثناء غير معالج:\n%s", text)
        if on_error is not None:
            try:
                on_error(text)
            except Exception:  # pragma: no cover - دفاع فقط
                pass
    sys.excepthook = _hook
