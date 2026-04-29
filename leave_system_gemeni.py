#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام إدارة الإجازات التراكمية - النسخة المتقدمة المتكاملة
تتضمن جميع ميزات الواجهة الأصلية + الإضافات الجديدة كاملة.
"""

import sys, os, sqlite3, shutil, json
from datetime import date, datetime, timedelta
import webbrowser

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QMessageBox, QFrame, QCheckBox, QDateEdit, 
    QTextEdit, QDialog, QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QDate, QPoint
from PyQt6.QtGui import QFont, QColor, QAction

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

try:
    import matplotlib.pyplot as plt
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False

# ═══════════════════════════════════════════════
#  إعدادات النظام (حفظ الإعدادات)
# ═══════════════════════════════════════════════
CONFIG_FILE = "settings_config.json"
CONFIG = {
    "notifications": True,
    "auto_backup": True,
    "theme": "داكن"
}

def load_config():
    global CONFIG
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                CONFIG.update(json.load(f))
        except: pass

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f)
    except: pass

load_config()

# ═══════════════════════════════════════════════
#  الثوابت والألوان والاستايلات
# ═══════════════════════════════════════════════
DAYS_PER_LEAVE = 10
MAX_ANNUAL = 36

LEAVE_TYPES_MALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات", "كارت الزمنية"]
LEAVE_TYPES_FEMALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات",
                      "قبل الوضع", "بعد الوضع", "أمومة", "كارت الزمنية"]

UNIT_DAYS = {"يوم": 1, "شهر": 30, "سنة": 365}

C_DARK = {
    "bg": "#0F172A", "surface": "#1E293B", "card": "#334155", "accent": "#14B8A6",
    "blue": "#38BDF8", "warn": "#FBBF24", "text": "#F8FAFC", "muted": "#94A3B8",
    "border": "#475569", "neg": "#F87171", "gold": "#FBBF24",
}

C_LIGHT = {
    "bg": "#F1F5F9", "surface": "#FFFFFF", "card": "#F8FAFC", "accent": "#0D9488",
    "blue": "#0284C7", "warn": "#D97706", "text": "#0F172A", "muted": "#64748B",
    "border": "#CBD5E1", "neg": "#DC2626", "gold": "#D97706",
}

C = C_DARK if CONFIG["theme"] == "داكن" else C_LIGHT

def get_style(colors):
    return f"""
    QWidget {{ background-color: {colors["bg"]}; color: {colors["text"]}; font-family: 'Segoe UI', Arial; font-size: 10pt; }}
    QFrame#Card {{ background-color: {colors["card"]}; border-radius: 8px; border: 1px solid {colors["border"]}; }}
    QFrame#Surface {{ background-color: {colors["surface"]}; }}
    QLineEdit, QComboBox, QDateEdit, QTextEdit {{ background-color: {colors["surface"]}; color: {colors["text"]}; border: 1px solid {colors["border"]}; border-radius: 6px; padding: 6px; }}
    QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {{ border: 1px solid {colors["accent"]}; outline: none; }}
    QPushButton {{ font-weight: bold; padding: 8px 14px; border-radius: 6px; border: none; }}
    QPushButton#Accent {{ background-color: {colors["accent"]}; color: white; }}
    QPushButton#Accent:hover {{ opacity: 0.8; }}
    QPushButton#Blue {{ background-color: {colors["blue"]}; color: white; }}
    QPushButton#Warn {{ background-color: {colors["neg"]}; color: white; }}
    QPushButton#Gold {{ background-color: {colors["gold"]}; color: white; }}
    QPushButton#Ghost {{ background-color: transparent; border: 1px solid {colors["border"]}; color: {colors["text"]}; }}
    QPushButton#Ghost:hover {{ background-color: {colors["surface"]}; }}
    QTableWidget {{ background-color: {colors["surface"]}; alternate-background-color: {colors["card"]}; border: 1px solid {colors["border"]}; gridline-color: {colors["border"]}; selection-background-color: {colors["accent"]}; selection-color: white; }}
    QHeaderView::section {{ background-color: {colors["surface"]}; color: {colors["muted"]}; font-weight: bold; padding: 8px; border: none; border-right: 1px solid {colors["border"]}; border-bottom: 2px solid {colors["border"]}; }}
    QScrollBar:vertical {{ background: {colors["surface"]}; width: 12px; }}
    QScrollBar::handle:vertical {{ background: {colors["border"]}; border-radius: 6px; }}
    QScrollBar:horizontal {{ background: {colors["surface"]}; height: 12px; }}
    QScrollBar::handle:horizontal {{ background: {colors["border"]}; border-radius: 6px; }}
    QMenu {{ background-color: {colors["surface"]}; color: {colors["text"]}; border: 1px solid {colors["border"]}; border-radius: 6px; }}
    QMenu::item {{ padding: 6px 24px; }}
    QMenu::item:selected {{ background-color: {colors["accent"]}; color: white; }}
    """

APP_STYLE = get_style(C)

def update_global_style():
    global C, APP_STYLE
    C = C_DARK if CONFIG["theme"] == "داكن" else C_LIGHT
    APP_STYLE = get_style(C)
    app.setStyleSheet(APP_STYLE)

# ═══════════════════════════════════════════════
#  منطق الحساب
# ═══════════════════════════════════════════════
def days_since(start_date_str: str) -> int:
    try:
        sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        return max(0, (date.today() - sd).days)
    except: return 0

def unit_to_days(amount: int, unit: str) -> int:
    return amount * UNIT_DAYS.get(unit, 1)

def compute_balance(emp: dict) -> dict:
    start = emp.get("start_date", "")
    leaves = emp.get("history", [])
    raw_days = days_since(start)
    outside = sum(lv.get("days_actual", lv.get("days", 0)) for lv in leaves if lv.get("outside_balance", False))
    net_days = max(0, raw_days - outside)
    earned = net_days // DAYS_PER_LEAVE
    taken = sum(lv.get("days_actual", lv.get("days", 0)) for lv in leaves if not lv.get("outside_balance", False))
    balance = earned - taken
    return {
        "raw_days": raw_days, "outside": outside, "net_days": net_days,
        "earned": earned, "taken": taken, "balance": balance,
    }

# ═══════════════════════════════════════════════
#  قاعدة البيانات
# ═══════════════════════════════════════════════
class DB:
    def __init__(self):
        self.db_path = "employees_leave.db"
        self._init_db()

    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = 1")
        return conn

    def _init_db(self):
        with self.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    emp_id TEXT PRIMARY KEY, name TEXT, job_title TEXT,
                    workplace TEXT, gender TEXT, start_date TEXT, notes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leaves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id TEXT, type TEXT,
                    start_date TEXT, from_date TEXT, amount INTEGER, unit TEXT,
                    days_actual INTEGER, order_num TEXT, order_date TEXT,
                    outside_balance INTEGER, reason TEXT, added_date TEXT,
                    FOREIGN KEY(emp_id) REFERENCES employees(emp_id) ON DELETE CASCADE
                )
            """)

    def add(self, emp_id, fields: dict):
        with self.get_conn() as conn:
            conn.execute("INSERT INTO employees VALUES (?,?,?,?,?,?,?)",
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
            leaves = [dict(r) for r in leaves_rows]
            for l in leaves:
                l['outside_balance'] = bool(l['outside_balance'])
                l['order'] = l.pop('order_num', '')
            emp['history'] = leaves
            return emp

    def add_leave(self, emp_id, record: dict):
        with self.get_conn() as conn:
            conn.execute("""INSERT INTO leaves (emp_id, type, start_date, from_date, amount, unit, days_actual, order_num, order_date, outside_balance, reason, added_date)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (emp_id, record.get('type'), record.get('start_date'), record.get('from_date'),
                       record.get('amount'), record.get('unit'), record.get('days_actual'), record.get('order'), record.get('order_date'), int(record.get('outside_balance', False)), record.get('reason'), record.get('added_date')))

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

    def search(self, q="", workplace="الكل"):
        with self.get_conn() as conn:
            like_q = f"%{q}%" if q else "%%"
            query = "SELECT * FROM employees WHERE (emp_id LIKE ? OR name LIKE ?)"
            params = [like_q, like_q]
            if workplace != "الكل":
                query += " AND workplace = ?"
                params.append(workplace)
            
            emps = conn.execute(query, params).fetchall()
            if not emps: return {}

            emp_dict = {e['emp_id']: dict(e) for e in emps}
            for e in emp_dict.values(): e['history'] = []

            placeholders = ','.join(['?']*len(emps))
            ids = tuple(emp_dict.keys())
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

    def get_all_workplaces(self):
        with self.get_conn() as conn:
            rows = conn.execute("SELECT DISTINCT workplace FROM employees WHERE workplace IS NOT NULL AND workplace != ''").fetchall()
            return [r[0] for r in rows]

db = DB()

# ═══════════════════════════════════════════════
#  نوافذ الحوار والتطبيقات الإضافية
# ═══════════════════════════════════════════════
class BaseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(APP_STYLE)

def create_date_edit():
    de = QDateEdit()
    de.setCalendarPopup(True)
    de.setDisplayFormat("yyyy-MM-dd")
    de.setDate(QDate.currentDate())
    return de

class AboutDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("حول النظام")
        self.resize(400, 300)
        layout = QVBoxLayout(self)
        lbl = QLabel("""
        نظام إدارة الإجازات التراكمية
        الإصدار: 2.0 المتكامل
        
        تم التطوير باستخدام PyQt6
        يدعم إدارة الموظفين، الإجازات، الفلترة، التقارير المتقدمة،
        التنبيهات، ولوحة الإحصائيات.
        """)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

class SettingsDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الإعدادات")
        self.resize(350, 200)
        
        layout = QFormLayout(self)
        self.chk_notifications = QCheckBox("تفعيل الإشعارات والتنبيهات عند البدء")
        self.chk_notifications.setChecked(CONFIG["notifications"])
        
        self.chk_backup = QCheckBox("نسخ احتياطي تلقائي للقاعدة عند الإغلاق")
        self.chk_backup.setChecked(CONFIG["auto_backup"])

        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(["داكن", "فاتح"])
        self.cmb_theme.setCurrentText(CONFIG["theme"])

        layout.addRow("الإشعارات:", self.chk_notifications)
        layout.addRow("النسخ الاحتياطي:", self.chk_backup)
        layout.addRow("المظهر:", self.cmb_theme)
        
        btn_save = QPushButton("حفظ التغييرات")
        btn_save.setObjectName("Accent")
        btn_save.clicked.connect(self._save_settings)
        layout.addWidget(btn_save)

    def _save_settings(self):
        CONFIG["notifications"] = self.chk_notifications.isChecked()
        CONFIG["auto_backup"] = self.chk_backup.isChecked()
        new_theme = self.cmb_theme.currentText()
        if new_theme != CONFIG["theme"]:
            CONFIG["theme"] = new_theme
            update_global_style()
            # تحديث الواجهات المفتوحة
            for widget in app.topLevelWidgets():
                widget.setStyleSheet(APP_STYLE)
        save_config()
        self.accept()

class DatabaseOperationsDialog(BaseDialog):
    def __init__(self, parent=None, refresh_callback=None):
        super().__init__(parent)
        self.refresh_callback = refresh_callback
        self.setWindowTitle("عمليات قاعدة البيانات و الاستيراد")
        self.resize(450, 300)
        self._build()
    
    def _build(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("إدارة قاعدة البيانات و Excel")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        btn_export = QPushButton("📀 تصدير نسخة من قاعدة البيانات (Backup)")
        btn_export.setObjectName("Blue")
        btn_export.clicked.connect(self._export_db)
        layout.addWidget(btn_export)
        
        btn_import = QPushButton("📂 استيراد قاعدة بيانات (دمج DB)")
        btn_import.setObjectName("Gold")
        btn_import.clicked.connect(self._import_db)
        layout.addWidget(btn_import)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        
        btn_template = QPushButton("📄 تحميل قالب إدخال Excel فارغ")
        btn_template.setObjectName("Ghost")
        btn_template.clicked.connect(self._export_template)
        layout.addWidget(btn_template)
        
        btn_excel_import = QPushButton("📥 استيراد موظفين من قالب Excel")
        btn_excel_import.setObjectName("Accent")
        btn_excel_import.clicked.connect(self._import_excel)
        layout.addWidget(btn_excel_import)
        
        layout.addStretch()

    def _export_db(self):
        path, _ = QFileDialog.getSaveFileName(self, "حفظ النسخة الاحتياطية", f"backup_{date.today()}.db", "Database Files (*.db)")
        if path: 
            shutil.copy2("employees_leave.db", path)
            QMessageBox.information(self, "نجاح", "تم التصدير بنجاح.")

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
                            db.add(imp_emp['emp_id'], dict(imp_emp))
                            for lv in imp_leaves:
                                lv_dict = dict(lv)
                                lv_dict['order'] = lv_dict.pop('order_num', '')
                                db.add_leave(imp_emp['emp_id'], lv_dict)
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        db.add(imp_emp['emp_id'], dict(imp_emp))
                        for lv in imp_leaves:
                            lv_dict = dict(lv)
                            lv_dict['order'] = lv_dict.pop('order_num', '')
                            db.add_leave(imp_emp['emp_id'], lv_dict)
                        added += 1
                QMessageBox.information(self, "اكتمل", f"تمت الإضافة: {added}\nتحديث: {updated}\nتخطي: {skipped}")
                if self.refresh_callback:
                    self.refresh_callback()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"خطأ في الاستيراد: {e}")

    def _export_template(self):
        if not HAS_XLSX: return QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
        path, _ = QFileDialog.getSaveFileName(self, "تحميل القالب", "template.xlsx", "Excel Files (*.xlsx)")
        if not path: return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.sheet_view.rightToLeft = True
        ws.append(["emp_id","name","job_title","workplace","gender","start_date"])
        wb.save(path)
        QMessageBox.information(self, "نجاح", "تم حفظ القالب بنجاح.")

    def _import_excel(self):
        if not HAS_XLSX: return QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
        path, _ = QFileDialog.getOpenFileName(self, "استيراد Excel", "", "Excel Files (*.xlsx)")
        if not path: return
        try:
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            added, skipped = 0, 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                eid = str(row[0]) if row[0] else ""
                if not eid or eid == "None" or eid == "emp_id": continue
                if db.get(eid):
                    skipped += 1
                    continue
                db.add(eid, {
                    "name": str(row[1] or ""), "job_title": str(row[2] or ""),
                    "workplace": str(row[3] or ""), "gender": str(row[4] or "ذكر"),
                    "start_date": str(row[5] or ""), "notes": "مستورد من Excel"
                })
                added += 1
            QMessageBox.information(self, "اكتمل", f"تمت إضافة: {added} موظف.\nتخطي (موجود مسبقاً): {skipped}")
            if self.refresh_callback: self.refresh_callback()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل الاستيراد: {str(e)}")


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
            "name": name, "job_title": self.e_title.text().strip(),
            "workplace": self.e_workplace.text().strip(), "gender": self.cb_gender.currentText(),
            "start_date": start, "notes": self.e_notes.toPlainText().strip(),
        }
        if self.edit_mode: db.update(eid, fields)
        else: db.add(eid, fields)
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
            "type": ltype, "start_date": start_d, "from_date": start_d,
            "amount": amount, "unit": unit, "days_actual": days_actual,
            "order": self.e_order.text().strip(), "order_date": self.e_order_date.date().toString("yyyy-MM-dd"),
            "outside_balance": self.cb_outside.isChecked(), "reason": self.e_reason.text().strip(),
            "added_date": str(date.today()),
        }
        if self.edit_mode: db.update_leave(self.emp_id, self.leave_idx, record)
        else: db.add_leave(self.emp_id, record)
        if self.on_save: self.on_save()
        self.accept()

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
        self.setWindowTitle(f"تسجيل إجازة سريعة - {self.emp_name}")
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
            if reply != QMessageBox.StandardButton.Yes: return
            self.cb_outside.setChecked(True)

        record = {
            "type": ltype, "start_date": start_d, "from_date": start_d,
            "amount": amount, "unit": unit, "days_actual": days_actual,
            "order": self.e_order.text().strip(), "order_date": self.e_order_date.date().toString("yyyy-MM-dd"),
            "outside_balance": self.cb_outside.isChecked(), "reason": self.e_reason.text().strip(),
            "added_date": str(date.today()),
        }
        db.add_leave(self.emp_id, record)
        if self.on_save: self.on_save()
        self.accept()

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
        LeaveDialog(self, self.emp_id, on_save=self._refresh_and_notify).exec()
        
    def _edit(self):
        idx = self._sel_idx()
        if idx is None: return QMessageBox.warning(self, "تنبيه", "حدد إجازة.")
        LeaveDialog(self, self.emp_id, leave_idx=idx, on_save=self._refresh_and_notify).exec()
        
    def _delete(self):
        idx = self._sel_idx()
        if idx is None: return QMessageBox.warning(self, "تنبيه", "حدد إجازة.")
        reply = QMessageBox.question(self, "تأكيد", "حذف هذه الإجازة؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_leave(self.emp_id, idx)
            self._refresh_and_notify()
            
    def _refresh_and_notify(self):
        self._refresh()
        if self.on_save: self.on_save()
        
    def _export_xlsx(self):
        if not HAS_XLSX: return QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
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
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 15
        wb.save(path)
        QMessageBox.information(self, "تم", f"تم التصدير:\n{path}")
        
    def _export_pdf(self):
        if not HAS_PDF: return QMessageBox.critical(self, "خطأ", "reportlab/arabic_reshaper/python_bidi غير مثبت.")
        try: pdfmetrics.registerFont(TTFont('ArabicFont', 'arial.ttf'))
        except Exception: return QMessageBox.critical(self, "خطأ", "لم يتم العثور على خط Arial في النظام.")
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PDF", "", "PDF Files (*.pdf)")
        if not path: return
        def ar(text):
            if not text: return ""
            return get_display(arabic_reshaper.reshape(str(text)))
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

# ═══════════════════════════════════════════════
#  الدوال العامة والتنبيهات والتقارير
# ═══════════════════════════════════════════════
def check_notifications():
    if not CONFIG.get("notifications", True): return []
    alerts = []
    for eid, emp in db.all().items():
        b = compute_balance(emp)
        if b["balance"] <= 5:
            alerts.append(f"⚠️ {emp['name']} رصيده منخفض ({b['balance']} يوم)")
        for lv in emp["history"]:
            if lv["type"] in ["طويلة", "مرضية"]:
                try:
                    end_date = datetime.strptime(lv["start_date"], "%Y-%m-%d") + timedelta(days=lv["days_actual"])
                    if 0 <= (end_date.date() - date.today()).days <= 3:
                        alerts.append(f"⏳ إجازة {emp['name']} تنتهي قريباً ({end_date.date()})")
                except: pass
    return alerts 

def generate_global_html_report():
    html = f"""<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="UTF-8">
    <style>body{{font-family:'Segoe UI',Arial; padding:30px;}} table{{width:100%; border-collapse:collapse;}} 
    th, td{{border:1px solid #ccc; padding:10px; text-align:center;}} th{{background-color:#0f172a; color:white;}}</style>
    </head><body><h2>التقرير الشامل لأرصدة الإجازات - {date.today()}</h2><table>
    <tr><th>الاسم</th><th>الرقم الوظيفي</th><th>مكان العمل</th><th>أيام الخدمة</th><th>المستحقة</th><th>المأخوذة</th><th>الرصيد</th></tr>"""
    for eid, emp in db.all().items():
        b = compute_balance(emp)
        color = "red" if b['balance'] < 0 else "green"
        html += f"<tr><td>{emp['name']}</td><td>{eid}</td><td>{emp.get('workplace','')}</td><td>{b['raw_days']}</td><td>{b['earned']}</td><td>{b['taken']}</td><td style='color:{color}; font-weight:bold;'>{b['balance']}</td></tr>"
    html += "</table><script>window.print();</script></body></html>"
    
    tmp = os.path.join(os.path.expanduser("~"), "_global_report.html")
    with open(tmp, "w", encoding="utf-8") as f: f.write(html)
    webbrowser.open(f"file://{tmp}")

def generate_dashboard():
    if not HAS_PLOT: return False
    data = {}
    for emp in db.all().values():
        for lv in emp["history"]:
            data[lv["type"]] = data.get(lv["type"], 0) + lv["days_actual"]
    if not data: return "NoData"
    
    plt.style.use('ggplot')
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(data.keys(), data.values(), color='#14B8A6')
    ax.set_title('توزيع الإجازات المأخوذة حسب النوع (بالأيام)')
    ax.set_ylabel('إجمالي الأيام')
    plt.tight_layout()
    plt.show()
    return True

# ═══════════════════════════════════════════════
#  النافذة الرئيسية MainApp
# ═══════════════════════════════════════════════
class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("نظام إدارة الإجازات التراكمية 2.0")
        self.resize(1300, 800)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._ui()
        self._refresh()
    
    def closeEvent(self, event):
        if CONFIG.get("auto_backup", True):
            try: shutil.copy2("employees_leave.db", f"backup_auto_{date.today()}.db")
            except: pass
        event.accept()

    def _ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0,0,0,0)

        # ─── Header ───
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

        # ─── Body Layout ───
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(15, 15, 15, 15)

        # ─── Sidebar ───
        side = QFrame()
        side.setObjectName("Card")
        side.setFixedWidth(300)
        side_layout = QVBoxLayout(side)
        
        btn_add_emp = QPushButton("➕  إضافة موظف جديد")
        btn_add_emp.setObjectName("Accent")
        btn_add_emp.clicked.connect(self._add_emp)
        side_layout.addWidget(btn_add_emp)
        
        side_layout.addWidget(self._separator())
        
        btn_quick_leave = QPushButton("📝  تسجيل إجازة سريعة")
        btn_quick_leave.setObjectName("Blue")
        btn_quick_leave.clicked.connect(self._quick_leave_window)
        side_layout.addWidget(btn_quick_leave)
        
        side_layout.addWidget(self._separator())
        
        btn_db_ops = QPushButton("🗄️  عمليات قاعدة البيانات (استيراد/تصدير)")
        btn_db_ops.setObjectName("Ghost")
        btn_db_ops.clicked.connect(self._open_db_ops)
        side_layout.addWidget(btn_db_ops)
        
        btn_dashboard = QPushButton("📊  لوحة البيانات والإحصائيات")
        btn_dashboard.setObjectName("Blue")
        btn_dashboard.clicked.connect(self._show_dashboard)
        side_layout.addWidget(btn_dashboard)

        btn_html_report = QPushButton("🌐  تقرير أرصدة شامل لجميع الموظفين")
        btn_html_report.setObjectName("Ghost")
        btn_html_report.clicked.connect(generate_global_html_report)
        side_layout.addWidget(btn_html_report)
        
        side_layout.addWidget(self._separator())
        
        btn_leaves = QPushButton("📅  سجل إجازات الموظف المحدد")
        btn_leaves.setObjectName("Ghost")
        btn_leaves.clicked.connect(self._view_leaves)
        side_layout.addWidget(btn_leaves)
        
        btn_edit = QPushButton("✏  تعديل الموظف المحدد")
        btn_edit.setObjectName("Ghost")
        btn_edit.clicked.connect(self._edit_emp)
        side_layout.addWidget(btn_edit)
        
        btn_del = QPushButton("🗑  حذف الموظف المحدد")
        btn_del.setObjectName("Warn")
        btn_del.clicked.connect(self._delete_emp)
        side_layout.addWidget(btn_del)
        
        side_layout.addStretch()
        
        btn_print = QPushButton("🖨  طباعة كشف تفصيلي للموظف")
        btn_print.setObjectName("Ghost")
        btn_print.clicked.connect(self._print_emp)
        side_layout.addWidget(btn_print)
        
        btn_settings = QPushButton("⚙ الإعدادات")
        btn_settings.clicked.connect(lambda: SettingsDialog(self).exec())
        side_layout.addWidget(btn_settings)

        btn_about = QPushButton("ℹ حول النظام")
        btn_about.clicked.connect(lambda: AboutDialog(self).exec())
        side_layout.addWidget(btn_about)

        # ─── Center Layout ───
        center_layout = QVBoxLayout()
        
        # Search & Filters
        search_layout = QHBoxLayout()
        
        btn_export_all = QPushButton("📊  تصدير الجدول إلى Excel")
        btn_export_all.setObjectName("Gold")
        btn_export_all.clicked.connect(self._export_all)
        search_layout.addWidget(btn_export_all)
        
        search_layout.addSpacing(20)
        
        search_layout.addWidget(QLabel("تصفية حسب القسم:"))
        self.combo_workplace = QComboBox()
        self.combo_workplace.addItem("الكل")
        self.combo_workplace.addItems(db.get_all_workplaces())
        self.combo_workplace.currentTextChanged.connect(self._refresh)
        search_layout.addWidget(self.combo_workplace)
        
        search_layout.addSpacing(20)
        
        search_layout.addWidget(QLabel("بحث:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("الاسم أو الرقم الوظيفي...")
        self.search_input.textChanged.connect(self._refresh)
        search_layout.addWidget(self.search_input)
        
        center_layout.addLayout(search_layout)

        # Table
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.cols = ["الرقم الوظيفي","الاسم","العنوان الوظيفي","القسم","الجنس","المباشرة","أيام الخدمة","خارج الرصيد","الدوام المحسوبة","المستحقة","المأخوذة","الرصيد"]
        self.table.setColumnCount(len(self.cols))
        self.table.setHorizontalHeaderLabels(self.cols)
        
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._on_sel)
        
        center_layout.addWidget(self.table)

        # ─── Details Panel ───
        self.details_frame = QFrame()
        self.details_frame.setObjectName("Card")
        self.details_frame.setFixedHeight(120)
        details_layout = QGridLayout(self.details_frame)
        self.dlbls = {}
        items = [("name","الاسم"), ("job_title","العنوان الوظيفي"), ("workplace","القسم"),
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

    def _separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {C['border']}; max-height: 1px;")
        return line

    def _refresh(self):
        q = self.search_input.text().lower()
        wp = self.combo_workplace.currentText()
        self.table.setRowCount(0)
        for eid, emp in db.search(q, wp).items():
            b = compute_balance(emp)
            row = self.table.rowCount()
            self.table.insertRow(row)
            items = [eid, emp.get("name",""), emp.get("job_title",""), emp.get("workplace",""), emp.get("gender",""), emp.get("start_date",""), 
                     str(b["raw_days"]), str(b["outside"]), str(b["net_days"]), str(b["earned"]), str(b["taken"]), str(b["balance"])]
            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 11:
                    item.setForeground(QColor(C["neg"] if b["balance"] < 0 else C["accent"]))
                self.table.setItem(row, col_idx, item)
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

    def _show_context_menu(self, pos: QPoint):
        eid = self._sel_id()
        if not eid: return
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        act_print = QAction("🖨 طباعة الكشف التفصيلي", self)
        act_print.triggered.connect(self._print_emp)
        
        act_edit = QAction("✏ تعديل الموظف", self)
        act_edit.triggered.connect(self._edit_emp)
        
        act_leaves = QAction("📅 سجل الإجازات", self)
        act_leaves.triggered.connect(self._view_leaves)
        
        act_add_leave = QAction("➕ إضافة إجازة سريعة", self)
        act_add_leave.triggered.connect(self._quick_leave_window)
        
        act_delete = QAction("🗑 حذف الموظف", self)
        act_delete.triggered.connect(self._delete_emp)
        
        menu.addAction(act_print)
        menu.addAction(act_edit)
        menu.addAction(act_leaves)
        menu.addAction(act_add_leave)
        menu.addSeparator()
        menu.addAction(act_delete)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # أزرار الإدارة والأوامر
    def _add_emp(self): EmployeeDialog(self, on_save=self._refresh).exec()
    
    def _edit_emp(self):
        eid = self._sel_id()
        if not eid: return QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
        EditEmployeeDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel())).exec()

    def _delete_emp(self):
        eid = self._sel_id()
        if not eid: return QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
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
        if not eid: return QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
        LeavesRegisterDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel())).exec()

    def _quick_leave_window(self):
        eid = self._sel_id()
        if not eid: return QMessageBox.warning(self, "تنبيه", "حدد موظفاً أولاً.")
        LeaveQuickDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel())).exec()

    def _open_db_ops(self): DatabaseOperationsDialog(self, refresh_callback=self._refresh).exec()

    def _show_dashboard(self):
        res = generate_dashboard()
        if res == "NoData": QMessageBox.information(self, "معلومة", "لا توجد بيانات إجازات لرسمها.")
        elif not res: QMessageBox.critical(self, "خطأ", "مكتبة Matplotlib غير مثبتة.")

    def _export_all(self):
        if not HAS_XLSX: return QMessageBox.critical(self, "خطأ", "openpyxl غير مثبت.")
        path, _ = QFileDialog.getSaveFileName(self, "تصدير الكل", "", "Excel Files (*.xlsx)")
        if not path: return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "الموظفون"
        ws.sheet_view.rightToLeft = True
        hdrs = ["الرقم الوظيفي","الاسم","العنوان الوظيفي","القسم","الجنس","تاريخ المباشرة",
                "أيام الخدمة","خارج الرصيد","أيام الدوام المحسوبة","المستحقة","المأخوذة","الرصيد","ملاحظات"]
        ws.append(hdrs)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="00C896")
            cell.fill = PatternFill("solid", fgColor="1C2D3E")
        for eid, emp in db.search(self.search_input.text().lower(), self.combo_workplace.currentText()).items():
            b = compute_balance(emp)
            ws.append([eid, emp.get("name",""), emp.get("job_title",""), emp.get("workplace",""), emp.get("gender",""), emp.get("start_date",""),
                       b["raw_days"], b["outside"], b["net_days"], b["earned"], b["taken"], b["balance"], emp.get("notes","")])
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 18
        wb.save(path)
        QMessageBox.information(self, "تم", f"تم التصدير:\n{path}")

    def _print_emp(self):
        eid = self._sel_id()
        if not eid: return QMessageBox.warning(self, "تنبيه", "حدد موظفاً.")
        emp = db.get(eid)
        b = compute_balance(emp)
        history_rows = ""
        for i, lv in enumerate(emp.get("history", [])):
            outside = "نعم" if lv.get("outside_balance") else "لا"
            start_d = lv.get("start_date", lv.get("from_date", ""))
            history_rows += f"""<tr><td>{i+1}</td><td>{lv.get('type','')}</td><td>{start_d}</td><td>{lv.get('amount','')} {lv.get('unit','')}</td><td>{outside}</td><td>{lv.get('order','')}</td><td>{lv.get('order_date','')}</td><td>{lv.get('reason','')}</td></tr>"""
        if not history_rows: history_rows = "<tr><td colspan='8' style='text-align:center;'>لا توجد إجازات مسجلة</td></tr>"
        
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
<h1>البيانات التفصيلية لسجل الإجازات والرصيد التراكمي الخاص بـ: {emp.get('name','')}</h1>
<div class="grid">
  <div class="item"><label>الرقم الوظيفي</label><span>{eid}</span></div>
  <div class="item"><label>العنوان الوظيفي</label><span>{emp.get('job_title','-')}</span></div>
  <div class="item"><label>القسم / مكان العمل</label><span>{emp.get('workplace','-')}</span></div>
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
      <div>توقيع المسؤول: _________________________</div>
  </div>
</div>
<script>window.onload=function(){{window.print();}}</script>
</body></html>"""
        tmp = os.path.join(os.path.expanduser("~"), "_emp_print.html")
        with open(tmp, "w", encoding="utf-8") as f: f.write(html)
        webbrowser.open(f"file://{tmp}")

# ═══════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    
    window = MainApp()
    
    alerts = check_notifications()
    if alerts:
        QMessageBox.warning(window, "تنبيهات النظام", "\n\n".join(alerts))
        
    window.show()
    sys.exit(app.exec())