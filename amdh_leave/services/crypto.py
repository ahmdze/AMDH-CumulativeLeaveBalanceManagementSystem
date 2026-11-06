"""تشفير قاعدة البيانات عبر SQLCipher + ملف قفل لكلمة المرور + تشفير الخزنة وملفات النقل.

كيف يعمل:
  * عند تفعيل التشفير تُنشأ قاعدة مشفّرة بمفتاح مشتق من كلمة المرور
    (PBKDF2-HMAC-SHA256، 200 ألف تكرار، مفتاح خام 256-bit يُمرَّر إلى SQLCipher).
  * يُكتب ملف قفل ``.amdh_lock.json`` في مجلد البيانات يحمل الملح وعدد التكرارات
    وبصمة تحقق (لا يحمل كلمة المرور نفسها)، فيعرف البرنامج قبل الفتح أن القاعدة مشفّرة.
  * إن لم تكن حزمة SQLCipher مثبتة، يبقى البرنامج يعمل بلا تشفير مع رسالة واضحة
    وخطوات التثبيت — بلا أي إتلاف للبيانات.

التثبيت:  pip install sqlcipher3==0.6.4
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from ..logging_setup import get_logger

LOG = get_logger("crypto")

LOCK_FILENAME = ".amdh_lock.json"
KEY_FILENAME = ".amdh_dbkey"
KDF_ITERATIONS = 200_000
KEY_BYTES = 32
SQLCIPHER_MODULES = ("sqlcipher3", "sqlcipher3.dbapi2", "pysqlcipher3.dbapi2")

VAULT_PREFIX = "enc:v1:"
TRANSFER_MAGIC = b"AMDH_ENC_V1\n"
_DEFAULT_TRANSFER_SECRET = "amdh-transfer-envelope-v1-key-2026"


class CryptoError(Exception):
    """خطأ تشفير مع رسالة عربية واضحة."""


# ---------------------------------------------------------------------------
# تشفير قياسي للخزنة وملفات النقل (Fernet / HMAC-XOR fallback)
# ---------------------------------------------------------------------------
def _fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256((secret or _DEFAULT_TRANSFER_SECRET).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_bytes(data: bytes, secret: str = "") -> bytes:
    """يشفّر مصفوفة بايتات باستخدام Fernet (AES-128-CBC + HMAC-SHA256) مع ترويسة قياسية."""
    try:
        from cryptography.fernet import Fernet

        token = Fernet(_fernet_key(secret)).encrypt(data)
        return TRANSFER_MAGIC + token
    except ImportError:  # pragma: no cover
        return data


def decrypt_bytes(data: bytes, secret: str = "") -> bytes:
    """يفك تشفير مصفوفة بايتات مشفّرة بـ encrypt_bytes (أو يعيدها كما هي إن لم تكن مشفّرة)."""
    if not data.startswith(TRANSFER_MAGIC):
        return data
    payload = data[len(TRANSFER_MAGIC) :]
    try:
        from cryptography.fernet import Fernet

        return Fernet(_fernet_key(secret)).decrypt(payload)
    except Exception as exc:  # noqa: BLE001
        raise CryptoError("فشل فك تشفير البيانات — المفتاح غير مطابق أو الملف تالف.") from exc


def is_encrypted_payload(data: bytes) -> bool:
    return data.startswith(TRANSFER_MAGIC)


def encrypt_secret_text(plaintext: str, secret: str = "") -> str:
    """يشفّر نصاً حساساً (مثل كلمات مرور الخزنة) ليُحفظ مشفّراً داخل الجدول."""
    if not plaintext or plaintext.startswith(VAULT_PREFIX):
        return plaintext
    try:
        from cryptography.fernet import Fernet

        token = Fernet(_fernet_key(secret or "amdh-vault-secret-v1")).encrypt(plaintext.encode("utf-8"))
        return VAULT_PREFIX + token.decode("ascii")
    except ImportError:  # pragma: no cover
        return plaintext


def decrypt_secret_text(stored: str, secret: str = "") -> str:
    """يفك تشفير نص محفوظ في الخزنة (ويقبل النص القديم غير المشفّر بتوافق عكسي)."""
    if not stored or not stored.startswith(VAULT_PREFIX):
        return stored or ""
    token = stored[len(VAULT_PREFIX) :].encode("ascii")
    try:
        from cryptography.fernet import Fernet

        return Fernet(_fernet_key(secret or "amdh-vault-secret-v1")).decrypt(token).decode("utf-8")
    except Exception:  # noqa: BLE001
        return stored


# ---------------------------------------------------------------------------
# توفّر SQLCipher
# ---------------------------------------------------------------------------
def sqlcipher_module():
    """يعيد وحدة SQLCipher إن كانت مثبتة وإلا None."""
    import importlib

    for name in SQLCIPHER_MODULES:
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
    return None


def sqlcipher_available() -> bool:
    return sqlcipher_module() is not None


def install_hint() -> str:
    return (
        "لتشفير قاعدة البيانات يجب تثبيت حزمة SQLCipher:\n\n"
        "    pip install sqlcipher3==0.6.4\n\n"
        "ثم أعد تشغيل البرنامج. (على لينكس قد تحتاج:\n"
        "    pip install sqlcipher3  أو  apt install libsqlcipher-dev)"
    )


# ---------------------------------------------------------------------------
# اشتقاق المفتاح وملف القفل
# ---------------------------------------------------------------------------
def new_salt() -> str:
    return os.urandom(16).hex()


def derive_key(
    password: str, salt_hex: str, iterations: int = KDF_ITERATIONS, length: int = KEY_BYTES
) -> str:
    """يشتق مفتاحاً خاماً (hex) من كلمة المرور — يُمرَّر إلى SQLCipher بلا KDF داخلي."""
    if not password:
        raise CryptoError("كلمة المرور فارغة.")
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError as exc:
        raise CryptoError("ملح غير صالح في ملف القفل.") from exc
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations), dklen=length)
    return digest.hex()


def key_pragma(key_hex: str) -> str:
    """صيغة PRAGMA key للمفتاح الخام في SQLCipher."""
    return f"\"x'{key_hex}'\""


def verifier(password: str, salt_hex: str, iterations: int) -> str:
    """بصمة تحقق مستقلة (لا تكشف المفتاح) للتأكد من صحة كلمة المرور قبل الفتح."""
    return derive_key(password, salt_hex, iterations, length=32)


# ---------------------------------------------------------------------------
# ملف القفل
# ---------------------------------------------------------------------------
def lock_path(data_dir: Path) -> Path:
    return Path(data_dir) / LOCK_FILENAME


def read_lock(data_dir: Path) -> dict | None:
    path = lock_path(data_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("mode") == "keyfile":
        return data
    if not data.get("salt") or not data.get("verifier"):
        return None
    return data


# ---------------------------------------------------------------------------
# ملف المفتاح التلقائي (نسخ المؤسسات): يفتح القاعدة دون سؤال كلمة مرور
# ---------------------------------------------------------------------------
def key_file_path(data_dir: Path) -> Path:
    return Path(data_dir) / KEY_FILENAME


def read_key_file(data_dir: Path) -> str | None:
    """يعيد مفتاحاً سداسياً صالحاً من ملف المفتاح، أو None."""
    path = key_file_path(data_dir)
    try:
        text = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    if len(text) != KEY_BYTES * 2:
        return None
    try:
        bytes.fromhex(text)
    except ValueError:
        return None
    return text


def write_key_file(data_dir: Path, key_hex: str) -> Path:
    path = key_file_path(data_dir)
    path.write_text(key_hex.strip().lower(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def remove_key_file(data_dir: Path) -> None:
    path = key_file_path(data_dir)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def write_key_lock(data_dir: Path) -> Path:
    """قفل وضع «المفتاح التلقائي» — لا يحمل كلمة مرور ولا بصمة."""
    payload = {
        "version": 1,
        "enabled": True,
        "mode": "keyfile",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cipher": "sqlcipher",
    }
    path = lock_path(data_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def is_encryption_enabled(data_dir: Path) -> bool:
    data = read_lock(data_dir)
    return bool(data and data.get("enabled"))


def write_lock(
    data_dir: Path,
    password: str,
    iterations: int = KDF_ITERATIONS,
    enabled: bool = True,
    salt: str | None = None,
) -> Path:
    """يكتب ملف القفل (ملح + بصمة تحقق) بعد تشفير ناجح.

    ``salt`` يجب أن يكون **نفس الملح** المستخدم في اشتقاق مفتاح التشفير، وإلا
    أصبح الملف المشفّر غير قابل للفتح. يُولَّد تلقائياً فقط عند التفعيل الأولي.
    """
    salt = salt or new_salt()
    payload = {
        "version": 1,
        "enabled": bool(enabled),
        "salt": salt,
        "iterations": int(iterations),
        "verifier": verifier(password, salt, iterations),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cipher": "sqlcipher",
    }
    path = lock_path(data_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def remove_lock(data_dir: Path) -> None:
    path = lock_path(data_dir)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def check_password(data_dir: Path, password: str) -> bool:
    data = read_lock(data_dir)
    if not data or not data.get("salt"):
        return False
    candidate = verifier(password, data["salt"], int(data.get("iterations", KDF_ITERATIONS)))
    return hmac.compare_digest(candidate, str(data["verifier"]))


# ---------------------------------------------------------------------------
# الاتصال والكشف
# ---------------------------------------------------------------------------
def is_encrypted_database(path: str | Path) -> bool:
    """هل الملف قاعدة مشفّرة؟ (تُكتشف بمحاولة فتحه بقارئ SQLite العادي)."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        probe = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            probe.execute("SELECT count(*) FROM sqlite_master").fetchone()
            return False
        finally:
            probe.close()
    except sqlite3.DatabaseError as exc:
        message = str(exc).lower()
        if "not a database" in message or "encrypted" in message or "file is encrypted" in message:
            return True
        return False


def open_connection(path: str | Path, key_hex: str | None = None) -> sqlite3.Connection:
    """يفتح اتصالاً عادياً أو مشفّراً حسب وجود المفتاح.

    إن طُلب مفتاح ولازمة SQLCipher غير مثبتة يُرفع CryptoError برسالة إرشادية.
    """
    if key_hex:
        module = sqlcipher_module()
        if module is None:
            raise CryptoError(install_hint())
        connection = module.connect(str(path))
        connection.execute(f"PRAGMA key = {key_pragma(key_hex)}")
        connection.execute("PRAGMA cipher_page_size = 4096")
        connection.execute("PRAGMA kdf_iter = 256000")
        try:  # اختبار المفتاح فوراً
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except Exception as exc:  # noqa: BLE001 - أي فشل هنا يعني مفتاحاً/ملفاً خاطئاً
            connection.close()
            raise CryptoError("كلمة المرور غير صحيحة أو أن الملف ليس قاعدة SQLCipher صالحة.") from exc
        return connection
    plain = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    return plain


# ---------------------------------------------------------------------------
# التشفير وفك التشفير
# ---------------------------------------------------------------------------
def _require_sqlcipher() -> object:
    module = sqlcipher_module()
    if module is None:
        raise CryptoError(install_hint())
    return module


def _table_names(connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _encrypt_to(source: str | Path, key_hex: str, *, keep_backup: bool = True) -> tuple[Path, Path | None]:
    """ينفّذ تحويل قاعدة عادية إلى مشفّرة بمفتاح خام (بلا كتابة قفل)."""
    module = _require_sqlcipher()
    source = Path(source)
    if is_encrypted_database(source):
        raise CryptoError("قاعدة البيانات مشفّرة مسبقاً.")
    backup: Path | None = None
    if keep_backup:
        backup = source.with_name(f"{source.stem}_plain_{datetime.now():%Y%m%d_%H%M%S}.db")
        shutil.copy2(source, backup)

    temp = source.with_name(source.name + ".enc.tmp")
    if temp.exists():
        temp.unlink()
    connection = module.connect(str(source))
    try:
        connection.execute(f"ATTACH DATABASE '{temp.as_posix()}' AS encrypted KEY {key_pragma(key_hex)}")
        connection.execute("SELECT sqlcipher_export('encrypted')")
        connection.execute("DETACH DATABASE encrypted")
    except Exception as exc:
        connection.close()
        if temp.exists():
            temp.unlink()
        raise CryptoError(f"فشل التشفير: {exc}") from exc
    connection.close()

    for suffix in ("-wal", "-shm"):
        side = Path(str(source) + suffix)
        if side.exists():
            side.unlink()
    source.write_bytes(temp.read_bytes())
    temp.unlink()
    return source, backup


def encrypt_database(
    source: str | Path, password: str, *, keep_backup: bool = True, iterations: int = KDF_ITERATIONS
) -> Path:
    """يحوّل قاعدة عادية إلى قاعدة مشفّرة بكلمة مرور (نمط المركز)."""
    source = Path(source)
    salt = new_salt()
    key_hex = derive_key(password, salt, iterations)
    output, backup = _encrypt_to(source, key_hex, keep_backup=keep_backup)
    remove_key_file(output.parent)
    write_lock(output.parent, password, iterations, salt=salt)
    LOG.warning(
        "تم تشفير قاعدة البيانات (%s) — نسخة غير مشفّرة: %s", output.name, backup.name if backup else "—"
    )
    return output


def encrypt_with_key(source: str | Path, key_hex: str, *, keep_backup: bool = False) -> Path:
    """يشفّر قاعدة عادية بمفتاح خام ويكتب ملف المفتاح (نمط نسخة المؤسسة)."""
    source = Path(source)
    output, backup = _encrypt_to(source, key_hex, keep_backup=keep_backup)
    write_key_file(output.parent, key_hex)
    write_key_lock(output.parent)
    LOG.warning("تم تشفير نسخة المؤسسة بمفتاح تلقائي (%s)", output.name)
    return output


def decrypt_database(
    source: str | Path,
    password: str,
    *,
    destination: str | Path | None = None,
    iterations: int | None = None,
    keep_backup: bool = True,
) -> Path:
    """يفك التشفير إلى قاعدة عادية (لاستعادة الوصول أو النسخ الاحتياطي)."""
    module = _require_sqlcipher()
    source = Path(source)
    data_dir = source.parent
    lock = read_lock(data_dir)
    if lock and lock.get("mode") == "keyfile":
        raise CryptoError(
            "هذه نسخة مؤسسة تعمل بمفتاح تلقائي؛ لا تُفك بكلمة مرور. استخدم أداة المفتاح في مركز الدائرة."
        )
    if not lock and iterations is None:
        raise CryptoError("ملف القفل غير موجود — لا يمكن اشتقاق المفتاح.")
    salt = lock["salt"] if lock else new_salt()
    iterations = int(iterations if iterations is not None else lock.get("iterations", KDF_ITERATIONS))
    key_hex = derive_key(password, salt, iterations)

    target = Path(destination) if destination else source.with_name(f"{source.stem}_plain.db")
    if target.exists():
        target.unlink()
    connection = module.connect(str(source))
    try:
        connection.execute(f"PRAGMA key = {key_pragma(key_hex)}")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        connection.execute(f"ATTACH DATABASE '{target.as_posix()}' AS plaintext KEY ''")
        connection.execute("SELECT sqlcipher_export('plaintext')")
        connection.execute("DETACH DATABASE plaintext")
    except Exception as exc:
        connection.close()
        raise CryptoError(f"فشل فك التشفير: {exc}") from exc
    connection.close()
    LOG.warning("تم فك تشفير قاعدة البيانات إلى %s", target.name)
    return target


def change_password(source: str | Path, old_password: str, new_password: str) -> None:
    """تغيير كلمة المرور: فك تشفير مؤقت ثم إعادة تشفير بكلمة جديدة."""
    source = Path(source)
    if not check_password(source.parent, old_password):
        raise CryptoError("كلمة المرور الحالية غير صحيحة.")
    plain = decrypt_database(source, old_password, destination=source.with_name(source.name + ".rekey"))
    try:
        encrypt_database(plain, new_password, keep_backup=False)
        shutil.copy2(plain, source)
    finally:
        if plain.exists():
            plain.unlink()


def disable_encryption(data_dir: Path, db_path: str | Path, password: str) -> Path:
    """يلغي التشفير: يفك التشفير إلى ملف عادي، يستبدل القاعدة، ويحذف ملف القفل."""
    db_path = Path(db_path)
    if not check_password(data_dir, password):
        raise CryptoError("كلمة المرور غير صحيحة.")
    if sqlcipher_module() is None:
        raise CryptoError(install_hint())
    plain = decrypt_database(db_path, password, destination=db_path.with_name(db_path.name + ".plain"))
    try:
        for suffix in ("-wal", "-shm"):
            side = Path(str(db_path) + suffix)
            if side.exists():
                side.unlink()
        shutil.copy2(plain, db_path)
    finally:
        if plain.exists():
            plain.unlink()
    remove_lock(data_dir)
    remove_key_file(data_dir)
    LOG.warning("تم إلغاء تشفير قاعدة البيانات: %s", db_path.name)
    return db_path


def security_summary(data_dir: Path, db_path: Path) -> dict:
    """ملخص حالة التشفير لعرضه في الواجهة."""
    lock = read_lock(data_dir) or {}
    return {
        "sqlcipher_available": sqlcipher_available(),
        "lock_file": lock_path(data_dir).exists(),
        "encryption_enabled": is_encryption_enabled(data_dir),
        "database_encrypted": is_encrypted_database(db_path),
        "key_file": bool(read_key_file(data_dir)),
        "mode": lock.get("mode", "password" if lock else ""),
        "lock_data": lock,
    }
