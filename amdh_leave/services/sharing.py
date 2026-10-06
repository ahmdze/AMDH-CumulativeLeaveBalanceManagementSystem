"""المشاركة: إرسال التقارير بالبريد الإلكتروني (SMTP) وتلغرام (Bot API).

بلا اعتماديات خارجية: smtplib وurllib من المكتبة القياسية.
الإعدادات تُحفظ في إعدادات الواجهة (QSettings)، وكلمة المرور/الرمز يُخزَّنان كما هما
(يُنصح باستخدام كلمة مرور تطبيق مخصّصة أو رمز بوت محدود الصلاحيات).
"""

from __future__ import annotations

import mimetypes
import smtplib
import ssl
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path

from ..logging_setup import get_logger

LOG = get_logger("sharing")


class SharingError(Exception):
    """خطأ في الإرسال مع رسالة عربية واضحة."""


# ---------------------------------------------------------------------------
# إعدادات
# ---------------------------------------------------------------------------
@dataclass
class EmailConfig:
    host: str = ""
    port: int = 587
    security: str = "starttls"      # starttls | ssl | none
    username: str = ""
    password: str = ""
    sender: str = ""
    recipients: list[str] = field(default_factory=list)
    timeout: int = 30

    @classmethod
    def from_settings(cls, settings) -> "EmailConfig":
        def value(key, default=""):
            try:
                return settings.value(key, default)
            except AttributeError:
                return default
        recipients = str(value("share_email_recipients", "") or "")
        return cls(
            host=str(value("share_email_host", "") or ""),
            port=int(value("share_email_port", 587) or 587),
            security=str(value("share_email_security", "starttls") or "starttls"),
            username=str(value("share_email_username", "") or ""),
            password=str(value("share_email_password", "") or ""),
            sender=str(value("share_email_sender", "") or ""),
            recipients=[item.strip() for item in recipients.replace(";", ",").split(",") if item.strip()],
        )

    def save(self, settings) -> None:
        settings.setValue("share_email_host", self.host)
        settings.setValue("share_email_port", int(self.port))
        settings.setValue("share_email_security", self.security)
        settings.setValue("share_email_username", self.username)
        settings.setValue("share_email_password", self.password)
        settings.setValue("share_email_sender", self.sender)
        settings.setValue("share_email_recipients", ", ".join(self.recipients))

    @property
    def from_address(self) -> str:
        return self.sender or self.username

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.from_address and self.recipients)


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""
    timeout: int = 30

    @classmethod
    def from_settings(cls, settings) -> "TelegramConfig":
        def value(key, default=""):
            try:
                return settings.value(key, default)
            except AttributeError:
                return default
        return cls(bot_token=str(value("share_telegram_token", "") or ""),
                   chat_id=str(value("share_telegram_chat", "") or ""))

    def save(self, settings) -> None:
        settings.setValue("share_telegram_token", self.bot_token)
        settings.setValue("share_telegram_chat", self.chat_id)

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


# ---------------------------------------------------------------------------
# التحقق
# ---------------------------------------------------------------------------
def validate_email_config(config: EmailConfig) -> str:
    if not config.host:
        return "خادم البريد (SMTP) غير محدد."
    if not (0 < int(config.port) < 65536):
        return "منفذ الخادم غير صالح."
    if config.security not in ("starttls", "ssl", "none"):
        return "نوع الحماية غير معروف."
    if not config.from_address:
        return "بريد المُرسل غير محدد."
    if "@" not in config.from_address:
        return "بريد المُرسل غير صالح."
    if not config.recipients:
        return "لا يوجد مستلمون."
    for address in config.recipients:
        if "@" not in address:
            return f"بريد غير صالح: {address}"
    return ""


def validate_telegram_config(config: TelegramConfig) -> str:
    if not config.bot_token:
        return "رمز البوت (Token) غير محدد."
    if ":" not in config.bot_token:
        return "رمز البوت غير صالح (يجب أن يحتوي على ':')."
    if not config.chat_id:
        return "معرّف المحادثة (Chat ID) غير محدد."
    return ""


# ---------------------------------------------------------------------------
# البريد الإلكتروني
# ---------------------------------------------------------------------------
def build_email_message(config: EmailConfig, subject: str, body: str,
                        attachments: list[Path] | None = None) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.from_address
    message["To"] = ", ".join(config.recipients)
    message.set_content(body)
    for path in attachments or []:
        path = Path(path)
        if not path.exists():
            continue
        guessed, _encoding = mimetypes.guess_type(str(path))
        maintype, subtype = (guessed or "application/octet-stream").split("/", 1)
        message.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype,
                               filename=path.name)
    return message


def send_email(config: EmailConfig, subject: str, body: str,
               attachments: list[Path] | None = None) -> None:
    """يرسل البريد. يرفع SharingError برسالة عربية عند الفشل."""
    problem = validate_email_config(config)
    if problem:
        raise SharingError(problem)
    message = build_email_message(config, subject, body, attachments)
    try:
        if config.security == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(config.host, int(config.port), timeout=config.timeout,
                                  context=context) as server:
                if config.username:
                    server.login(config.username, config.password)
                server.send_message(message)
        else:
            with smtplib.SMTP(config.host, int(config.port), timeout=config.timeout) as server:
                server.ehlo()
                if config.security == "starttls":
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if config.username:
                    server.login(config.username, config.password)
                server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise SharingError("فشل تسجيل الدخول لخادم البريد — تحقق من اسم المستخدم وكلمة المرور "
                           "(يفضّل كلمة مرور تطبيق).") from exc
    except smtplib.SMTPException as exc:
        raise SharingError(f"فشل إرسال البريد: {exc}") from exc
    except (OSError, ssl.SSLError) as exc:
        raise SharingError(f"تعذّر الاتصال بخادم البريد ({config.host}:{config.port}): {exc}") from exc
    LOG.info("أُرسل بريد إلى %s", ", ".join(config.recipients))


# ---------------------------------------------------------------------------
# تلغرام
# ---------------------------------------------------------------------------
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _multipart(fields: dict[str, str], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    """يبني جسم multipart/form-data بلا مكتبات خارجية."""
    boundary = f"----AMDH{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(str(value).encode("utf-8"))
        parts.append(b"\r\n")
    for field_name, path in files:
        path = Path(path)
        if not path.exists():
            continue
        guessed, _ = mimetypes.guess_type(str(path))
        content_type = guessed or "application/octet-stream"
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{path.name}"\r\n'.encode())
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(path.read_bytes())
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def _telegram_request(token: str, method: str, fields: dict[str, str],
                      files: list[tuple[str, Path]], timeout: int) -> dict:
    import json
    body, boundary = _multipart(fields, files)
    request = urllib.request.Request(
        TELEGRAM_API.format(token=token, method=method), data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Content-Length": str(len(body))})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise SharingError(f"رفض تلغرام الطلب ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise SharingError(f"تعذّر الاتصال بتلغرام: {exc.reason}") from exc
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise SharingError("رد غير مفهوم من تلغرام.") from exc
    if not data.get("ok"):
        raise SharingError(f"خطأ من تلغرام: {data.get('description', 'غير معروف')}")
    return data


def send_telegram_message(config: TelegramConfig, text: str) -> dict:
    problem = validate_telegram_config(config)
    if problem:
        raise SharingError(problem)
    return _telegram_request(config.bot_token, "sendMessage",
                             {"chat_id": config.chat_id, "text": text,
                              "parse_mode": "HTML"}, [], config.timeout)


def send_telegram_document(config: TelegramConfig, path: str | Path, caption: str = "") -> dict:
    problem = validate_telegram_config(config)
    if problem:
        raise SharingError(problem)
    path = Path(path)
    if not path.exists():
        raise SharingError(f"الملف غير موجود: {path}")
    fields = {"chat_id": config.chat_id}
    if caption:
        fields["caption"] = caption[:1000]
    result = _telegram_request(config.bot_token, "sendDocument", fields,
                              [("document", path)], config.timeout)
    LOG.info("أُرسل مستند إلى تلغرام: %s", path.name)
    return result


def send_telegram(config: TelegramConfig, text: str, attachments: list[Path] | None = None) -> int:
    """يرسل رسالة نصية ثم المرفقات. يعيد عدد ما أُرسل."""
    sent = 0
    if text:
        send_telegram_message(config, text)
        sent += 1
    for path in attachments or []:
        send_telegram_document(config, path, caption=Path(path).name)
        sent += 1
    return sent


def telegram_help() -> str:
    return (
        "لإنشاء بوت: افتح تلغرام ← @BotFather ← /newbot ← انسخ الرمز (Token).\n"
        "لمعرفة معرّف المحادثة: أرسل رسالة للبوت ثم افتح:\n"
        "https://api.telegram.org/bot<الرمز>/getUpdates واستخرج chat.id"
    )
