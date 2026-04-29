#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام إدارة الإجازات التراكمية - النسخة المتكاملة
مع: تقارير متقدمة، Dashboard، Light Mode، نسخ احتياطي تلقائي، دعم المؤسسات.
"""

import sys
import os, sqlite3, shutil
from datetime import date, datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QMessageBox, QFrame, QCheckBox, QDateEdit, 
    QTextEdit, QDialog, QFileDialog, QMenu, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QDate, QPoint, QSettings, QTimer
from PyQt6.QtGui import QFont, QColor, QIcon, QAction

# محاولة استيراد المكتبات المساعدة
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# =================== الثوابت والألوان ===================
DAYS_PER_LEAVE = 10
MAX_ANNUAL = 36

LEAVE_TYPES_MALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات", "كارت الزمنية"]
LEAVE_TYPES_FEMALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات",
                      "قبل الوضع", "بعد الوضع", "أمومة", "كارت الزمنية"]

UNIT_DAYS = {"يوم": 1, "شهر": 30, "سنة": 365}

C = {
    "bg": "#0F172A",
    "surface": "#1E293B",
    "card": "#334155",
    "accent": "#14B8A6",
    "blue": "#38BDF8",
    "warn": "#FBBF24",
    "text": "#F8FAFC",
    "muted": "#94A3B8",
    "border": "#475569",
    "neg": "#F87171",
    "gold": "#FBBF24",
}

# ستايل داكن
APP_STYLE = f"""
QWidget {{
    background-color: {C["bg"]};
    color: {C["text"]};
    font-family: 'Segoe UI', Arial;
    font-size: 10pt;
}}
QFrame#Card {{
    background-color: {C["card"]};
    border-radius: 8px;
    border: 1px solid {C["border"]};
}}
QFrame#Surface {{
    background-color: {C["surface"]};
}}
QLineEdit, QComboBox, QDateEdit, QTextEdit {{
    background-color: {C["surface"]};
    color: {C["text"]};
    border: 1px solid {C["border"]};
    border-radius: 6px;
    padding: 6px;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {{
    border: 1px solid {C["accent"]};
    outline: none;
}}
QPushButton {{
    font-weight: bold;
    padding: 8px 14px;
    border-radius: 6px;
    border: none;
}}
QPushButton#Accent {{ background-color: {C["accent"]}; color: #0F172A; }}
QPushButton#Accent:hover {{ background-color: #0D9488; }}
QPushButton#Blue {{ background-color: {C["blue"]}; color: #0F172A; }}
QPushButton#Blue:hover {{ background-color: #0284C7; }}
QPushButton#Warn {{ background-color: {C["neg"]}; color: white; }}
QPushButton#Warn:hover {{ background-color: #DC2626; }}
QPushButton#Gold {{ background-color: {C["gold"]}; color: #0F172A; }}
QPushButton#Gold:hover {{ background-color: #D97706; }}
QPushButton#Ghost {{ background-color: transparent; border: 1px solid {C["border"]}; color: {C["text"]}; }}
QPushButton#Ghost:hover {{ background-color: {C["surface"]}; }}

QTableWidget {{
    background-color: {C["surface"]};
    alternate-background-color: {C["card"]};
    border: 1px solid {C["border"]};
    gridline-color: {C["border"]};
    selection-background-color: {C["accent"]};
    selection-color: #0F172A;
}}
QHeaderView::section {{
    background-color: {C["surface"]};
    color: {C["muted"]};
    font-weight: bold;
    padding: 8px;
    border: none;
    border-right: 1px solid {C["border"]};
    border-bottom: 2px solid {C["border"]};
}}
QScrollBar:vertical {{
    background: {C["surface"]};
    width: 12px;
}}
QScrollBar::handle:vertical {{
    background: {C["border"]};
    border-radius: 6px;
}}
QScrollBar:horizontal {{
    background: {C["surface"]};
    height: 12px;
}}
QScrollBar::handle:horizontal {{
    background: {C["border"]};
    border-radius: 6px;
}}
QMenu {{
    background-color: {C["surface"]};
    color: {C["text"]};
    border: 1px solid {C["border"]};
    border-radius: 6px;
}}
QMenu::item {{
    padding: 6px 24px;
}}
QMenu::item:selected {{
    background-color: {C["accent"]};
    color: #0F172A;
}}
"""

# ستايل فاتح
LIGHT_STYLE = """
QWidget {
    background-color: #F1F5F9;
    color: #0F172A;
    font-family: 'Segoe UI', Arial;
    font-size: 10pt;
}
QFrame#Card {
    background-color: #FFFFFF;
    border-radius: 8px;
    border: 1px solid #CBD5E1;
}
QFrame#Surface {
    background-color: #E2E8F0;
}
QLineEdit, QComboBox, QDateEdit, QTextEdit {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px;
}
QPushButton {
    font-weight: bold;
    padding: 8px 14px;
    border-radius: 6px;
    border: none;
}
QPushButton#Accent { background-color: #0D9488; color: white; }
QPushButton#Accent:hover { background-color: #0F766E; }
QPushButton#Blue { background-color: #3B82F6; color: white; }
QPushButton#Blue:hover { background-color: #2563EB; }
QPushButton#Warn { background-color: #EF4444; color: white; }
QPushButton#Warn:hover { background-color: #DC2626; }
QPushButton#Gold { background-color: #F59E0B; color: white; }
QPushButton#Gold:hover { background-color: #D97706; }
QPushButton#Ghost { background-color: transparent; border: 1px solid #CBD5E1; color: #0F172A; }
QPushButton#Ghost:hover { background-color: #E2E8F0; }

QTableWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    border: 1px solid #CBD5E1;
    gridline-color: #E2E8F0;
    selection-background-color: #0D9488;
    selection-color: white;
}
QHeaderView::section {
    background-color: #F1F5F9;
    color: #475569;
    font-weight: bold;
    padding: 8px;
    border: none;
    border-right: 1px solid #CBD5E1;
    border-bottom: 2px solid #CBD5E1;
}
QMenu {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
}
QMenu::item:selected {
    background-color: #0D9488;
    color: white;
}
"""

# =================== دوال المساعدة ===================
def days_since(start_date_str: str) -> int:
    try:
        sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        return max(0, (date.today() - sd).days)
    except:
        return 0

def earned_from_days(net_days: int) -> int:
    return net_days // DAYS_PER_LEAVE

def total_leave_days(leaves: list) -> int:
    total = 0
    for lv in leaves:
        if not lv.get("outside_balance", False):
            total += lv.get("days_actual", lv.get("days", 0))
    return total

def leave_days_outside(leaves: list) -> int:
    total = 0
    for lv in leaves:
        if lv.get("outside_balance", False):
            total += lv.get("days_actual", lv.get("days", 0))
    return total

def compute_balance(emp: dict) -> dict:
    start    = emp.get("start_date", "")
    leaves   = emp.get("history", [])
    raw_days = days_since(start)
    outside  = leave_days_outside(leaves)
    net_days = max(0, raw_days - outside)
    earned   = earned_from_days(net_days)
    taken    = total_leave_days(leaves)
    balance  = earned - taken
    return {
        "raw_days":  raw_days,
        "outside":   outside,
        "net_days":  net_days,
        "earned":    earned,
        "taken":     taken,
        "balance":   balance,
    }

def unit_to_days(amount: int, unit: str) -> int:
    return amount * UNIT_DAYS.get(unit, 1)

def safe_parse_date(date_str: str):
    """تحويل النص إلى كائن date مع التحقق من الأخطاء"""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        return None

# =================== قاعدة البيانات مع دعم المؤسسات ===================
class DB:
    def __init__(self):
        self.db_path = "employees_leave.db"
        self._init_db()
        self._migrate_json_to_sqlite()
        self._upgrade_db()

    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = 1")
        return conn

    def _init_db(self):
        with self.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    emp_id TEXT PRIMARY KEY,
                    name TEXT,
                    job_title TEXT,
                    workplace TEXT,
                    gender TEXT,
                    start_date TEXT,
                    notes TEXT,
                    institution TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leaves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    emp_id TEXT,
                    type TEXT,
                    start_date TEXT,
                    from_date TEXT,
                    amount INTEGER,
                    unit TEXT,
                    days_actual INTEGER,
                    order_num TEXT,
                    order_date TEXT,
                    outside_balance INTEGER,
                    reason TEXT,
                    added_date TEXT,
                    FOREIGN KEY(emp_id) REFERENCES employees(emp_id) ON DELETE CASCADE
                )
            """)

    def _upgrade_db(self):
        with self.get_conn() as conn:
            try:
                conn.execute("ALTER TABLE employees ADD COLUMN institution TEXT")
            except sqlite3.OperationalError:
                pass

    def _migrate_json_to_sqlite(self):
        json_file = "employees_leave.json"
        if os.path.exists(json_file):
            import json
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    for eid, fields in data.items():
                        if not self.get(eid):
                            self.add(eid, fields)
                            for lv in fields.get("history", []):
                                self.add_leave(eid, lv)
                os.rename(json_file, "employees_leave_backup_migrated.json")
                print("تم ترحيل البيانات بنجاح من JSON إلى SQLite")
            except Exception as e:
                print("Migration error:", e)

    def add(self, emp_id, fields: dict):
        with self.get_conn() as conn:
            conn.execute("INSERT INTO employees (emp_id, name, job_title, workplace, gender, start_date, notes, institution) VALUES (?,?,?,?,?,?,?,?)",
                      (emp_id, fields.get('name'), fields.get('job_title'), fields.get('workplace'), fields.get('gender'), fields.get('start_date'), fields.get('notes'), fields.get('institution', '')))

    def update(self, emp_id, fields: dict):
        with self.get_conn() as conn:
            conn.execute("UPDATE employees SET name=?, job_title=?, workplace=?, gender=?, start_date=?, notes=?, institution=? WHERE emp_id=?",
                      (fields.get('name'), fields.get('job_title'), fields.get('workplace'), fields.get('gender'), fields.get('start_date'), fields.get('notes'), fields.get('institution', ''), emp_id))

    def delete(self, emp_id):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM employees WHERE emp_id=?", (emp_id,))

    def get(self, emp_id):
        with self.get_conn() as conn:
            row = conn.execute("SELECT * FROM employees WHERE emp_id=?", (emp_id,)).fetchone()
            if not row: return None
            emp = dict(row)
            leaves_rows = conn.execute("SELECT * FROM leaves WHERE emp_id=? ORDER BY id ASC", (emp_id,)).fetchall()
            leaves = []
            for r in leaves_rows:
                l = dict(r)
                l['outside_balance'] = bool(l['outside_balance'])
                l['order'] = l.pop('order_num', '')
                leaves.append(l)
            emp['history'] = leaves
            return emp

    def add_leave(self, emp_id, record: dict):
        with self.get_conn() as conn:
            conn.execute("""INSERT INTO leaves (emp_id, type, start_date, from_date, amount, unit, days_actual, order_num, order_date, outside_balance, reason, added_date)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (emp_id, record.get('type'), record.get('start_date'), record.get('from_date'),
                       record.get('amount'), record.get('unit'), record.get('days_actual'),
                       record.get('order'), record.get('order_date'), int(record.get('outside_balance', False)),
                       record.get('reason'), record.get('added_date')))

    def delete_leave(self, emp_id, leave_idx):
        emp = self.get(emp_id)
        if emp and leave_idx < len(emp['history']):
            real_id = emp['history'][leave_idx]['id']
            with self.get_conn() as conn:
                conn.execute("DELETE FROM leaves WHERE id=?", (real_id,))

    def update_leave(self, emp_id, leave_idx, record: dict):
        emp = self.get(emp_id)
        if emp and leave_idx < len(emp['history']):
            real_id = emp['history'][leave_idx]['id']
            with self.get_conn() as conn:
                conn.execute("""UPDATE leaves SET type=?, start_date=?, from_date=?, amount=?, unit=?, days_actual=?, order_num=?, order_date=?, outside_balance=?, reason=?, added_date=? WHERE id=?""",
                          (record.get('type'), record.get('start_date'), record.get('from_date'),
                           record.get('amount'), record.get('unit'), record.get('days_actual'),
                           record.get('order'), record.get('order_date'), int(record.get('outside_balance', False)),
                           record.get('reason'), record.get('added_date'), real_id))

    def search(self, q="", workplace_filter="", institution_filter=""):
        with self.get_conn() as conn:
            conditions = []
            params = []
            if q:
                conditions.append("(emp_id LIKE ? OR name LIKE ?)")
                like_q = f"%{q}%"
                params.extend([like_q, like_q])
            if workplace_filter:
                conditions.append("workplace LIKE ?")
                params.append(f"%{workplace_filter}%")
            if institution_filter:
                conditions.append("institution LIKE ?")
                params.append(f"%{institution_filter}%")
            
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            
            query = f"SELECT * FROM employees {where_clause}"
            emps = conn.execute(query, params).fetchall()
            if not emps: return {}
            emp_dict = {e['emp_id']: dict(e) for e in emps}
            for e in emp_dict.values():
                e['history'] = []
            ids = tuple(emp_dict.keys())
            if ids:
                placeholders = ','.join(['?'] * len(ids))
                leaves_rows = conn.execute(f"SELECT * FROM leaves WHERE emp_id IN ({placeholders}) ORDER BY id ASC", ids).fetchall()
                for r in leaves_rows:
                    eid = r['emp_id']
                    if eid in emp_dict:
                        l = dict(r)
                        l['outside_balance'] = bool(l['outside_balance'])
                        l['order'] = l.pop('order_num', '')
                        emp_dict[eid]['history'].append(l)
            return emp_dict

    def all(self):
        return self.search()

db = DB()

# =================== BaseDialog ===================
class BaseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(QApplication.instance().styleSheet())

# =================== نافذة حول ===================
class AboutDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("حول النظام")
        self.resize(400, 300)
        layout = QVBoxLayout(self)
        lbl = QLabel("""
        نظام إدارة الإجازات التراكمية
        الإصدار: 2.0 (نسخة متكاملة)
        
        تم التطوير باستخدام PyQt6
        يدعم إدارة الموظفين والإجازات والتقارير
        الإشعارات الذكية، الوضع الفاتح/الداكن، النسخ الاحتياطي التلقائي
        """)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

# =================== نافذة الإعدادات ===================
class SettingsDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الإعدادات")
        self.resize(400, 250)
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.chk_notifications = QCheckBox("تفعيل الإشعارات عند بدء التشغيل")
        self.chk_backup = QCheckBox("نسخ احتياطي تلقائي عند الإغلاق")
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(["داكن", "فاتح"])
        form_layout.addRow("الإشعارات", self.chk_notifications)
        form_layout.addRow("النسخ الاحتياطي", self.chk_backup)
        form_layout.addRow("الوضع", self.cmb_theme)
        layout.addLayout(form_layout)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        self._load_settings()

    def _load_settings(self):
        settings = QSettings("MyCompany", "LeaveSystem")
        self.chk_notifications.setChecked(settings.value("notifications", True, type=bool))
        self.chk_backup.setChecked(settings.value("auto_backup", False, type=bool))
        theme = settings.value("theme", "داكن")
        idx = self.cmb_theme.findText(theme)
        if idx >= 0:
            self.cmb_theme.setCurrentIndex(idx)

    def _save(self):
        settings = QSettings("MyCompany", "LeaveSystem")
        settings.setValue("notifications", self.chk_notifications.isChecked())
        settings.setValue("auto_backup", self.chk_backup.isChecked())
        settings.setValue("theme", self.cmb_theme.currentText())
        app = QApplication.instance()
        if self.cmb_theme.currentText() == "فاتح":
            app.setStyleSheet(LIGHT_STYLE)
        else:
            app.setStyleSheet(APP_STYLE)
        QMessageBox.information(self, "تم", "تم حفظ الإعدادات.")
        self.accept()

def create_date_edit():
    de = QDateEdit()
    de.setCalendarPopup(True)
    de.setDisplayFormat("yyyy-MM-dd")
    de.setDate(QDate.currentDate())
    return de

# =================== حوار الموظف (مع institution) ===================
class EmployeeDialog(BaseDialog):
    def __init__(self, parent=None, emp_id=None, on_save=None):
        super().__init__(parent)
        self.emp_id = emp_id
        self.on_save = on_save
        self.edit_mode = emp_id is not None
        self.setWindowTitle("تعديل موظف" if self.edit_mode else "إضافة موظف جديد")
        self.resize(500, 650)
        self._build()
        if self.edit_mode:
            self._load_emp()
    def _build(self):
        main_layout = QVBoxLayout(self)
        title = QLabel("تعديل بيانات الموظف" if self.edit_mode else "إضافة موظف جديد")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C['accent']}; padding: 10px;")
        main_layout.addWidget(title)
        form_frame = QFrame()
        form_frame.setObjectName("Card")
        form_layout = QFormLayout(form_frame)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(15)
        self.e_id = QLineEdit()
        self.e_name = QLineEdit()
        self.e_title = QLineEdit()
        self.e_workplace = QLineEdit()
        self.e_institution = QLineEdit()
        self.cb_gender = QComboBox()
        self.cb_gender.addItems(["ذكر", "أنثى"])
        self.e_start = create_date_edit()
        self.e_notes = QTextEdit()
        self.e_notes.setFixedHeight(80)
        form_layout.addRow("الرقم الوظيفي *", self.e_id)
        form_layout.addRow("الاسم الكامل *", self.e_name)
        form_layout.addRow("العنوان الوظيفي", self.e_title)
        form_layout.addRow("مكان العمل", self.e_workplace)
        form_layout.addRow("المؤسسة / القسم", self.e_institution)
        form_layout.addRow("الجنس", self.cb_gender)
        form_layout.addRow("تاريخ المباشرة *", self.e_start)
        form_layout.addRow("ملاحظات", self.e_notes)
        if self.edit_mode:
            self.e_id.setEnabled(False)
        main_layout.addWidget(form_frame)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("إلغاء")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("حفظ")
        save_btn.setObjectName("Accent")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        main_layout.addLayout(btn_layout)
    def _load_emp(self):
        emp = db.get(self.emp_id)
        if not emp: return
        self.e_id.setText(self.emp_id)
        self.e_name.setText(emp.get("name", ""))
        self.e_title.setText(emp.get("job_title", ""))
        self.e_workplace.setText(emp.get("workplace", ""))
        self.e_institution.setText(emp.get("institution", ""))
        self.cb_gender.setCurrentText(emp.get("gender", "ذكر"))
        if emp.get("start_date", ""):
            self.e_start.setDate(QDate.fromString(emp["start_date"], "yyyy-MM-dd"))
        self.e_notes.setPlainText(emp.get("notes", ""))
    def _save(self):
        eid = self.e_id.text().strip() if not self.edit_mode else self.emp_id
        name = self.e_name.text().strip()
        start = self.e_start.date().toString("yyyy-MM-dd")
        if not eid or not name:
            QMessageBox.warning(self, "تنبيه", "الرقم الوظيفي والاسم إلزاميان.")
            return
        if not self.edit_mode and db.get(eid):
            QMessageBox.warning(self, "تنبيه", "الرقم الوظيفي مسجل مسبقاً.")
            return
        fields = {
            "name": name,
            "job_title": self.e_title.text().strip(),
            "workplace": self.e_workplace.text().strip(),
            "institution": self.e_institution.text().strip(),
            "gender": self.cb_gender.currentText(),
            "start_date": start,
            "notes": self.e_notes.toPlainText().strip(),
        }
        if self.edit_mode:
            db.update(eid, fields)
        else:
            db.add(eid, fields)
        if self.on_save: self.on_save()
        self.accept()

# =================== باقي الحوارات الأساسية ===================
# =================== حوار الإجازة (إضافة/تعديل) ===================
class LeaveDialog(BaseDialog):
    def __init__(self, parent=None, emp_id=None, leave_idx=None, on_save=None):
        super().__init__(parent)
        self.emp_id = emp_id
        self.leave_idx = leave_idx
        self.on_save = on_save
        self.edit_mode = leave_idx is not None
        emp = db.get(emp_id)
        self.gender = emp.get("gender", "ذكر") if emp else "ذكر"
        self.setWindowTitle("تعديل إجازة" if self.edit_mode else "إضافة إجازة")
        self.resize(400, 500)
        self._build()
        if self.edit_mode:
            self._load()
    def _build(self):
        main_layout = QVBoxLayout(self)
        title = QLabel("بيانات الإجازة")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C['accent']}; padding: 10px;")
        main_layout.addWidget(title)
        form_frame = QFrame()
        form_frame.setObjectName("Card")
        form_layout = QFormLayout(form_frame)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        ltypes = LEAVE_TYPES_FEMALE if self.gender == "أنثى" else LEAVE_TYPES_MALE
        self.cb_type = QComboBox()
        self.cb_type.addItems(ltypes)
        amount_layout = QHBoxLayout()
        self.e_amount = QLineEdit()
        self.cb_unit = QComboBox()
        self.cb_unit.addItems(["يوم", "شهر", "سنة"])
        amount_layout.addWidget(self.e_amount)
        amount_layout.addWidget(self.cb_unit)
        self.e_start_date = create_date_edit()
        self.e_order = QLineEdit()
        self.e_order_date = create_date_edit()
        self.cb_outside = QCheckBox("هل يتم احتساب الخدمة أيام الإجازة خارج الرصيد؟")
        self.e_reason = QLineEdit()
        form_layout.addRow("نوع الإجازة", self.cb_type)
        form_layout.addRow("العدد والوحدة", amount_layout)
        form_layout.addRow("بدءاً من تاريخ", self.e_start_date)
        form_layout.addRow("الأمر (اختياري)", self.e_order)
        form_layout.addRow("تاريخ الأمر (اختياري)", self.e_order_date)
        form_layout.addRow("", self.cb_outside)
        form_layout.addRow("السبب / الملاحظة", self.e_reason)
        main_layout.addWidget(form_frame)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("إلغاء")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("حفظ")
        save_btn.setObjectName("Accent")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        main_layout.addLayout(btn_layout)
    def _load(self):
        emp = db.get(self.emp_id)
        lv = emp["history"][self.leave_idx]
        self.cb_type.setCurrentText(lv.get("type", ""))
        self.e_amount.setText(str(lv.get("amount", "")))
        self.cb_unit.setCurrentText(lv.get("unit", "يوم"))
        sd = lv.get("start_date", lv.get("from_date", ""))
        if sd: self.e_start_date.setDate(QDate.fromString(sd, "yyyy-MM-dd"))
        self.e_order.setText(lv.get("order", ""))
        od = lv.get("order_date", "")
        if od: self.e_order_date.setDate(QDate.fromString(od, "yyyy-MM-dd"))
        self.cb_outside.setChecked(lv.get("outside_balance", False))
        self.e_reason.setText(lv.get("reason", ""))
    def _save(self):
        ltype = self.cb_type.currentText()
        amount_s = self.e_amount.text().strip()
        unit = self.cb_unit.currentText()
        start_d = self.e_start_date.date().toString("yyyy-MM-dd")
        if not amount_s:
            QMessageBox.warning(self, "تنبيه", "أدخل العدد.")
            return
        try:
            amount = int(amount_s)
            days_actual = unit_to_days(amount, unit)
        except:
            QMessageBox.warning(self, "تنبيه", "أدخل عدداً صحيحاً للعدد.")
            return
        record = {
            "type": ltype,
            "start_date": start_d,
            "from_date": start_d,
            "amount": amount,
            "unit": unit,
            "days_actual": days_actual,
            "order": self.e_order.text().strip(),
            "order_date": self.e_order_date.date().toString("yyyy-MM-dd"),
            "outside_balance": self.cb_outside.isChecked(),
            "reason": self.e_reason.text().strip(),
            "added_date": str(date.today()),
        }
        if self.edit_mode:
            db.update_leave(self.emp_id, self.leave_idx, record)
        else:
            db.add_leave(self.emp_id, record)
        if self.on_save: self.on_save()
        self.accept()

# =================== حوار إضافة إجازة سريع (مستقل) ===================
class LeaveQuickDialog(BaseDialog):
    def __init__(self, parent=None, emp_id=None, on_save=None):
        super().__init__(parent)
        self.emp_id = emp_id
        self.on_save = on_save
        emp = db.get(emp_id)
        if not emp:
            QMessageBox.critical(self, "خطأ", "الموظف غير موجود")
            self.reject()
            return
        self.emp_name = emp.get("name", "")
        self.emp_title = emp.get("job_title", "")
        self.gender = emp.get("gender", "ذكر")
        self.setWindowTitle(f"تسجيل إجازة - {self.emp_name} ({self.emp_title})")
        self.resize(500, 600)
        self._build()
    def _build(self):
        layout = QVBoxLayout(self)
        title = QLabel(f"تسجيل إجازة للموظف: {self.emp_name}\nالعنوان الوظيفي: {self.emp_title}")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {C['accent']}; margin-bottom: 10px;")
        layout.addWidget(title)
        form_frame = QFrame()
        form_frame.setObjectName("Card")
        form_layout = QFormLayout(form_frame)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(15)
        ltypes = LEAVE_TYPES_FEMALE if self.gender == "أنثى" else LEAVE_TYPES_MALE
        self.cb_type = QComboBox()
        self.cb_type.addItems(ltypes)
        amount_layout = QHBoxLayout()
        self.e_amount = QLineEdit()
        self.cb_unit = QComboBox()
        self.cb_unit.addItems(["يوم", "شهر", "سنة"])
        amount_layout.addWidget(self.e_amount)
        amount_layout.addWidget(self.cb_unit)
        self.e_start_date = create_date_edit()
        self.e_order = QLineEdit()
        self.e_order_date = create_date_edit()
        self.cb_outside = QCheckBox("هل يتم احتساب الخدمة (أيام خارج الرصيد)؟")
        self.e_reason = QLineEdit()
        form_layout.addRow("نوع الإجازة", self.cb_type)
        form_layout.addRow("العدد والوحدة", amount_layout)
        form_layout.addRow("بدءاً من تاريخ", self.e_start_date)
        form_layout.addRow("الأمر (اختياري)", self.e_order)
        form_layout.addRow("تاريخ الأمر (اختياري)", self.e_order_date)
        form_layout.addRow("", self.cb_outside)
        form_layout.addRow("السبب / الملاحظة", self.e_reason)
        layout.addWidget(form_frame)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("إلغاء")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("حفظ الإجازة")
        save_btn.setObjectName("Accent")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
    def _save(self):
        ltype = self.cb_type.currentText()
        amount_s = self.e_amount.text().strip()
        unit = self.cb_unit.currentText()
        start_d = self.e_start_date.date().toString("yyyy-MM-dd")

        if not amount_s:
            QMessageBox.warning(self, "تنبيه", "أدخل العدد.")
            return
        try:
            amount = int(amount_s)
            days_actual = unit_to_days(amount, unit)
        except:
            QMessageBox.warning(self, "تنبيه", "أدخل عدداً صحيحاً للعدد.")
            return

        emp = db.get(self.emp_id)
        b = compute_balance(emp)
        if days_actual > b["balance"] and not self.cb_outside.isChecked():
            reply = QMessageBox.question(self, "تجاوز الرصيد", f"الرصيد المتاح: {b['balance']} يوم.\nهل تريد المتابعة (تسجيل إجازة خارج الرصيد)؟",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.cb_outside.setChecked(True)

        record = {
            "type": ltype,
            "start_date": start_d,
            "from_date": start_d,
            "amount": amount,
            "unit": unit,
            "days_actual": days_actual,
            "order": self.e_order.text().strip(),
            "order_date": self.e_order_date.date().toString("yyyy-MM-dd"),
            "outside_balance": self.cb_outside.isChecked(),
            "reason": self.e_reason.text().strip(),
            "added_date": str(date.today()),
        }
        db.add_leave(self.emp_id, record)
        if self.on_save:
            self.on_save()
        
        # تحديث الإشعارات في النافذة الرئيسية (بدون عرضها)
        parent_window = self.parent()
        if parent_window and hasattr(parent_window, 'check_notifications'):
            parent_window.check_notifications(show_message=False)
        
        self.accept()

# =================== حوار عمليات قاعدة البيانات ===================
class DatabaseOperationsDialog(BaseDialog):
    def __init__(self, parent=None, refresh_callback=None):
        super().__init__(parent)
        self.refresh_callback = refresh_callback
        self.setWindowTitle("عمليات قاعدة البيانات")
        self.resize(450, 300)
        self._build()
    def _build(self):
        layout = QVBoxLayout(self)
        title = QLabel("إدارة قاعدة البيانات")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {C['accent']};")
        layout.addWidget(title)
        btn_export = QPushButton("📀 تصدير قاعدة البيانات (DB)")
        btn_export.setObjectName("Blue")
        btn_export.clicked.connect(self._export_db)
        layout.addWidget(btn_export)
        btn_import = QPushButton("📂 استيراد قاعدة البيانات (دمج)")
        btn_import.setObjectName("Gold")
        btn_import.clicked.connect(self._import_db)
        layout.addWidget(btn_import)
        btn_template = QPushButton("📄 تصدير قالب Excel للموظفين")
        btn_template.setObjectName("Ghost")
        btn_template.clicked.connect(self._export_template)
        layout.addWidget(btn_template)
        btn_import_excel = QPushButton("📊 استيراد موظفين من Excel")
        btn_import_excel.setObjectName("Ghost")
        btn_import_excel.clicked.connect(self._import_excel)
        layout.addWidget(btn_import_excel)
        layout.addStretch()
    def _export_db(self):
        path, _ = QFileDialog.getSaveFileName(self, "تصدير قاعدة البيانات", "employees_backup.db", "Database Files (*.db)")
        if not path: return
        try:
            shutil.copy2("employees_leave.db", path)
            QMessageBox.information(self, "نجاح", f"تم تصدير قاعدة البيانات إلى:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل التصدير: {e}")
    def _import_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "استيراد قاعدة البيانات", "", "Database Files (*.db)")
        if not path: return
        try:
            with sqlite3.connect(path) as imported_conn:
                imported_conn.row_factory = sqlite3.Row
                ic = imported_conn.cursor()
                ic.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees'")
                if not ic.fetchone():
                    QMessageBox.critical(self, "خطأ", "الملف المحدد لا يحتوي على جدول الموظفين.")
                    return
                ic.execute("SELECT * FROM employees")
                imported_emps = ic.fetchall()
                added, updated, skipped = 0, 0, 0
                for imp_emp in imported_emps:
                    eid = imp_emp['emp_id']
                    ic.execute("SELECT * FROM leaves WHERE emp_id=? ORDER BY id ASC", (eid,))
                    imp_leaves = ic.fetchall()
                    existing = db.get(eid)
                    if existing:
                        reply = QMessageBox.question(self, "تعارض", f"الموظف {imp_emp['name']} ({eid}) موجود. استبدال؟",
                                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                        if reply == QMessageBox.StandardButton.Cancel:
                            break
                        elif reply == QMessageBox.StandardButton.Yes:
                            db.delete(eid)
                            self._insert_emp(imp_emp, imp_leaves)
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        self._insert_emp(imp_emp, imp_leaves)
                        added += 1
                QMessageBox.information(self, "اكتمل", f"تمت الإضافة: {added}\nتحديث: {updated}\nتخطي: {skipped}")
                if self.refresh_callback:
                    self.refresh_callback()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"خطأ في الاستيراد: {e}")
    def _insert_emp(self, imp_emp, imp_leaves):
        db.add(imp_emp['emp_id'], dict(imp_emp))
        for lv in imp_leaves:
            lv_dict = dict(lv)
            lv_dict['order'] = lv_dict.pop('order_num', '')
            db.add_leave(imp_emp['emp_id'], lv_dict)
    def _export_template(self):
        if not HAS_XLSX:
            QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ قالب Excel", "template.xlsx", "Excel Files (*.xlsx)")
        if not path: return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["emp_id","name","job_title","workplace","institution","gender","start_date"])
        ws['A1'].font = Font(bold=True)
        wb.save(path)
        QMessageBox.information(self, "تم", f"تم حفظ القالب في:\n{path}")
    def _import_excel(self):
        if not HAS_XLSX:
            QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "اختر ملف Excel", "", "Excel Files (*.xlsx)")
        if not path: return
        try:
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            added = 0
            skipped = 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                eid = str(row[0]) if row[0] else ""
                if not eid:
                    continue
                if db.get(eid):
                    skipped += 1
                    continue
                db.add(eid, {
                    "name": row[1] if row[1] else "",
                    "job_title": row[2] if row[2] else "",
                    "workplace": row[3] if row[3] else "",
                    "institution": row[4] if row[4] else "",
                    "gender": row[5] if row[5] in ["ذكر", "أنثى"] else "ذكر",
                    "start_date": row[6] if row[6] else str(date.today()),
                    "notes": ""
                })
                added += 1
            QMessageBox.information(self, "اكتمل", f"تم استيراد {added} موظف جديد.\nتخطي (موجود مسبقاً): {skipped}")
            if self.refresh_callback:
                self.refresh_callback()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل الاستيراد: {e}")

# =================== حوار تعديل الموظف (اختيار تعديل معلومات أو إجازات) ===================
class EditEmployeeDialog(BaseDialog):
    def __init__(self, parent=None, emp_id=None, on_save=None):
        super().__init__(parent)
        self.emp_id = emp_id
        self.on_save = on_save
        emp = db.get(emp_id)
        self.setWindowTitle(f"خيارات التعديل")
        self.resize(350, 200)
        layout = QVBoxLayout(self)
        title = QLabel(f"تعديل: {emp.get('name','')}")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(20)
        btn_info = QPushButton("📋  المعلومات العامة")
        btn_info.setObjectName("Blue")
        btn_info.clicked.connect(self._open_info)
        layout.addWidget(btn_info)
        btn_leaves = QPushButton("📅  سجل الإجازات")
        btn_leaves.setObjectName("Accent")
        btn_leaves.clicked.connect(self._open_leaves)
        layout.addWidget(btn_leaves)
    def _open_info(self):
        self.accept()
        dlg = EmployeeDialog(self.parent(), emp_id=self.emp_id, on_save=self.on_save)
        dlg.exec()
    def _open_leaves(self):
        self.accept()
        dlg = LeavesRegisterDialog(self.parent(), self.emp_id, on_save=self.on_save)
        dlg.exec()

# =================== سجل الإجازات (نافذة منفصلة) ===================
class LeavesRegisterDialog(BaseDialog):
    def __init__(self, parent=None, emp_id=None, on_save=None):
        super().__init__(parent)
        self.emp_id = emp_id
        self.on_save = on_save
        emp = db.get(emp_id)
        self.setWindowTitle(f"سجل إجازات: {emp.get('name','')}")
        self.resize(1000, 500)
        self._build()
        self._refresh()
    def _build(self):
        layout = QVBoxLayout(self)
        emp = db.get(self.emp_id)
        title = QLabel(f"سجل إجازات: {emp.get('name','')}")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C['accent']};")
        layout.addWidget(title)
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("➕ إضافة إجازة")
        btn_add.setObjectName("Accent")
        btn_add.clicked.connect(self._add)
        btn_edit = QPushButton("✏ تعديل المحددة")
        btn_edit.setObjectName("Blue")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("🗑 حذف المحددة")
        btn_del.setObjectName("Warn")
        btn_del.clicked.connect(self._delete)
        btn_excel = QPushButton("📊 تصدير Excel")
        btn_excel.setObjectName("Ghost")
        btn_excel.clicked.connect(self._export_xlsx)
        btn_pdf = QPushButton("📄 تصدير PDF")
        btn_pdf.setObjectName("Ghost")
        btn_pdf.clicked.connect(self._export_pdf)
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_del)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_excel)
        btn_layout.addWidget(btn_pdf)
        layout.addLayout(btn_layout)
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.cols = ["#", "النوع", "بدءاً من", "العدد", "الوحدة", "الأيام الفعلية", "خارج الرصيد", "الأمر", "تاريخ الأمر", "السبب", "تاريخ الإضافة"]
        self.table.setColumnCount(len(self.cols))
        self.table.setHorizontalHeaderLabels(self.cols)
        layout.addWidget(self.table)
    def _refresh(self):
        self.table.setRowCount(0)
        emp = db.get(self.emp_id)
        history = emp.get("history", [])
        self.table.setRowCount(len(history))
        for i, lv in enumerate(history):
            self.table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self.table.setItem(i, 1, QTableWidgetItem(lv.get("type","")))
            self.table.setItem(i, 2, QTableWidgetItem(lv.get("start_date", lv.get("from_date",""))))
            self.table.setItem(i, 3, QTableWidgetItem(str(lv.get("amount",""))))
            self.table.setItem(i, 4, QTableWidgetItem(lv.get("unit","يوم")))
            self.table.setItem(i, 5, QTableWidgetItem(str(lv.get("days_actual",0))))
            self.table.setItem(i, 6, QTableWidgetItem("نعم" if lv.get("outside_balance") else "لا"))
            self.table.setItem(i, 7, QTableWidgetItem(lv.get("order","")))
            self.table.setItem(i, 8, QTableWidgetItem(lv.get("order_date","")))
            self.table.setItem(i, 9, QTableWidgetItem(lv.get("reason","")))
            self.table.setItem(i, 10, QTableWidgetItem(lv.get("added_date","")))
        self.table.resizeColumnsToContents()
    def _sel_idx(self):
        row = self.table.currentRow()
        return row if row >= 0 else None
    def _add(self):
        dlg = LeaveDialog(self, self.emp_id, on_save=self._refresh_and_notify)
        dlg.exec()
    def _edit(self):
        idx = self._sel_idx()
        if idx is None:
            QMessageBox.warning(self, "تنبيه", "حدد إجازة.")
            return
        dlg = LeaveDialog(self, self.emp_id, leave_idx=idx, on_save=self._refresh_and_notify)
        dlg.exec()
    def _delete(self):
        idx = self._sel_idx()
        if idx is None:
            QMessageBox.warning(self, "تنبيه", "حدد إجازة.")
            return
        reply = QMessageBox.question(self, "تأكيد", "حذف هذه الإجازة؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_leave(self.emp_id, idx)
            self._refresh_and_notify()
    def _refresh_and_notify(self):
        self._refresh()
        if self.on_save: self.on_save()
    def _export_xlsx(self):
        if not HAS_XLSX:
            QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ Excel", "", "Excel Files (*.xlsx)")
        if not path: return
        emp = db.get(self.emp_id)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "سجل الإجازات"
        ws.sheet_view.rightToLeft = True
        ws.append(self.cols)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="00C896")
            cell.fill = PatternFill("solid", fgColor="1C2D3E")
        for i,lv in enumerate(emp.get("history",[])):
            ws.append([i+1, lv.get("type",""), lv.get("start_date", lv.get("from_date","")),
                       lv.get("amount",""), lv.get("unit",""), lv.get("days_actual",0),
                       "نعم" if lv.get("outside_balance") else "لا",
                       lv.get("order",""), lv.get("order_date",""),
                       lv.get("reason",""), lv.get("added_date","")])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 15
        wb.save(path)
        QMessageBox.information(self, "تم", f"تم التصدير:\n{path}")
    def _export_pdf(self):
        if not HAS_PDF:
            QMessageBox.critical(self, "خطأ", "reportlab غير مثبت.")
            return
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
        except ImportError:
            QMessageBox.critical(self, "خطأ", "لتصدير PDF باللغة العربية، يرجى تثبيت:\npip install arabic-reshaper python-bidi")
            return
        try:
            pdfmetrics.registerFont(TTFont('ArabicFont', 'arial.ttf'))
        except Exception:
            QMessageBox.critical(self, "خطأ", "لم يتم العثور على خط Arial في النظام.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PDF", "", "PDF Files (*.pdf)")
        if not path: return
        def ar(text):
            if not text: return ""
            reshaped_text = arabic_reshaper.reshape(str(text))
            bidi_text = get_display(reshaped_text)
            return bidi_text
        emp = db.get(self.emp_id)
        doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(name='ArabicTitle', parent=styles['Title'], fontName='ArabicFont', fontSize=16, alignment=1)
        info_style = ParagraphStyle(name='ArabicInfo', parent=styles['Normal'], fontName='ArabicFont', fontSize=12, alignment=1)
        story = []
        story.append(Paragraph(ar(f"سجل إجازات: {emp.get('job_title', '')} - {emp.get('name', '')}"), title_style))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(ar(f"الرقم الوظيفي: {self.emp_id} ، مكان العمل: {emp.get('workplace', '')}"), info_style))
        story.append(Spacer(1, 0.3*cm))
        headers = [ar(c) for c in reversed(self.cols)]
        data = [headers]
        for i,lv in enumerate(emp.get("history",[])):
            row = [
                ar(lv.get("added_date","")), ar(lv.get("reason","")), ar(lv.get("order_date","")),
                ar(lv.get("order","")), ar("نعم" if lv.get("outside_balance") else "لا"),
                ar(str(lv.get("days_actual",0))), ar(lv.get("unit","")), ar(str(lv.get("amount",""))),
                ar(lv.get("start_date", lv.get("from_date",""))), ar(lv.get("type","")), ar(str(i+1))
            ]
            data.append(row)
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#1C2D3E")),
            ("TEXTCOLOR",  (0,0),(-1,0), colors.HexColor("#00C896")),
            ("FONTNAME",   (0,0),(-1,-1),"ArabicFont"),
            ("GRID",       (0,0),(-1,-1), 0.5, colors.grey),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f5f5f5")]),
            ("ALIGN",      (0,0),(-1,-1),"CENTER"),
        ]))
        story.append(t)
        doc.build(story)
        QMessageBox.information(self, "تم", f"تم التصدير بنجاح:\n{path}")

# =================== دوال التقارير والإشعارات ===================
def generate_global_report():
    report = []
    for eid, emp in db.all().items():
        b = compute_balance(emp)
        report.append({
            "name": emp["name"],
            "earned": b["earned"],
            "taken": b["taken"],
            "balance": b["balance"]
        })
    return report

def export_html_report(data):
    if not data:
        QMessageBox.information(None, "معلومات", "لا توجد بيانات للتصدير.")
        return
    html = """<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="UTF-8"><title>تقرير الأرصدة</title>
<style>
body { font-family: Arial; margin: 40px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
th { background-color: #14B8A6; color: white; }
</style>
</head>
<body>
<h2>تقرير الإجازات التراكمية</h2>
<table>
<tr><th>الاسم</th><th>المستحقة</th><th>المأخوذة</th><th>الرصيد</th></tr>
"""
    for r in data:
        html += f"<tr><td>{r['name']}</td><td>{r['earned']}</td><td>{r['taken']}</td><td>{r['balance']}</td></tr>"
    html += "</table><p>تاريخ التقرير: " + str(date.today()) + "</p></body></html>"
    with open("global_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    import webbrowser
    webbrowser.open("global_report.html")

# =================== النافذة الرئيسية ===================
class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("نظام إدارة الإجازات التراكمية")
        self.resize(1280, 780)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._ui()
        self._refresh()
        # تطبيق الثيم المحفوظ
        settings = QSettings("MyCompany", "LeaveSystem")
        theme = settings.value("theme", "داكن")
        if theme == "فاتح":
            QApplication.instance().setStyleSheet(LIGHT_STYLE)
        else:
            QApplication.instance().setStyleSheet(APP_STYLE)
        # عرض الإشعارات
        if settings.value("notifications", True, type=bool):
            QTimer.singleShot(500, lambda: self.check_notifications(show_message=True, force=False))
        else:
            # حتى لو معطلة، لا تظهر تلقائياً
            pass

    def get_all_alerts(self):
        """جمع كل التنبيهات (رصيد منخفض + إجازات تنتهي خلال 5 أيام)"""
        alerts = []
        today = date.today()
        for eid, emp in db.all().items():
            # رصيد منخفض
            balance = compute_balance(emp)["balance"]
            if balance <= 5:
                alerts.append(f"⚠️ {emp.get('name', '')} - رصيده منخفض جداً: {balance} يوم")
            
            # فحص كل الإجازات: أي إجازة تنتهي خلال 5 أيام أو أقل
            for lv in emp.get("history", []):
                start_date_str = lv.get("start_date")
                if not start_date_str:
                    continue
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    days_actual = lv.get("days_actual", 0)
                    end_date = start_date + timedelta(days=days_actual)
                    remaining = (end_date - today).days
                    if 0 <= remaining <= 5:
                        ltype = lv.get("type", "إجازة")
                        alerts.append(f"📅 {emp.get('name', '')} - {emp.get('job_title', '')} - {emp.get('institution', '')} : {ltype} تنتهي بعد {remaining} يوم (من {start_date} إلى {end_date})")
                except Exception as e:
                    continue
        return alerts

    def check_notifications(self, show_message=True, force=False):
        """عرض الإشعارات: force=True يتجاوز إعدادات الإشعارات"""
        if not force:
            settings = QSettings("MyCompany", "LeaveSystem")
            if not settings.value("notifications", True, type=bool):
                if show_message:
                    QMessageBox.information(self, "إشعارات معطلة", "تم تعطيل الإشعارات التلقائية من الإعدادات.\nيمكنك الضغط على زر التنبيهات يدوياً.")
                return
        alerts = self.get_all_alerts()
        if show_message:
            if alerts:
                self.show_alerts_window(alerts)
            else:
                QMessageBox.information(self, "إشعارات", "لا توجد تنبيهات حالياً.")

    def show_alerts_window(self, alerts_list):
        """نافذة مستقلة لعرض التنبيهات مع إمكانية تصدير HTML"""
        dialog = QDialog(self)
        dialog.setWindowTitle("الإشعارات والتنبيهات")
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.resize(700, 500)
        dialog.setStyleSheet(self.styleSheet())
        
        layout = QVBoxLayout(dialog)
        
        title = QLabel(f"قائمة التنبيهات ({len(alerts_list)})")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C['accent']};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText("\n".join(alerts_list))
        layout.addWidget(text_edit)
        
        btn_layout = QHBoxLayout()
        btn_export = QPushButton("📄 تصدير التقرير (HTML)")
        btn_export.setObjectName("Blue")
        btn_export.clicked.connect(lambda: self.export_alerts_html(alerts_list))
        btn_close = QPushButton("إغلاق")
        btn_close.setObjectName("Ghost")
        btn_close.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_export)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        dialog.exec()

    def export_alerts_html(self, alerts_list):
        """فتح تقرير التنبيهات في المتصفح مباشرة دون حفظ مسبق"""
        if not alerts_list:
            QMessageBox.information(self, "لا توجد بيانات", "لا توجد تنبيهات للتصدير.")
            return
        
        html = f"""<!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head><meta charset="UTF-8"><title>تقرير التنبيهات</title>
    <style>
    body {{ font-family: 'Segoe UI', Arial; direction: rtl; padding: 30px; }}
    h1 {{ color: #0f3460; border-bottom: 2px solid #00C896; }}
    ul {{ list-style-type: none; padding: 0; }}
    li {{ background: #f9f9f9; margin: 8px 0; padding: 10px; border-radius: 6px; }}
    @media print {{ body {{ padding: 20px; }} li {{ break-inside: avoid; }} }}
    </style>
    </head>
    <body>
    <h1>تقرير الإشعارات والتنبيهات</h1>
    <p>تاريخ التقرير: {date.today()}</p>
    <ul>
    """
        for alert in alerts_list:
            html += f"<li>{alert}</li>"
        html += "</ul></body></html>"
        
        # حفظ الملف المؤقت في مجلد المستخدم
        temp_file = os.path.join(os.path.expanduser("~"), "alerts_report_temp.html")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(html)
        
        # فتح في المتصفح
        import webbrowser
        webbrowser.open(f"file://{temp_file}")
        
        QMessageBox.information(self, "تم", "تم فتح التقرير في المتصفح.\nيمكنك الطباعة أو الحفظ من هناك.")
            

    def closeEvent(self, event):
        settings = QSettings("MyCompany", "LeaveSystem")
        if settings.value("auto_backup", False, type=bool):
            backup_dir = "backups"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            backup_name = f"backup_{date.today()}.db"
            backup_path = os.path.join(backup_dir, backup_name)
            try:
                shutil.copy2("employees_leave.db", backup_path)
                print(f"تم عمل نسخ احتياطي إلى {backup_path}")
            except Exception as e:
                print(f"فشل النسخ الاحتياطي: {e}")
        event.accept()

    def _open_settings(self):
        SettingsDialog(self).exec()

    def _open_about(self):
        AboutDialog(self).exec()

    def _ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0,0,0,0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("Surface")
        hdr.setFixedHeight(60)
        hdr_layout = QHBoxLayout(hdr)
        title_lbl = QLabel("نظام إدارة الإجازات التراكمية")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {C['accent']};")
        sub_lbl = QLabel(f"يوم إجازة لكل {DAYS_PER_LEAVE} أيام دوام  |  المعدل السنوي {MAX_ANNUAL} يوم")
        sub_lbl.setStyleSheet(f"color: {C['muted']};")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()
        hdr_layout.addWidget(sub_lbl)
        main_layout.addWidget(hdr)

        # Body
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(15, 15, 15, 15)

        # Sidebar
        side = QFrame()
        side.setObjectName("Card")
        side.setFixedWidth(300)
        side_layout = QVBoxLayout(side)

        btn_add_emp = QPushButton("➕  إضافة موظف جديد")
        btn_add_emp.setObjectName("Accent")
        btn_add_emp.clicked.connect(self._add_emp)
        side_layout.addWidget(btn_add_emp)

        side_layout.addWidget(self._separator())
        btn_quick_leave = QPushButton("📝  تسجيل إجازة")
        btn_quick_leave.setObjectName("Blue")
        btn_quick_leave.clicked.connect(self._quick_leave_window)
        side_layout.addWidget(btn_quick_leave)


        btn_report = QPushButton("📄  تقرير إجمالي HTML")
        btn_report.setObjectName("Ghost")
        btn_report.clicked.connect(lambda: export_html_report(generate_global_report()))
        side_layout.addWidget(btn_report)


        side_layout.addWidget(self._separator())
        btn_leaves = QPushButton("📅  سجل الإجازات")
        btn_leaves.setObjectName("Ghost")
        btn_leaves.clicked.connect(self._view_leaves)
        side_layout.addWidget(btn_leaves)

        btn_edit = QPushButton("✏  تعديل الموظف")
        btn_edit.setObjectName("Ghost")
        btn_edit.clicked.connect(self._edit_emp)
        side_layout.addWidget(btn_edit)

        btn_del = QPushButton("🗑  حذف الموظف")
        btn_del.setObjectName("Warn")
        btn_del.clicked.connect(self._delete_emp)
        side_layout.addWidget(btn_del)

        side_layout.addStretch()
        btn_print = QPushButton("🖨  طباعة التفاصيل")
        btn_print.setObjectName("Ghost")
        btn_print.clicked.connect(self._print_emp)
        side_layout.addWidget(btn_print)

        btn_settings = QPushButton("⚙ الإعدادات")
        btn_settings.setObjectName("Ghost")
        btn_settings.clicked.connect(self._open_settings)
        side_layout.addWidget(btn_settings)

        btn_notify = QPushButton("🔔 عرض التنبيهات")
        btn_notify.setObjectName("Ghost")
        btn_notify.clicked.connect(lambda: self.check_notifications(show_message=True, force=True))
        side_layout.addWidget(btn_notify)

        side_layout.addWidget(self._separator())
        btn_db_ops = QPushButton("🗄️  عمليات قاعدة البيانات")
        btn_db_ops.setObjectName("Ghost")
        btn_db_ops.clicked.connect(self._open_db_ops)
        side_layout.addWidget(btn_db_ops)

        btn_about = QPushButton("ℹ حول")
        btn_about.setObjectName("Ghost")
        btn_about.clicked.connect(self._open_about)
        side_layout.addWidget(btn_about)

        # Center
        center_layout = QVBoxLayout()
        # شريط البحث والفلترة
        filter_layout = QHBoxLayout()
        self.btn_export_all = QPushButton("📊  تصدير الكل Excel")
        self.btn_export_all.setObjectName("Gold")
        self.btn_export_all.clicked.connect(self._export_all)
        filter_layout.addWidget(self.btn_export_all)

        filter_layout.addWidget(QLabel("بحث:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("الاسم أو الرقم...")
        self.search_input.textChanged.connect(self._refresh)
        filter_layout.addWidget(self.search_input)

        filter_layout.addWidget(QLabel("مكان العمل:"))
        self.workplace_filter = QLineEdit()
        self.workplace_filter.setPlaceholderText("فلترة حسب مكان العمل")
        self.workplace_filter.textChanged.connect(self._refresh)
        filter_layout.addWidget(self.workplace_filter)

        filter_layout.addWidget(QLabel("المؤسسة:"))
        self.institution_filter = QLineEdit()
        self.institution_filter.setPlaceholderText("فلترة حسب المؤسسة")
        self.institution_filter.textChanged.connect(self._refresh)
        filter_layout.addWidget(self.institution_filter)

        filter_layout.addStretch()
        center_layout.addLayout(filter_layout)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.cols = ["الرقم الوظيفي","الاسم","العنوان الوظيفي","مكان العمل","المؤسسة","الجنس","المباشرة","أيام الخدمة","خارج الرصيد","الدوام المحسوبة","المستحقة","المأخوذة","الرصيد"]
        self.table.setColumnCount(len(self.cols))
        self.table.setHorizontalHeaderLabels(self.cols)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._on_sel)
        center_layout.addWidget(self.table)

        # Details panel
        self.details_frame = QFrame()
        self.details_frame.setObjectName("Card")
        self.details_frame.setFixedHeight(120)
        details_layout = QGridLayout(self.details_frame)
        self.dlbls = {}
        items = [("name","الاسم"), ("job_title","العنوان الوظيفي"), ("workplace","مكان العمل"),
                 ("institution","المؤسسة"), ("gender","الجنس"), ("start_date","تاريخ المباشرة"),
                 ("raw_days","أيام الخدمة"), ("net_days","أيام الدوام المحسوبة"), ("earned","المستحقة"),
                 ("taken","المأخوذة"), ("balance","الرصيد")]
        for i, (k, lb) in enumerate(items):
            title_lbl = QLabel(lb)
            title_lbl.setStyleSheet(f"color: {C['muted']}; font-size: 11px;")
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
            val_lbl = QLabel("—")
            val_lbl.setFont(QFont("Segoe UI", 16 if k == "balance" else 11, QFont.Weight.Bold))
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            details_layout.addWidget(title_lbl, 0, i)
            details_layout.addWidget(val_lbl, 1, i)
            self.dlbls[k] = val_lbl
        center_layout.addWidget(self.details_frame)

        body_layout.addWidget(side)
        body_layout.addLayout(center_layout)
        main_layout.addLayout(body_layout)

    def _separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {C['border']}; max-height: 1px;")
        return line

    def _refresh(self):
        q = self.search_input.text().strip()
        workplace = self.workplace_filter.text().strip()
        institution = self.institution_filter.text().strip()
        self.table.setRowCount(0)
        for eid, emp in db.search(q, workplace, institution).items():
            b = compute_balance(emp)
            row = self.table.rowCount()
            self.table.insertRow(row)
            items = [
                eid, emp.get("name",""), emp.get("job_title",""), emp.get("workplace",""),
                emp.get("institution",""), emp.get("gender",""), emp.get("start_date",""),
                str(b["raw_days"]), str(b["outside"]), str(b["net_days"]), str(b["earned"]),
                str(b["taken"]), str(b["balance"])
            ]
            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 12:  # عمود الرصيد
                    item.setForeground(QColor(C["neg"] if b["balance"] < 0 else C["accent"]))
                self.table.setItem(row, col_idx, item)
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, eid)
        self.table.resizeColumnsToContents()
        self._on_sel()

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0: return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _on_sel(self):
        eid = self._sel_id()
        if not eid:
            for v in self.dlbls.values():
                v.setText("—")
                v.setStyleSheet(f"color: {C['text']};")
            return
        emp = db.get(eid)
        b = compute_balance(emp)
        for k, v in self.dlbls.items():
            if k in ("raw_days","net_days","earned","taken","balance"):
                val = b.get(k, "—")
                suffix = " يوم"
                color = C["accent"] if b["balance"] >= 0 else C["neg"]
                if k != "balance": color = C["text"]
            else:
                val = emp.get(k, "—")
                suffix = ""
                color = C["text"]
            v.setText(f"{val}{suffix}")
            v.setStyleSheet(f"color: {color};")

    def _show_context_menu(self, pos):
        if not self._sel_id(): return
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        for text, slot in [("🖨 طباعة التفاصيل", self._print_emp),
                           ("✏ تعديل الموظف", self._edit_emp),
                           ("📅 سجل الإجازات", self._view_leaves),
                           ("➕ إضافة إجازة", self._quick_leave_window),
                           ("🗑 حذف الموظف", self._delete_emp)]:
            act = QAction(text, self)
            act.triggered.connect(slot)
            menu.addAction(act)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _add_emp(self):
        EmployeeDialog(self, on_save=self._refresh).exec()

    def _edit_emp(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
            return
        EditEmployeeDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel())).exec()

    def _delete_emp(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
            return
        name = db.get(eid).get("name","")
        if QMessageBox.question(self, "تأكيد", f"حذف '{name}' بالكامل مع سجلاته؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            db.delete(eid)
            self._refresh()

    def _view_leaves(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
            return
        LeavesRegisterDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel())).exec()

    def _quick_leave_window(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً أولاً.")
            return
        LeaveQuickDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel())).exec()

    def _open_db_ops(self):
        DatabaseOperationsDialog(self, refresh_callback=self._refresh).exec()

    def _export_all(self):
        if not HAS_XLSX:
            QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "تصدير الكل", "", "Excel Files (*.xlsx)")
        if not path: return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "الموظفون"
        ws.sheet_view.rightToLeft = True
        hdrs = ["الرقم الوظيفي","الاسم","العنوان الوظيفي","مكان العمل","المؤسسة","الجنس","تاريخ المباشرة",
                "أيام الخدمة","خارج الرصيد","أيام الدوام المحسوبة","المستحقة","المأخوذة","الرصيد","ملاحظات"]
        ws.append(hdrs)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="00C896")
            cell.fill = PatternFill("solid", fgColor="1C2D3E")
        for eid, emp in db.search().items():
            b = compute_balance(emp)
            ws.append([eid, emp.get("name",""), emp.get("job_title",""), emp.get("workplace",""),
                       emp.get("institution",""), emp.get("gender",""), emp.get("start_date",""),
                       b["raw_days"], b["outside"], b["net_days"],
                       b["earned"], b["taken"], b["balance"], emp.get("notes","")])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 18
        wb.save(path)
        QMessageBox.information(self, "تم", f"تم التصدير:\n{path}")

    def _print_emp(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
            return
        emp = db.get(eid)
        b = compute_balance(emp)
        history_rows = ""
        for i, lv in enumerate(emp.get("history", [])):
            outside = "نعم" if lv.get("outside_balance") else "لا"
            start_d = lv.get("start_date", lv.get("from_date", ""))
            history_rows += f"""
                <tr>
                    <td>{i+1}</td>
                    <td>{lv.get('type','')}</td>
                    <td>{start_d}</td>
                    <td>{lv.get('amount','')} {lv.get('unit','')}</td>
                    <td>{outside}</td>
                    <td>{lv.get('order','')}</td>
                    <td>{lv.get('order_date','')}</td>
                    <td>{lv.get('reason','')}</td>
                </tr>"""
        if not history_rows:
            history_rows = "<tr><td colspan='8' style='text-align:center;'>لا توجد إجازات مسجلة</td></tr>"
        html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="UTF-8">
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;direction:rtl;padding:40px;color:#1a1a2e;}}
h1{{font-size:22px;border-bottom:3px solid #00C896;padding-bottom:10px;color:#0f3460;}}
h2{{font-size:18px;color:#0f3460;margin-top:0;}}
.grid{{display:flex;flex-wrap:wrap;gap:20px;margin-top:20px;}}
.item{{min-width:180px;}}
.item label{{font-size:11px;color:#666;display:block;}}
.item span{{font-size:14px;font-weight:bold;color:#1a1a2e;}}
.balance{{font-size:24px;color:{'#00C896' if b['balance']>=0 else '#FF4757'};}}
.page-break {{ page-break-before: always; margin-top: 40px; padding-top: 20px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 10px 8px; text-align: center; }}
th {{ background-color: #1C2D3E; color: #00C896; }}
tr:nth-child(even) {{ background-color: #f9f9f9; }}
.footer-signatures {{ display: flex; justify-content: space-between; margin-top: 60px; font-size: 14px; font-weight: bold; page-break-inside: avoid; }}
@media print{{ body{{padding:20px;}} .page-break {{ margin-top: 0; }} }}
</style>
</head>
<body>
<h1>البيانات التفصيلية لسجل الاجازات والرصيد التراكمي الخاص بـ:<br>{emp.get('job_title', '')} - {emp.get('name', '')}</h1>
<div class="grid">
  <div class="item"><label>الرقم الوظيفي</label><span>{eid}</span></div>
  <div class="item"><label>العنوان الوظيفي</label><span>{emp.get('job_title','-')}</span></div>
  <div class="item"><label>مكان العمل</label><span>{emp.get('workplace','-')}</span></div>
  <div class="item"><label>المؤسسة</label><span>{emp.get('institution','-')}</span></div>
  <div class="item"><label>الجنس</label><span>{emp.get('gender','-')}</span></div>
  <div class="item"><label>تاريخ المباشرة</label><span>{emp.get('start_date','-')}</span></div>
  <div class="item"><label>ملاحظات</label><span>{emp.get('notes','-') or '-'}</span></div>
  <hr class="separator" style="width: 100%; margin: 15px 0; border: 1px solid #ccc;">
  <div class="item"><label>أيام الخدمة الكلية</label><span>{b['raw_days']} يوم</span></div>
  <div class="item"><label>أيام خارج الرصيد</label><span>{b['outside']} يوم</span></div>
  <div class="item"><label>أيام الدوام المحسوبة</label><span>{b['net_days']} يوم</span></div>
  <div class="item"><label>الإجازات المستحقة</label><span>{b['earned']} يوم</span></div>
  <div class="item"><label>الإجازات المأخوذة</label><span>{b['taken']} يوم</span></div>
  <div class="item"><label>الرصيد المتبقي</label><span class="balance">{b['balance']} يوم</span></div>
</div>
<div class="page-break">
  <h2>سجل الإجازات الخاص بالموظف <br>{emp.get('job_title', '')} - {emp.get('name', '')}</h2>
  <table>
    <thead><tr><th>#</th><th>النوع</th><th>بدءاً من</th><th>العدد</th><th>خارج الرصيد؟</th><th>الأمر</th><th>تاريخ الأمر</th><th>السبب</th></tr></thead>
    <tbody>{history_rows}</tbody>
  </table>
  <div class="footer-signatures">
      <div>تاريخ الطباعة: {date.today()}</div>
      <div>الموظف المسؤول عن التقرير: _________________________</div>
  </div>
</div>
<script>window.onload=function(){{window.print();}}</script>
</body></html>"""
        tmp = os.path.join(os.path.expanduser("~"), "_emp_print.html")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(html)
        import webbrowser
        webbrowser.open(f"file://{tmp}")

# =================== تشغيل التطبيق ===================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)  # مؤقتاً، سيتم تغييره لاحقاً حسب الإعدادات المحفوظة
    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)
    window = MainApp()
    window.show()
    sys.exit(app.exec())