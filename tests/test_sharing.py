"""اختبارات المشاركة: البريد الإلكتروني وتلغرام."""

from __future__ import annotations

from pathlib import Path

import pytest

from amdh_leave.services import sharing
from amdh_leave.services.sharing import EmailConfig, SharingError, TelegramConfig


# ---------------------------------------------------------------------------
# التحقق
# ---------------------------------------------------------------------------
def test_validate_email_config():
    assert "SMTP" in sharing.validate_email_config(EmailConfig())
    config = EmailConfig(host="smtp.example.com", port=587, sender="a@b.com",
                         recipients=["c@d.com"])
    assert sharing.validate_email_config(config) == ""
    bad_port = EmailConfig(host="h", port=0, sender="a@b.com", recipients=["c@d.com"])
    assert "منفذ" in sharing.validate_email_config(bad_port)
    bad_sender = EmailConfig(host="h", sender="ليس-بريداً", recipients=["c@d.com"])
    assert "المُرسل" in sharing.validate_email_config(bad_sender)
    no_recipients = EmailConfig(host="h", sender="a@b.com")
    assert "مستلمون" in sharing.validate_email_config(no_recipients)
    bad_recipient = EmailConfig(host="h", sender="a@b.com", recipients=["bad"])
    assert "غير صالح" in sharing.validate_email_config(bad_recipient)


def test_validate_telegram_config():
    assert "البوت" in sharing.validate_telegram_config(TelegramConfig())
    assert "صالح" in sharing.validate_telegram_config(TelegramConfig(bot_token="abc"))
    assert "المحادثة" in sharing.validate_telegram_config(TelegramConfig(bot_token="1:abc"))
    assert sharing.validate_telegram_config(
        TelegramConfig(bot_token="123:ABCDEF", chat_id="456")) == ""


def test_is_configured_flags():
    assert EmailConfig(host="h", username="u@x.com", recipients=["a@b.com"]).is_configured
    assert not EmailConfig(host="h").is_configured
    assert TelegramConfig(bot_token="1:a", chat_id="2").is_configured


# ---------------------------------------------------------------------------
# بناء الرسالة وتلغرام
# ---------------------------------------------------------------------------
def test_build_email_message_with_attachments(tmp_path):
    attachment = tmp_path / "تقرير.xlsx"
    attachment.write_bytes(b"PK\x03\x04fake-xlsx-content")
    config = EmailConfig(host="h", sender="from@example.com",
                         recipients=["to1@example.com", "to2@example.com"])
    message = sharing.build_email_message(config, "تقرير الإجازات", "المحتوى", [attachment])
    assert message["Subject"] == "تقرير الإجازات"
    assert message["From"] == "from@example.com"
    assert "to1@example.com" in message["To"] and "to2@example.com" in message["To"]
    assert message.get_content_type() == "multipart/mixed"
    names = [part.get_filename() for part in message.iter_attachments()]
    assert "تقرير.xlsx" in names


def test_build_email_message_skips_missing_attachment(tmp_path):
    config = EmailConfig(host="h", sender="a@b.com", recipients=["c@d.com"])
    message = sharing.build_email_message(config, "s", "b", [tmp_path / "غير موجود.xlsx"])
    assert not list(message.iter_attachments())


def test_multipart_body_contains_file_and_boundary(tmp_path):
    target = tmp_path / "report.pdf"
    target.write_bytes(b"%PDF-1.4 fake")
    body, boundary = sharing._multipart({"chat_id": "123", "caption": "تقرير"},
                                        [("document", target)])
    assert boundary.encode() in body
    assert b'name="chat_id"' in body and b"123" in body
    assert b'filename="report.pdf"' in body
    assert b"%PDF-1.4 fake" in body
    assert body.rstrip().endswith(b"--")


def test_telegram_api_url_shape():
    assert sharing.TELEGRAM_API.format(token="T", method="sendDocument").endswith(
        "/botT/sendDocument")


def test_telegram_help_mentions_botfather():
    assert "BotFather" in sharing.telegram_help()


# ---------------------------------------------------------------------------
# الإرسال: الفشل يُترجم إلى رسالة عربية واضحة (بلا شبكة)
# ---------------------------------------------------------------------------
def test_send_email_rejects_incomplete_config():
    with pytest.raises(SharingError):
        sharing.send_email(EmailConfig(), "s", "b")


def test_send_email_invalid_host_raises_arabic_error():
    config = EmailConfig(host="invalid.invalid", port=587, sender="a@b.com",
                         recipients=["c@d.com"], timeout=3)
    with pytest.raises(SharingError) as error:
        sharing.send_email(config, "s", "b")
    assert "خادم البريد" in str(error.value) or "فشل" in str(error.value)


def test_send_telegram_rejects_incomplete_config():
    with pytest.raises(SharingError):
        sharing.send_telegram_message(TelegramConfig(), "نص")


def test_send_telegram_document_missing_file():
    config = TelegramConfig(bot_token="1:a", chat_id="2")
    with pytest.raises(SharingError) as error:
        sharing.send_telegram_document(config, "no-such-file.pdf")
    assert "غير موجود" in str(error.value)


# ---------------------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------------------
def test_configs_roundtrip_through_qsettings(tmp_path):
    from PyQt6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)
    email = EmailConfig(host="smtp.gmail.com", port=465, security="ssl",
                        username="user@gmail.com", password="app-password",
                        sender="user@gmail.com",
                        recipients=["a@b.com", "c@d.com"])
    email.save(settings)
    TelegramConfig(bot_token="123:XYZ", chat_id="987").save(settings)
    settings.sync()

    loaded = EmailConfig.from_settings(settings)
    assert loaded.host == "smtp.gmail.com" and loaded.port == 465
    assert loaded.security == "ssl" and loaded.password == "app-password"
    assert loaded.recipients == ["a@b.com", "c@d.com"]
    telegram = TelegramConfig.from_settings(settings)
    assert telegram.bot_token == "123:XYZ" and telegram.chat_id == "987"
    assert telegram.is_configured and loaded.is_configured


def test_from_settings_handles_missing_values(tmp_path):
    from PyQt6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "empty.ini"), QSettings.Format.IniFormat)
    email = EmailConfig.from_settings(settings)
    assert email.host == "" and email.port == 587 and email.recipients == []
    assert TelegramConfig.from_settings(settings).bot_token == ""
