"""اختبارات الشريط الجانبي: الصلاحيات، الأقسام الفارغة، و tooltips."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QPushButton                      # noqa: E402

from amdh_leave.models import AppUser                                      # noqa: E402
from amdh_leave.services import security as S                              # noqa: E402
from amdh_leave.ui.main_window import MainWindow                           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_sidebar_builds_without_error(qapp, ctx):
    """الشريط الجانبي يُبنى بدون أخطاء مع صلاحيات المدير."""
    window = MainWindow(ctx)
    try:
        sidebar = window._sidebar()
        assert sidebar is not None
        holder = sidebar.widget()
        assert holder is not None
        # التحقق من وجود أزرار
        layout = holder.layout()
        assert layout is not None
    finally:
        window.close()


def test_sidebar_hides_sections_without_permission(qapp, tmp_paths, db):
    """الأقسام التي لا يملك المستخدم صلاحية أي زر فيها تُخفى بالكامل."""
    from amdh_leave.context import AppContext
    from amdh_leave.services.backup import BackupService
    from PyQt6.QtCore import QSettings

    # مستخدم viewer لا يملك edit_employee ولا edit_leave
    viewer_session = S.make_session(AppUser(username="v", role="viewer"), False)
    viewer_ctx = AppContext(
        paths=tmp_paths, db=db,
        backup=BackupService(db, tmp_paths.backups_dir),
        session=viewer_session,
        settings=QSettings("MyCompany", "AMDH-Tests"),
    )
    window = MainWindow(viewer_ctx)
    try:
        sidebar = window._sidebar()
        holder = sidebar.widget()
        layout = holder.layout()

        # جمع كل العناصر في الـ layout
        items_text = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, QPushButton):
                    items_text.append(w.text())

        # زر "خروج" يجب أن يكون موجوداُ دائماُ
        assert any("خروج" in t for t in items_text)

        # أزرار تتطلب edit_employee يجب أن تكون مخفية
        assert not any("إضافة موظف" in t for t in items_text)
        assert not any("تعديل الموظف" in t for t in items_text)
        assert not any("حذف الموظف" in t for t in items_text)

        # أزرار تتطلب edit_leave يجب أن تكون مخفية
        assert not any("تسجيل إجازة" in t for t in items_text)

        # أزرار لا تتطلب صلاحية يجب أن تكون مرئية
        assert any("بطاقة الموظف" in t for t in items_text)
        assert any("سجل الإجازات" in t for t in items_text)
        assert any("الإعدادات" in t for t in items_text)
        assert any("حول" in t for t in items_text)
    finally:
        window.close()


def test_sidebar_section_titles_hidden_when_empty(qapp, tmp_paths, db):
    """عناوين الأقسام الفارغة لا تظهر في الـ layout."""
    from amdh_leave.context import AppContext
    from amdh_leave.services.backup import BackupService
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QLabel

    viewer_session = S.make_session(AppUser(username="v", role="viewer"), False)
    viewer_ctx = AppContext(
        paths=tmp_paths, db=db,
        backup=BackupService(db, tmp_paths.backups_dir),
        session=viewer_session,
        settings=QSettings("MyCompany", "AMDH-Tests"),
    )
    window = MainWindow(viewer_ctx)
    try:
        sidebar = window._sidebar()
        holder = sidebar.widget()
        layout = holder.layout()

        # جمع عناوين الأقسام المرئية
        section_labels = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, QLabel):
                    text = w.text()
                    # العناوين لها نمط معين
                    if "إدارة" in text or "الإجازات" in text or "التقارير" in text or "المؤسسات" in text or "عام" in text or "الأمان" in text:
                        section_labels.append(text)

        # قسم "إدارة الموظفين" يجب أن يظهر لأن viewer يملك بطاقة الموظف
        # لكن الأقسام التي كل أزرارها مخفية لا يجب أن تظهر
        # viewer يملك: بطاقة الموظف (بدون صلاحية) من قسم إدارة الموظفين
        # لذلك قسم إدارة الموظفين يجب أن يظهر
        assert "إدارة الموظفين" in section_labels

        # قسم الإجازات والدوام: viewer يملك سجل الإجازات وتقويم الإجازات
        assert "الإجازات والدوام" in section_labels
    finally:
        window.close()


def test_sidebar_tooltips_set(qapp, ctx):
    """الأزرار في الشريط الجانبي لها tooltips."""
    window = MainWindow(ctx)
    try:
        sidebar = window._sidebar()
        holder = sidebar.widget()
        layout = holder.layout()

        tooltips_found = 0
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, QPushButton):
                    tooltip = w.toolTip()
                    if tooltip:
                        tooltips_found += 1

        # يجب أن تكون معظم الأزرار لها tooltips
        assert tooltips_found > 10, f"فقط {tooltips_found} أزرار لها tooltips"
    finally:
        window.close()


def test_sidebar_width_is_dynamic(qapp, ctx):
    """عرض الشريط الجانبي ليس ثابتاً بل له حد أدنى وأقصى."""
    window = MainWindow(ctx)
    try:
        sidebar = window._sidebar()
        # التحقق من أن العرض ليس ثابتاً
        assert sidebar.minimumWidth() > 0
        assert sidebar.maximumWidth() > sidebar.minimumWidth()
        # الحد الأدنى 200 والحد الأقصى 280
        assert sidebar.minimumWidth() == 200
        assert sidebar.maximumWidth() == 280
    finally:
        window.close()


def test_sidebar_exit_button_always_visible(qapp, tmp_paths, db):
    """زر الخروج يظهر دائماً بغض النظر عن الصلاحيات."""
    from amdh_leave.context import AppContext
    from amdh_leave.services.backup import BackupService
    from PyQt6.QtCore import QSettings

    # مستخدم بدون أي صلاحيات
    empty_perms = S.Session(username="nobody", display_name="بدون صلاحيات",
                            role="viewer", permissions=set())
    viewer_ctx = AppContext(
        paths=tmp_paths, db=db,
        backup=BackupService(db, tmp_paths.backups_dir),
        session=empty_perms,
        settings=QSettings("MyCompany", "AMDH-Tests"),
    )
    window = MainWindow(viewer_ctx)
    try:
        sidebar = window._sidebar()
        holder = sidebar.widget()
        layout = holder.layout()

        items_text = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, QPushButton):
                    items_text.append(w.text())

        # زر الخروج يجب أن يكون موجوداً
        assert any("خروج" in t for t in items_text)
    finally:
        window.close()


def test_sidebar_editor_role_visibility(qapp, tmp_paths, db):
    """دور editor يرى أزرار مختلفة عن viewer."""
    from amdh_leave.context import AppContext
    from amdh_leave.services.backup import BackupService
    from PyQt6.QtCore import QSettings

    editor_session = S.make_session(AppUser(username="e", role="editor"), False)
    editor_ctx = AppContext(
        paths=tmp_paths, db=db,
        backup=BackupService(db, tmp_paths.backups_dir),
        session=editor_session,
        settings=QSettings("MyCompany", "AMDH-Tests"),
    )
    window = MainWindow(editor_ctx)
    try:
        sidebar = window._sidebar()
        holder = sidebar.widget()
        layout = holder.layout()

        items_text = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, QPushButton):
                    items_text.append(w.text())

        # editor يملك edit_employee
        assert any("إضافة موظف" in t for t in items_text)
        assert any("تعديل الموظف" in t for t in items_text)

        # editor يملك edit_leave
        assert any("تسجيل إجازة" in t for t in items_text)

        # editor لا يملك manage_users
        assert not any("المستخدمون" in t for t in items_text)
    finally:
        window.close()
