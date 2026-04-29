#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام إدارة الإجازات التراكمية - النسخة المتقدمة (نسخة PyQt6)
يدعم: منتقي التاريخ، مكان العمل، استقطاع خارج الرصيد، الأوامر الإدارية، كارت الزمنية،
عرض من اليمين لليسار (Native RTL)، التصدير لـ PDF (داعم للعربية) و Excel، واستيراد/تصدير قواعد البيانات للدمج.
"""

import sys
import os, sqlite3, shutil
from datetime import date, datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QMessageBox, QFrame, QCheckBox, QDateEdit, 
    QTextEdit, QDialog, QFileDialog, QScrollArea
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QColor, QIcon

# ─── محاولة استيراد مكتبات مساعدة ───
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

# ═══════════════════════════════════════════════
#  الثوابت والألوان (الوضع الداكن الحديث)
# ═══════════════════════════════════════════════
DAYS_PER_LEAVE = 10
MAX_ANNUAL = 36

LEAVE_TYPES_MALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات", "كارت الزمنية"]
LEAVE_TYPES_FEMALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات",
                      "قبل الوضع", "بعد الوضع", "أمومة", "كارت الزمنية"]

UNIT_DAYS = {"يوم": 1, "شهر": 30, "سنة": 365}

C = {
    "bg": "#0F172A",        # كحلي داكن كخلفية رئيسية
    "surface": "#1E293B",   # درجة أفتح قليلاً لمناطق العمل (Panels)
    "card": "#334155",      # بطاقات بارزة بشكل أنيق
    "accent": "#14B8A6",    # أخضر نعناعي مشرق (Teal 400) للفت الانتباه
    "blue": "#38BDF8",      # أزرق سماوي مضيء
    "warn": "#FBBF24",      # أصفر تحذيري واضح
    "text": "#F8FAFC",      # أبيض مائل للرمادي للنصوص الأساسية
    "muted": "#94A3B8",     # نصوص فرعية هادئة
    "border": "#475569",    # حدود متناسقة مع عمق الخلفية
    "neg": "#F87171",       # أحمر فاتح للتباين في الوضع المظلم
    "gold": "#FBBF24",
}

# ستايل شيت (QSS) العام للبرنامج
APP_STYLE = f"""
QWidget {{
    background-color: {C["bg"]};
    color: {C["text"]};
    font-family: 'Segoe UI', Arial;
    font-size: 10pt;
}}
QFrame#Card {{
    background-color: {C["card"]};
    border-radius: 6px;
    border: 1px solid {C["border"]};
}}
QFrame#Surface {{
    background-color: {C["surface"]};
}}
QLineEdit, QComboBox, QDateEdit, QTextEdit {{
    background-color: {C["surface"]};
    color: {C["text"]};
    border: 1px solid {C["border"]};
    border-radius: 4px;
    padding: 6px;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {{
    border: 1px solid {C["accent"]};
}}
QPushButton {{
    font-weight: bold;
    padding: 8px 14px;
    border-radius: 4px;
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
}}
QHeaderView::section {{
    background-color: {C["surface"]};
    color: {C["muted"]};
    font-weight: bold;
    padding: 6px;
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
"""

# ═══════════════════════════════════════════════
#  منطق الحساب
# ═══════════════════════════════════════════════
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

# ═══════════════════════════════════════════════
#  قاعدة البيانات (SQLite)
# ═══════════════════════════════════════════════
class DB:
    def __init__(self):
        self.db_path = "employees_leave.db"
        self._init_db()
        self._migrate_json_to_sqlite()

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
                    notes TEXT
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
            conn.execute("INSERT INTO employees (emp_id, name, job_title, workplace, gender, start_date, notes) VALUES (?,?,?,?,?,?,?)",
                      (emp_id, fields.get('name'), fields.get('job_title'), fields.get('workplace'), fields.get('gender'), fields.get('start_date'), fields.get('notes')))

    def update(self, emp_id, fields: dict):
        with self.get_conn() as conn:
            conn.execute("UPDATE employees SET name=?, job_title=?, workplace=?, gender=?, start_date=?, notes=? WHERE emp_id=?",
                      (fields.get('name'), fields.get('job_title'), fields.get('workplace'), fields.get('gender'), fields.get('start_date'), fields.get('notes'), emp_id))

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

    def search(self, q=""):
        with self.get_conn() as conn:
            if q:
                like_q = f"%{q}%"
                emps = conn.execute("SELECT * FROM employees WHERE emp_id LIKE ? OR name LIKE ?", (like_q, like_q)).fetchall()
            else:
                emps = conn.execute("SELECT * FROM employees").fetchall()
            
            if not emps: return {}

            emp_dict = {e['emp_id']: dict(e) for e in emps}
            for e in emp_dict.values():
                e['history'] = []

            if q:
                placeholders = ','.join(['?']*len(emps))
                ids = tuple(emp_dict.keys())
                leaves_rows = conn.execute(f"SELECT * FROM leaves WHERE emp_id IN ({placeholders}) ORDER BY id ASC", ids).fetchall()
            else:
                leaves_rows = conn.execute("SELECT * FROM leaves ORDER BY id ASC").fetchall()
            
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

# ═══════════════════════════════════════════════
#  نوافذ الحوار (Dialogs)
# ═══════════════════════════════════════════════

class BaseDialog(QDialog):
    """كلاس أساسي لتوريث إعدادات الـ RTL والستايل للنوافذ الفرعية"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

def create_date_edit():
    de = QDateEdit()
    de.setCalendarPopup(True)
    de.setDisplayFormat("yyyy-MM-dd")
    de.setDate(QDate.currentDate())
    return de

class EmployeeDialog(BaseDialog):
    def __init__(self, parent=None, emp_id=None, on_save=None):
        super().__init__(parent)
        self.emp_id = emp_id
        self.on_save = on_save
        self.edit_mode = emp_id is not None

        self.setWindowTitle("تعديل موظف" if self.edit_mode else "إضافة موظف جديد")
        self.resize(500, 600)
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
        
        self.cb_gender = QComboBox()
        self.cb_gender.addItems(["ذكر", "أنثى"])
        
        self.e_start = create_date_edit()
        
        self.e_notes = QTextEdit()
        self.e_notes.setFixedHeight(80)

        form_layout.addRow("الرقم الوظيفي *", self.e_id)
        form_layout.addRow("الاسم الكامل *", self.e_name)
        form_layout.addRow("العنوان الوظيفي", self.e_title)
        form_layout.addRow("مكان العمل", self.e_workplace)
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
        self.cb_gender.setCurrentText(emp.get("gender", "ذكر"))
        
        date_str = emp.get("start_date", "")
        if date_str:
            self.e_start.setDate(QDate.fromString(date_str, "yyyy-MM-dd"))
            
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
        
        # أزرار التحكم
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

        # الجدول
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # إعدادات السلوك الأصلية للـ RTL كما طلبت
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
        if row < 0: return None
        return row

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

        headers = [ar(c) for c in reversed(self.cols)] # Reverse for RTL table in ReportLab
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

# ═══════════════════════════════════════════════
#  النافذة الرئيسية
# ═══════════════════════════════════════════════
class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("نظام إدارة الإجازات التراكمية")
        self.resize(1280, 780)
        
        # التفعيل الجذري للـ RTL للنافذة الرئيسية ومحتوياتها
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self._ui()
        self._refresh()

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

        # Body Layout
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(15, 15, 15, 15)
        
        # Sidebar
        side = QFrame()
        side.setObjectName("Card")
        side.setFixedWidth(300)
        self._sidebar(side)
        
        # Center (Table + Details)
        center_layout = QVBoxLayout()
        
        # Search Bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("بحث:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("الاسم أو الرقم الوظيفي...")
        self.search_input.textChanged.connect(self._refresh)
        search_layout.addWidget(self.search_input)
        search_layout.addStretch()
        center_layout.addLayout(search_layout)

        # Table
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_sel)
        
        # إعدادات الـ RTL (السماح بتغيير حجم العمود، دفع البقية، التمرير)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        
        self.cols = ["الرقم الوظيفي","الاسم","العنوان الوظيفي","مكان العمل","الجنس","المباشرة","أيام الخدمة","خارج الرصيد","الدوام المحسوبة","المستحقة","المأخوذة","الرصيد"]
        self.table.setColumnCount(len(self.cols))
        self.table.setHorizontalHeaderLabels(self.cols)
        
        center_layout.addWidget(self.table)

        # Details Panel
        self.details_frame = QFrame()
        self.details_frame.setObjectName("Card")
        self.details_frame.setFixedHeight(120)
        details_layout = QGridLayout(self.details_frame)
        
        self.dlbls = {}
        items = [("name","الاسم"), ("job_title","العنوان الوظيفي"), ("workplace","مكان العمل"),
                 ("gender","الجنس"), ("start_date","تاريخ المباشرة"), ("raw_days","أيام الخدمة"),
                 ("net_days","أيام الدوام المحسوبة"), ("earned","المستحقة"),
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

    def _sidebar(self, p):
        layout = QVBoxLayout(p)
        
        btn_add = QPushButton("➕  إضافة موظف جديد")
        btn_add.setObjectName("Accent")
        btn_add.clicked.connect(self._add_emp)
        layout.addWidget(btn_add)
        
        # خط فاصل
        line1 = QFrame(); line1.setFrameShape(QFrame.Shape.HLine); line1.setStyleSheet(f"color: {C['border']};")
        layout.addWidget(line1)
        
        lbl_quick = QLabel("تسجيل إجازة سريعة")
        lbl_quick.setStyleSheet(f"color: {C['blue']}; font-weight: bold;")
        layout.addWidget(lbl_quick)
        
        form_layout = QFormLayout()
        self.cb_ltype = QComboBox()
        self.cb_ltype.addItems(LEAVE_TYPES_MALE)
        
        amt_lyt = QHBoxLayout()
        self.e_lamount = QLineEdit()
        self.cb_lunit = QComboBox()
        self.cb_lunit.addItems(["يوم", "شهر", "سنة"])
        amt_lyt.addWidget(self.e_lamount)
        amt_lyt.addWidget(self.cb_lunit)
        
        self.e_lstart = create_date_edit()
        self.e_lorder = QLineEdit()
        self.e_lorder_date = create_date_edit()
        self.cb_outside = QCheckBox("خارج الرصيد؟")
        self.e_lreason = QLineEdit()
        
        form_layout.addRow("النوع", self.cb_ltype)
        form_layout.addRow("العدد", amt_lyt)
        form_layout.addRow("من تاريخ", self.e_lstart)
        form_layout.addRow("الأمر", self.e_lorder)
        form_layout.addRow("تاريخ الأمر", self.e_lorder_date)
        form_layout.addRow("", self.cb_outside)
        form_layout.addRow("السبب", self.e_lreason)
        layout.addLayout(form_layout)
        
        btn_quick = QPushButton("تسجيل الإجازة")
        btn_quick.setObjectName("Blue")
        btn_quick.clicked.connect(self._quick_leave)
        layout.addWidget(btn_quick)
        
        line2 = QFrame(); line2.setFrameShape(QFrame.Shape.HLine); line2.setStyleSheet(f"color: {C['border']};")
        layout.addWidget(line2)
        
        btn_leaves = QPushButton("📅  سجل الإجازات")
        btn_leaves.setObjectName("Ghost"); btn_leaves.clicked.connect(self._view_leaves)
        layout.addWidget(btn_leaves)
        
        btn_edit = QPushButton("✏  تعديل الموظف")
        btn_edit.setObjectName("Ghost"); btn_edit.clicked.connect(self._edit_emp)
        layout.addWidget(btn_edit)
        
        btn_del = QPushButton("🗑  حذف الموظف")
        btn_del.setObjectName("Warn"); btn_del.clicked.connect(self._delete_emp)
        layout.addWidget(btn_del)
        
        layout.addStretch()
        
        btn_export_db = QPushButton("💾  تصدير DB")
        btn_export_db.setObjectName("Ghost"); btn_export_db.clicked.connect(self._export_db)
        layout.addWidget(btn_export_db)
        
        btn_import_db = QPushButton("📂  استيراد DB")
        btn_import_db.setObjectName("Ghost"); btn_import_db.clicked.connect(self._import_db)
        layout.addWidget(btn_import_db)
        
        btn_export_all = QPushButton("📊  تصدير الكل Excel")
        btn_export_all.setObjectName("Gold"); btn_export_all.clicked.connect(self._export_all)
        layout.addWidget(btn_export_all)
        
        btn_print = QPushButton("🖨  طباعة تفاصيل")
        btn_print.setObjectName("Ghost"); btn_print.clicked.connect(self._print_emp)
        layout.addWidget(btn_print)

    def _refresh(self):
        q = self.search_input.text().lower()
        self.table.setRowCount(0)
        
        for eid, emp in db.search(q).items():
            b = compute_balance(emp)
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            items = [
                eid, emp.get("name",""), emp.get("job_title",""), emp.get("workplace",""), 
                emp.get("gender",""), emp.get("start_date",""), str(b["raw_days"]), 
                str(b["outside"]), str(b["net_days"]), str(b["earned"]), 
                str(b["taken"]), str(b["balance"])
            ]
            
            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 11: # Balance column
                    if b["balance"] < 0:
                        item.setForeground(QColor(C["neg"]))
                    else:
                        item.setForeground(QColor(C["accent"]))
                self.table.setItem(row, col_idx, item)
                
            # حفظ الـ ID الفعلي داخل الصف بطريقة آمنة في العمود 0
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, eid)

        self.table.resizeColumnsToContents()

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0: return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _on_sel(self):
        eid = self._sel_id()
        if not eid: return
        emp = db.get(eid)
        b = compute_balance(emp)
        
        gender = emp.get("gender", "ذكر")
        types = LEAVE_TYPES_FEMALE if gender == "أنثى" else LEAVE_TYPES_MALE
        self.cb_ltype.clear()
        self.cb_ltype.addItems(types)

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

    def _add_emp(self):
        dlg = EmployeeDialog(self, on_save=self._refresh)
        dlg.exec()

    def _edit_emp(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
            return
        dlg = EditEmployeeDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel()))
        dlg.exec()

    def _delete_emp(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
            return
        name = db.get(eid).get("name","")
        reply = QMessageBox.question(self, "تأكيد", f"حذف '{name}' بالكامل مع سجلاته؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            db.delete(eid)
            self._refresh()
            for v in self.dlbls.values(): 
                v.setText("—")
                v.setStyleSheet(f"color: {C['text']};")

    def _view_leaves(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
            return
        dlg = LeavesRegisterDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel()))
        dlg.exec()

    def _quick_leave(self):
        eid = self._sel_id()
        if not eid:
            QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
            return
            
        ltype = self.cb_ltype.currentText()
        amount_s = self.e_lamount.text().strip()
        unit = self.cb_lunit.currentText()
        outside = self.cb_outside.isChecked()
        reason = self.e_lreason.text().strip()
        start_d = self.e_lstart.date().toString("yyyy-MM-dd")
        order_n = self.e_lorder.text().strip()
        order_d = self.e_lorder_date.date().toString("yyyy-MM-dd")

        if not amount_s:
            QMessageBox.warning(self, "تنبيه", "أدخل عدد الأيام.")
            return
        try: amount = int(amount_s)
        except:
            QMessageBox.warning(self, "تنبيه", "أدخل عدداً صحيحاً للعدد.")
            return
            
        days = unit_to_days(amount, unit)
        emp = db.get(eid)
        b = compute_balance(emp)
        
        if days > b["balance"] and not outside:
            reply = QMessageBox.question(self, "تجاوز الرصيد", f"الرصيد المتاح: {b['balance']} يوم.\nهل تريد المتابعة؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes: return

        record = {
            "type": ltype, "start_date": start_d, "from_date": start_d,
            "amount": amount, "unit": unit, "days_actual": days,
            "order": order_n, "order_date": order_d,
            "outside_balance": outside, "reason": reason,
            "added_date": str(date.today()),
        }
        db.add_leave(eid, record)
        
        self.e_lamount.clear()
        self.e_lreason.clear()
        self.e_lorder.clear()
        self._refresh()
        self._on_sel()

    # ── التصدير والاستيراد ──
    def _export_db(self):
        path, _ = QFileDialog.getSaveFileName(self, "تصدير قاعدة البيانات", "employees_backup.db", "Database Files (*.db)")
        if not path: return
        try:
            shutil.copy2("employees_leave.db", path)
            QMessageBox.information(self, "نجاح", f"تم تصدير قاعدة البيانات بنجاح إلى:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء التصدير:\n{e}")

    def _import_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "استيراد قاعدة البيانات", "", "Database Files (*.db)")
        if not path: return
        
        try:
            with sqlite3.connect(path) as imported_conn:
                imported_conn.row_factory = sqlite3.Row
                ic = imported_conn.cursor()
                
                ic.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees'")
                if not ic.fetchone():
                    QMessageBox.critical(self, "خطأ", "الملف المحدد لا يحتوي على قاعدة بيانات صالحة للبرنامج.")
                    return

                ic.execute("SELECT * FROM employees")
                imported_emps = ic.fetchall()

                added_count, updated_count, skipped_count = 0, 0, 0
                
                for imp_emp in imported_emps:
                    eid = imp_emp['emp_id']
                    ic.execute("SELECT * FROM leaves WHERE emp_id=? ORDER BY id ASC", (eid,))
                    imp_leaves = ic.fetchall()

                    existing = db.get(eid)
                    if existing:
                        reply = QMessageBox.question(self, "تعارض بيانات", 
                            f"الموظف ( {imp_emp['name']} ) بالرقم ( {eid} ) موجود.\nهل تريد استبدال بياناته؟",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                            
                        if reply == QMessageBox.StandardButton.Cancel:
                            QMessageBox.information(self, "إلغاء", "تم إيقاف عملية الاستيراد.")
                            self._refresh()
                            return
                        elif reply == QMessageBox.StandardButton.Yes:
                            db.delete(eid)
                            self._insert_imported_emp(imp_emp, imp_leaves)
                            updated_count += 1
                        else:
                            skipped_count += 1
                    else:
                        self._insert_imported_emp(imp_emp, imp_leaves)
                        added_count += 1
            
            QMessageBox.information(self, "اكتمل الاستيراد", f"تمت إضافة: {added_count}\nتم تحديث: {updated_count}\nتم تخطي: {skipped_count}")
            self._refresh()

        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء الاستيراد:\n{e}")

    def _insert_imported_emp(self, imp_emp, imp_leaves):
        db.add(imp_emp['emp_id'], dict(imp_emp))
        for lv in imp_leaves:
            lv_dict = dict(lv)
            lv_dict['order'] = lv_dict.pop('order_num', '')
            db.add_leave(imp_emp['emp_id'], lv_dict)

    def _export_all(self):
        if not HAS_XLSX:
            QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "تصدير الكل", "", "Excel Files (*.xlsx)")
        if not path: return
        
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "الموظفون"
        ws.sheet_view.rightToLeft = True
        hdrs = ["الرقم الوظيفي","الاسم","العنوان الوظيفي","مكان العمل","الجنس","تاريخ المباشرة",
                "أيام الخدمة","خارج الرصيد","أيام الدوام المحسوبة","المستحقة","المأخوذة","الرصيد","ملاحظات"]
        ws.append(hdrs)
        
        for cell in ws[1]:
            cell.font = Font(bold=True, color="00C896")
            cell.fill = PatternFill("solid", fgColor="1C2D3E")
            
        for eid, emp in db.search().items():
            b = compute_balance(emp)
            ws.append([eid, emp.get("name",""), emp.get("job_title",""), emp.get("workplace",""),
                       emp.get("gender",""), emp.get("start_date",""),
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
            history_rows += f"""<tr>
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
<h1>البيانات التفصيلية لسجل الاجازات والرصيد التراكمي الخاص بـ: {emp.get('name','')}</h1>
<div class="grid">
  <div class="item"><label>الرقم الوظيفي</label><span>{eid}</span></div>
  <div class="item"><label>العنوان الوظيفي</label><span>{emp.get('job_title','-')}</span></div>
  <div class="item"><label>مكان العمل</label><span>{emp.get('workplace','-')}</span></div>
  <div class="item"><label>الجنس</label><span>{emp.get('gender','-')}</span></div>
  <div class="item"><label>تاريخ المباشرة</label><span>{emp.get('start_date','-')}</span></div>
  <div class="item"><label>ملاحظات</label><span>{emp.get('notes','-') or '-'}</span></div>
  <div class="item"><label>أيام الخدمة الكلية</label><span>{b['raw_days']} يوم</span></div>
  <div class="item"><label>أيام خارج الرصيد</label><span>{b['outside']} يوم</span></div>
  <div class="item"><label>أيام الدوام المحسوبة</label><span>{b['net_days']} يوم</span></div>
  <div class="item"><label>الإجازات المستحقة</label><span>{b['earned']} يوم</span></div>
  <div class="item"><label>الإجازات المأخوذة</label><span>{b['taken']} يوم</span></div>
  <div class="item"><label>الرصيد المتبقي</label><span class="balance">{b['balance']} يوم</span></div>
</div>
<div class="page-break">
  <h2>سجل الإجازات الخاص بالموظف</h2>
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

# ═══════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # تطبيق الستايل شيت العام
    app.setStyleSheet(APP_STYLE)
    
    # ضبط الخط الافتراضي
    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)
    
    window = MainApp()
    window.show()
    sys.exit(app.exec())