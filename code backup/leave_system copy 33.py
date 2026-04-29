#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام إدارة الإجازات التراكمية - النسخة المتقدمة (نسخة قاعدة بيانات SQLite)
يدعم: منتقي التاريخ، مكان العمل، استقطاع خارج الرصيد، الأوامر الإدارية، كارت الزمنية،
عرض من اليمين لليسار، التصدير لـ PDF (داعم للعربية) و Excel، واستيراد/تصدير قواعد البيانات للدمج.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime
import os, sqlite3, shutil

# ─── محاولة استيراد مكتبات مساعدة ───
try:
    from tkcalendar import DateEntry
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False
    print("تنبيه: لتفعيل 'منتقي التاريخ' (Date Picker)، يرجى تثبيت مكتبة tkcalendar عبر: pip install tkcalendar")

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
#  الثوابت
# ═══════════════════════════════════════════════
DAYS_PER_LEAVE = 10
MAX_ANNUAL = 36

LEAVE_TYPES_MALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات", "كارت الزمنية"]
LEAVE_TYPES_FEMALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات",
                      "قبل الوضع", "بعد الوضع", "أمومة", "كارت الزمنية"]

UNIT_DAYS = {"يوم": 1, "شهر": 30, "سنة": 365}

C = {
    "bg": "#0F1923", "surface": "#182534", "card": "#1C2D3E",
    "accent": "#00C896", "blue": "#0096FF", "warn": "#FF6135",
    "text": "#E0EAF5", "muted": "#6A8099", "border": "#243447",
    "neg": "#FF4757", "gold": "#FFB830",
}

TITLE_F = ("Segoe UI", 13, "bold")
HEAD_F  = ("Segoe UI", 10, "bold")
BODY_F  = ("Segoe UI", 10)
BIG_F   = ("Segoe UI", 18, "bold")
SMALL_F = ("Segoe UI", 9)


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


def set_treeview_rtl(tree, cols):
    reversed_cols = tuple(reversed(cols))
    tree.configure(displaycolumns=reversed_cols)


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
        conn.execute("PRAGMA foreign_keys = 1") # لتفعيل الحذف التلقائي للإجازات عند حذف الموظف
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
        """دالة للترحيل التلقائي من ملف JSON القديم (إن وجد) إلى قاعدة البيانات الجديدة"""
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
        """تبحث عن الموظفين وتجلب إجازاتهم بكفاءة عالية دون تحميل كل البيانات في حالة البحث"""
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

            # استدعاء الإجازات للموظفين الموجودين في نتيجة البحث فقط
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
#  مساعدات الواجهة
# ═══════════════════════════════════════════════
def apply_styles(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure("TFrame",    background=C["bg"])
    s.configure("TLabel",    background=C["bg"], foreground=C["text"], font=BODY_F)
    s.configure("TEntry",    fieldbackground=C["surface"], foreground=C["text"],
                insertcolor=C["accent"], font=BODY_F,
                bordercolor=C["border"], lightcolor=C["border"], darkcolor=C["border"])
    s.configure("TCombobox", fieldbackground=C["surface"], foreground=C["text"],
                background=C["surface"], font=BODY_F)
    s.configure("TCheckbutton", background=C["card"], foreground=C["text"], font=BODY_F)
    s.configure("Treeview",  background=C["surface"], foreground=C["text"],
                fieldbackground=C["surface"], rowheight=30, font=BODY_F, borderwidth=0)
    s.configure("Treeview.Heading", background=C["card"], foreground=C["accent"],
                font=HEAD_F, relief="flat")
    s.map("Treeview", background=[("selected", C["blue"])], foreground=[("selected","#fff")])
    for nm, bg, fg in [("Accent", C["accent"], C["bg"]),
                        ("Warn",   C["warn"],   "#fff"),
                        ("Blue",   C["blue"],   "#fff"),
                        ("Ghost",  C["surface"], C["text"]),
                        ("Gold",   C["gold"],   C["bg"])]:
        s.configure(f"{nm}.TButton", background=bg, foreground=fg, font=HEAD_F,
                    relief="flat", borderwidth=0, padding=(12, 6))
        s.map(f"{nm}.TButton", relief=[("active","flat")])

def hsep(parent, bg=None):
    tk.Frame(parent, bg=bg or C["border"], height=1).pack(fill="x", padx=10, pady=5)

def make_date_picker(parent):
    if HAS_CALENDAR:
        de = DateEntry(parent, width=12, background=C['card'],
                       foreground='white', borderwidth=0, date_pattern='yyyy-mm-dd',
                       headersbackground=C['surface'], headersforeground=C['text'],
                       selectbackground=C['accent'], selectforeground='white')
        de.pack(fill="x")
        return de
    else:
        e = ttk.Entry(parent)
        e.pack(fill="x")
        e.insert(0, "YYYY-MM-DD")
        return e

def set_entry_value(widget, value):
    if HAS_CALENDAR and isinstance(widget, DateEntry):
        widget.delete(0, tk.END)
        widget.insert(0, value)
    else:
        widget.delete(0, tk.END)
        widget.insert(0, value)


# ═══════════════════════════════════════════════
#  نافذة إضافة / تعديل موظف
# ═══════════════════════════════════════════════
class EmployeeDialog(tk.Toplevel):
    def __init__(self, master, emp_id=None, on_save=None):
        super().__init__(master)
        self.emp_id  = emp_id
        self.on_save = on_save
        self.edit_mode = emp_id is not None

        self.title("تعديل موظف" if self.edit_mode else "إضافة موظف جديد")
        self.geometry("520x700")
        self.configure(bg=C["bg"])
        self.resizable(False, True)
        self.grab_set()
        self.transient(master)

        apply_styles(self)
        self._build()

        if self.edit_mode:
            self._load_emp()

    def _build(self):
        hdr = tk.Frame(self, bg=C["surface"], height=48)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        title = "تعديل بيانات الموظف" if self.edit_mode else "إضافة موظف جديد"
        tk.Label(hdr, text=title, bg=C["surface"], fg=C["accent"], font=TITLE_F).pack(side="right", padx=16, pady=10)

        canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        canvas.pack(fill="both", expand=True)

        self.body = tk.Frame(canvas, bg=C["bg"])
        win_id = canvas.create_window((0, 0), window=self.body, anchor="nw")

        def on_conf(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        self.body.bind("<Configure>", on_conf)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        card = tk.Frame(self.body, bg=C["card"], bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=14, pady=(12,14))
        p2 = card
        pk = dict(padx=18, pady=10)

        def make_row(lbl_t, is_date=False, multiline=False):
            fr = tk.Frame(p2, bg=C["card"]); fr.pack(fill="x", **pk)
            tk.Label(fr, text=lbl_t, bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e", pady=(0,6))
            if is_date:
                return make_date_picker(fr)
            elif multiline:
                txt = tk.Text(fr, height=5, wrap="word", bg=C["surface"], fg=C["text"], insertbackground=C["text"], bd=0)
                txt.pack(fill="both", expand=True)
                return txt
            else:
                e = ttk.Entry(fr); e.pack(fill="x")
                return e

        def make_combo_row(lbl_t, values):
            fr = tk.Frame(p2, bg=C["card"]); fr.pack(fill="x", **pk)
            tk.Label(fr, text=lbl_t, bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e", pady=(0,6))
            v = tk.StringVar()
            cb = ttk.Combobox(fr, textvariable=v, values=values, state="readonly", font=BODY_F)
            cb.pack(fill="x")
            return cb, v

        self.e_id       = make_row("الرقم الوظيفي *")
        self.e_name     = make_row("الاسم الكامل *")
        self.e_title    = make_row("العنوان الوظيفي")
        self.e_workplace= make_row("مكان العمل")
        self.cb_gender, self.v_gender = make_combo_row("الجنس", ["ذكر", "أنثى"])
        self.e_start    = make_row("تاريخ المباشرة *", is_date=True)
        self.e_notes    = make_row("ملاحظات", multiline=True)

        if self.edit_mode:
            self.e_id.configure(state="disabled")

        btn_fr = tk.Frame(self.body, bg=C["bg"]); btn_fr.pack(fill="x", padx=14, pady=12)
        ttk.Button(btn_fr, text="حفظ", style="Accent.TButton", command=self._save).pack(side="right", padx=4)
        ttk.Button(btn_fr, text="إلغاء", style="Ghost.TButton", command=self.destroy).pack(side="right")

    def _load_emp(self):
        emp = db.get(self.emp_id)
        if not emp: return
        self.e_id.configure(state="normal")
        self.e_id.delete(0, tk.END); self.e_id.insert(0, self.emp_id)
        self.e_id.configure(state="disabled")
        self.e_name.delete(0, tk.END);  self.e_name.insert(0, emp.get("name",""))
        self.e_title.delete(0, tk.END); self.e_title.insert(0, emp.get("job_title",""))
        self.e_workplace.delete(0, tk.END); self.e_workplace.insert(0, emp.get("workplace",""))
        self.v_gender.set(emp.get("gender","ذكر"))
        set_entry_value(self.e_start, emp.get("start_date",""))
        self.e_notes.delete("1.0", tk.END); self.e_notes.insert("1.0", emp.get("notes",""))

    def _save(self):
        eid   = self.e_id.get().strip() if not self.edit_mode else self.emp_id
        name  = self.e_name.get().strip()
        start = self.e_start.get().strip()

        if not eid or not name:
            messagebox.showwarning("تنبيه", "الرقم الوظيفي والاسم إلزاميان.", parent=self); return
        if not self.edit_mode and db.get(eid):
            messagebox.showwarning("تنبيه", "الرقم الوظيفي مسجل مسبقاً.", parent=self); return
        try:
            datetime.strptime(start, "%Y-%m-%d")
        except:
            messagebox.showwarning("تنبيه", "تاريخ المباشرة غير صحيح. يجب أن يكون بصيغة YYYY-MM-DD", parent=self); return

        notes = self.e_notes.get("1.0", tk.END).strip()
        fields = {
            "name":       name,
            "job_title":  self.e_title.get().strip(),
            "workplace":  self.e_workplace.get().strip(),
            "gender":     self.v_gender.get() or "ذكر",
            "start_date": start,
            "notes":      notes,
        }
        if self.edit_mode:
            db.update(eid, fields)
        else:
            db.add(eid, fields)

        if self.on_save: self.on_save()
        self.destroy()


# ═══════════════════════════════════════════════
#  نافذة إضافة / تعديل إجازة
# ═══════════════════════════════════════════════
class LeaveDialog(tk.Toplevel):
    def __init__(self, master, emp_id, leave_idx=None, on_save=None):
        super().__init__(master)
        self.emp_id    = emp_id
        self.leave_idx = leave_idx
        self.on_save   = on_save
        self.edit_mode = leave_idx is not None

        emp = db.get(emp_id)
        self.gender = emp.get("gender","ذكر") if emp else "ذكر"

        self.title("تعديل إجازة" if self.edit_mode else "إضافة إجازة")
        self.geometry("420x520")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.grab_set()
        self.transient(master)

        apply_styles(self)
        self._build()
        if self.edit_mode:
            self._load()

    def _build(self):
        hdr = tk.Frame(self, bg=C["surface"], height=46); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="بيانات الإجازة", bg=C["surface"], fg=C["accent"], font=TITLE_F).pack(side="right", padx=16, pady=10)

        p = tk.Frame(self, bg=C["bg"]); p.pack(fill="both", expand=True, padx=14, pady=8)
        pk = dict(fill="x", pady=4)

        ltypes = LEAVE_TYPES_FEMALE if self.gender == "أنثى" else LEAVE_TYPES_MALE
        fr_t = tk.Frame(p, bg=C["card"]); fr_t.pack(**pk)
        tk.Label(fr_t, text="نوع الإجازة", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.v_type = tk.StringVar(value=ltypes[0])
        ttk.Combobox(fr_t, textvariable=self.v_type, values=ltypes, state="readonly", font=BODY_F).pack(fill="x")

        fr_n = tk.Frame(p, bg=C["card"]); fr_n.pack(**pk)
        tk.Label(fr_n, text="العدد والوحدة", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        inner = tk.Frame(fr_n, bg=C["card"]); inner.pack(fill="x")
        self.e_amount = ttk.Entry(inner, width=8); self.e_amount.pack(side="right", padx=(4,0))
        self.v_unit = tk.StringVar(value="يوم")
        ttk.Combobox(inner, textvariable=self.v_unit, values=["يوم","شهر","سنة"],
                     state="readonly", font=BODY_F, width=8).pack(side="right")

        fr_d = tk.Frame(p, bg=C["card"]); fr_d.pack(**pk)
        tk.Label(fr_d, text="بدءاً من تاريخ", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_start_date = make_date_picker(fr_d)

        fr_order = tk.Frame(p, bg=C["card"]); fr_order.pack(**pk)
        tk.Label(fr_order, text="الأمر (اختياري)", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_order = ttk.Entry(fr_order); self.e_order.pack(fill="x")

        fr_od = tk.Frame(p, bg=C["card"]); fr_od.pack(**pk)
        tk.Label(fr_od, text="تاريخ الأمر (اختياري)", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_order_date = make_date_picker(fr_od)
        if not self.edit_mode: set_entry_value(self.e_order_date, "")

        fr_ob = tk.Frame(p, bg=C["card"]); fr_ob.pack(**pk)
        self.v_outside = tk.BooleanVar(value=False)
        ttk.Checkbutton(fr_ob, text="هل يتم احتساب الخدمة أيام الإجازة خارج الرصيد؟",
                        variable=self.v_outside, style="TCheckbutton").pack(anchor="e")

        fr_r = tk.Frame(p, bg=C["card"]); fr_r.pack(**pk)
        tk.Label(fr_r, text="السبب / الملاحظة", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_reason = ttk.Entry(fr_r); self.e_reason.pack(fill="x")

        btn_fr = tk.Frame(p, bg=C["bg"]); btn_fr.pack(fill="x", pady=(10,0))
        ttk.Button(btn_fr, text="حفظ", style="Accent.TButton", command=self._save).pack(side="right", padx=4)
        ttk.Button(btn_fr, text="إلغاء", style="Ghost.TButton", command=self.destroy).pack(side="right")

    def _load(self):
        emp = db.get(self.emp_id)
        lv  = emp["history"][self.leave_idx]
        self.v_type.set(lv.get("type",""))
        self.e_amount.insert(0, str(lv.get("amount","")))
        self.v_unit.set(lv.get("unit","يوم"))
        set_entry_value(self.e_start_date, lv.get("start_date", lv.get("from_date", "")))
        self.e_order.insert(0, lv.get("order",""))
        set_entry_value(self.e_order_date, lv.get("order_date",""))
        self.v_outside.set(lv.get("outside_balance", False))
        self.e_reason.insert(0, lv.get("reason",""))

    def _save(self):
        ltype    = self.v_type.get()
        amount_s = self.e_amount.get().strip()
        unit     = self.v_unit.get()
        start_d  = self.e_start_date.get().strip()

        if not ltype:
            messagebox.showwarning("تنبيه","اختر نوع الإجازة.", parent=self); return
        if not amount_s:
            messagebox.showwarning("تنبيه","أدخل العدد.", parent=self); return
        
        try:
            amount = int(amount_s)
            days_actual = unit_to_days(amount, unit)
        except:
            messagebox.showwarning("تنبيه","أدخل عدداً صحيحاً للعدد.", parent=self); return

        record = {
            "type":           ltype,
            "start_date":     start_d,
            "from_date":      start_d,
            "amount":         amount,
            "unit":           unit,
            "days_actual":    days_actual,
            "order":          self.e_order.get().strip(),
            "order_date":     self.e_order_date.get().strip(),
            "outside_balance": self.v_outside.get(),
            "reason":         self.e_reason.get().strip(),
            "added_date":     str(date.today()),
        }

        if self.edit_mode:
            db.update_leave(self.emp_id, self.leave_idx, record)
        else:
            db.add_leave(self.emp_id, record)

        if self.on_save: self.on_save()
        self.destroy()


# ═══════════════════════════════════════════════
#  نافذة تعديل الموظف (خيارات)
# ═══════════════════════════════════════════════
class EditEmployeeDialog(tk.Toplevel):
    def __init__(self, master, emp_id, on_save=None):
        super().__init__(master)
        self.emp_id  = emp_id
        self.on_save = on_save
        emp = db.get(emp_id)
        self.title(f"تعديل: {emp.get('name','')}")
        self.geometry("340x200")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.grab_set(); self.transient(master)
        apply_styles(self)
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=C["surface"], height=46); hdr.pack(fill="x"); hdr.pack_propagate(False)
        emp = db.get(self.emp_id)
        tk.Label(hdr, text=f"تعديل: {emp.get('name','')}",
                 bg=C["surface"], fg=C["accent"], font=TITLE_F).pack(side="right", padx=16, pady=10)

        p = tk.Frame(self, bg=C["bg"]); p.pack(expand=True, pady=20)
        ttk.Button(p, text="📋  المعلومات العامة", style="Blue.TButton",
                   command=self._open_info).pack(fill="x", padx=30, pady=6)
        ttk.Button(p, text="📅  سجل الإجازات", style="Accent.TButton",
                   command=self._open_leaves).pack(fill="x", padx=30, pady=6)

    def _open_info(self):
        self.destroy()
        EmployeeDialog(self.master, emp_id=self.emp_id, on_save=self.on_save)

    def _open_leaves(self):
        self.destroy()
        LeavesRegisterDialog(self.master, self.emp_id, on_save=self.on_save)


# ═══════════════════════════════════════════════
#  نافذة سجل الإجازات
# ═══════════════════════════════════════════════
class LeavesRegisterDialog(tk.Toplevel):
    def __init__(self, master, emp_id, on_save=None):
        super().__init__(master)
        self.emp_id  = emp_id
        self.on_save = on_save
        emp = db.get(emp_id)
        self.title(f"سجل إجازات: {emp.get('name','')}")
        self.geometry("980x480")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self.grab_set(); self.transient(master)
        apply_styles(self)
        self._build()
        self._refresh()

    def _build(self):
        hdr = tk.Frame(self, bg=C["surface"], height=46); hdr.pack(fill="x"); hdr.pack_propagate(False)
        emp = db.get(self.emp_id)
        tk.Label(hdr, text=f"سجل إجازات: {emp.get('name','')}",
                 bg=C["surface"], fg=C["accent"], font=TITLE_F).pack(side="right", padx=16, pady=10)

        btn_fr = tk.Frame(self, bg=C["bg"]); btn_fr.pack(fill="x", padx=12, pady=6)
        ttk.Button(btn_fr, text="➕ إضافة إجازة", style="Accent.TButton",
                   command=self._add).pack(side="right", padx=4)
        ttk.Button(btn_fr, text="✏  تعديل المحددة", style="Blue.TButton",
                   command=self._edit).pack(side="right", padx=4)
        ttk.Button(btn_fr, text="🗑 حذف المحددة", style="Warn.TButton",
                   command=self._delete).pack(side="right", padx=4)
        ttk.Button(btn_fr, text="📊 تصدير Excel", style="Ghost.TButton",
                   command=self._export_xlsx).pack(side="left", padx=4)
        ttk.Button(btn_fr, text="📄 تصدير PDF", style="Ghost.TButton",
                   command=self._export_pdf).pack(side="left", padx=4)

        cols = ("idx","type","start_date","amount","unit","days","outside","order","order_date","reason","added")
        hdrs = ("#","النوع","بدءاً من","العدد","الوحدة","الأيام الفعلية","خارج الرصيد","الأمر","تاريخ الأمر","السبب","تاريخ الإضافة")
        wrap = tk.Frame(self, bg=C["bg"]); wrap.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        widths = [35,80,90,50,55,80,80,70,80,120,90]
        for col,hd,w in zip(cols,hdrs,widths):
            self.tree.heading(col, text=hd); self.tree.column(col, width=w, anchor="center", stretch=True)
        set_treeview_rtl(self.tree, cols)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        xsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=xsb.set)
        vsb.pack(side="left", fill="y")
        xsb.pack(side="bottom", fill="x")
        self.tree.pack(side="right", fill="both", expand=True)

    def _refresh(self):
        for r in self.tree.get_children(): self.tree.delete(r)
        emp = db.get(self.emp_id)
        for i, lv in enumerate(emp.get("history", [])):
            self.tree.insert("","end", values=(
                i+1, lv.get("type",""), lv.get("start_date", lv.get("from_date","")), 
                lv.get("amount",""), lv.get("unit","يوم"), lv.get("days_actual",0),
                "نعم" if lv.get("outside_balance") else "لا",
                lv.get("order",""), lv.get("order_date",""),
                lv.get("reason",""), lv.get("added_date","")
            ))

    def _sel_idx(self):
        sel = self.tree.selection()
        if not sel: return None
        return int(self.tree.item(sel[0],"values")[0]) - 1

    def _add(self):
        LeaveDialog(self, self.emp_id, on_save=self._refresh_and_notify)

    def _edit(self):
        idx = self._sel_idx()
        if idx is None: messagebox.showwarning("تنبيه","حدد إجازة.", parent=self); return
        LeaveDialog(self, self.emp_id, leave_idx=idx, on_save=self._refresh_and_notify)

    def _delete(self):
        idx = self._sel_idx()
        if idx is None: messagebox.showwarning("تنبيه","حدد إجازة.", parent=self); return
        if messagebox.askyesno("تأكيد","حذف هذه الإجازة؟", parent=self):
            db.delete_leave(self.emp_id, idx)
            self._refresh_and_notify()

    def _refresh_and_notify(self):
        self._refresh()
        if self.on_save: self.on_save()

    def _export_xlsx(self):
        if not HAS_XLSX:
            messagebox.showerror("خطأ","openpyxl غير مثبت.", parent=self); return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
               filetypes=[("Excel","*.xlsx")], parent=self)
        if not path: return
        emp = db.get(self.emp_id)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "سجل الإجازات"
        ws.sheet_view.rightToLeft = True
        hdrs = ["#","النوع","بدءاً من","العدد","الوحدة","الأيام الفعلية","خارج الرصيد","الأمر","تاريخ الأمر","السبب","تاريخ الإضافة"]
        ws.append(hdrs)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="1C2D3E")
            cell.font = Font(bold=True, color="00C896")
        for i,lv in enumerate(emp.get("history",[])):
            ws.append([i+1, lv.get("type",""), lv.get("start_date", lv.get("from_date","")),
                       lv.get("amount",""), lv.get("unit",""), lv.get("days_actual",0),
                       "نعم" if lv.get("outside_balance") else "لا",
                       lv.get("order",""), lv.get("order_date",""),
                       lv.get("reason",""), lv.get("added_date","")])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 15
        wb.save(path)
        messagebox.showinfo("تم", f"تم التصدير:\n{path}", parent=self)

    def _export_pdf(self):
        if not HAS_PDF:
            messagebox.showerror("خطأ","reportlab غير مثبت.", parent=self); return
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
        except ImportError:
            messagebox.showerror("خطأ", "لتصدير PDF باللغة العربية، يرجى تثبيت المكتبات التالية عبر موجه الأوامر:\npip install arabic-reshaper python-bidi", parent=self)
            return

        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        try:
            pdfmetrics.registerFont(TTFont('ArabicFont', 'arial.ttf'))
        except Exception:
            messagebox.showerror("خطأ", "لم يتم العثور على خط Arial في النظام لدعم اللغة العربية.", parent=self)
            return

        path = filedialog.asksaveasfilename(defaultextension=".pdf",
            filetypes=[("PDF","*.pdf")], parent=self)
        if not path: return

        def ar(text):
            if not text: return ""
            reshaped_text = arabic_reshaper.reshape(str(text))
            bidi_text = get_display(reshaped_text)
            return bidi_text

        emp = db.get(self.emp_id)
        doc = SimpleDocTemplate(path, pagesize=A4,
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            name='ArabicTitle',
            parent=styles['Title'],
            fontName='ArabicFont',
            fontSize=16,
            alignment=1 
        )

        story = []
        title_line = ar(f"سجل إجازات: {emp.get('job_title', '')} - {emp.get('name', '')}")
        story.append(Paragraph(title_line, title_style))
        story.append(Spacer(1, 0.3*cm))

        info_style = ParagraphStyle(
            name='ArabicInfo',
            parent=styles['Normal'],
            fontName='ArabicFont',
            fontSize=12,
            alignment=1  
        )
        info_line = ar(f"الرقم الوظيفي: {self.emp_id} ، مكان العمل: {emp.get('workplace', '')}")
        story.append(Paragraph(info_line, info_style))
        story.append(Spacer(1, 0.3*cm))

        headers = [ar("تاريخ الإضافة"),ar("السبب"), ar("تاريخ الأمر"), ar("الأمر"), ar("خارج الرصيد"), ar("الأيام"), ar("بدءاً من"), ar("النوع"), ar("#")]
        data = [headers]

        for i,lv in enumerate(emp.get("history",[])):
            row = [
                ar(lv.get("added_date","")),
                ar(lv.get("reason","")),
                ar(lv.get("order_date","")),
                ar(lv.get("order","")),
                ar("نعم" if lv.get("outside_balance") else "لا"),
                ar(str(lv.get("days_actual",0))),
                ar(lv.get("start_date", lv.get("from_date",""))),
                ar(lv.get("type","")),
                ar(str(i+1))
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
        messagebox.showinfo("تم", f"تم التصدير بنجاح:\n{path}", parent=self)


# ═══════════════════════════════════════════════
#  النافذة الرئيسية
# ═══════════════════════════════════════════════
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("نظام إدارة الإجازات التراكمية")
        self.geometry("1280x780")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        apply_styles(self)
        self._ui()
        self._refresh()

    def _ui(self):
        hdr = tk.Frame(self, bg=C["surface"], height=54)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="نظام إدارة الإجازات التراكمية",
                 bg=C["surface"], fg=C["accent"], font=TITLE_F).pack(side="right", padx=20, pady=12)
        tk.Label(hdr, text=f"يوم إجازة لكل {DAYS_PER_LEAVE} أيام دوام  |  المعدل السنوي {MAX_ANNUAL} يوم",
                 bg=C["surface"], fg=C["muted"], font=BODY_F).pack(side="left", padx=20)

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=10)

        side = tk.Frame(body, bg=C["card"], width=285)
        side.pack(side="right", fill="y", padx=(8,0)); side.pack_propagate(False)
        self._sidebar(side)

        center = tk.Frame(body, bg=C["bg"])
        center.pack(side="right", fill="both", expand=True)
        self._table(center)
        self._detail_panel(center)

    def _sidebar(self, p):
        pk = dict(padx=12, pady=3)

        ttk.Button(p, text="➕  إضافة موظف جديد", style="Accent.TButton",
                   command=self._add_emp).pack(fill="x", padx=12, pady=(12,6))

        hsep(p)

        tk.Label(p, text="تسجيل إجازة للموظف المحدد",
                 bg=C["card"], fg=C["blue"], font=HEAD_F).pack(anchor="e", **pk)

        fr_t = tk.Frame(p, bg=C["card"]); fr_t.pack(fill="x", **pk)
        tk.Label(fr_t, text="نوع الإجازة", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.v_ltype = tk.StringVar(value=LEAVE_TYPES_MALE[0])
        self.cb_ltype = ttk.Combobox(fr_t, textvariable=self.v_ltype,
                                      values=LEAVE_TYPES_MALE, state="readonly", font=BODY_F)
        self.cb_ltype.pack(fill="x")

        fr_n = tk.Frame(p, bg=C["card"]); fr_n.pack(fill="x", **pk)
        tk.Label(fr_n, text="العدد والوحدة", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        inner = tk.Frame(fr_n, bg=C["card"]); inner.pack(fill="x")
        self.e_lamount = ttk.Entry(inner, width=7); self.e_lamount.pack(side="right", padx=(4,0))
        self.v_lunit = tk.StringVar(value="يوم")
        ttk.Combobox(inner, textvariable=self.v_lunit, values=["يوم","شهر","سنة"],
                     state="readonly", font=BODY_F, width=7).pack(side="right")
        
        fr_start = tk.Frame(p, bg=C["card"]); fr_start.pack(fill="x", **pk)
        tk.Label(fr_start, text="بدءاً من تاريخ", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_lstart = make_date_picker(fr_start)

        fr_order = tk.Frame(p, bg=C["card"]); fr_order.pack(fill="x", **pk)
        tk.Label(fr_order, text="الأمر (اختياري)", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_lorder = ttk.Entry(fr_order); self.e_lorder.pack(fill="x")

        fr_od = tk.Frame(p, bg=C["card"]); fr_od.pack(fill="x", **pk)
        tk.Label(fr_od, text="تاريخ الأمر (اختياري)", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_lorder_date = make_date_picker(fr_od)
        set_entry_value(self.e_lorder_date, "")

        fr_ob = tk.Frame(p, bg=C["card"]); fr_ob.pack(fill="x", **pk)
        self.v_outside = tk.BooleanVar(value=False)
        ttk.Checkbutton(fr_ob, text="خارج الرصيد؟", variable=self.v_outside).pack(anchor="e")

        fr_r = tk.Frame(p, bg=C["card"]); fr_r.pack(fill="x", **pk)
        tk.Label(fr_r, text="السبب", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_lreason = ttk.Entry(fr_r); self.e_lreason.pack(fill="x")

        ttk.Button(p, text="تسجيل الإجازة", style="Blue.TButton",
                   command=self._quick_leave).pack(fill="x", padx=12, pady=(6,4))

        hsep(p)

        ttk.Button(p, text="📅  سجل الإجازات", style="Ghost.TButton",
                   command=self._view_leaves).pack(fill="x", **pk)
        ttk.Button(p, text="✏  تعديل الموظف", style="Ghost.TButton",
                   command=self._edit_emp).pack(fill="x", **pk)
        ttk.Button(p, text="🗑  حذف الموظف", style="Warn.TButton",
                   command=self._delete_emp).pack(fill="x", **pk)

        hsep(p)

        # ── أزرار الاستيراد والتصدير لقاعدة البيانات ──
        ttk.Button(p, text="💾  تصدير قاعدة البيانات", style="Ghost.TButton",
                   command=self._export_db).pack(fill="x", **pk)
        ttk.Button(p, text="📂  استيراد قاعدة البيانات", style="Ghost.TButton",
                   command=self._import_db).pack(fill="x", **pk)

        hsep(p)

        ttk.Button(p, text="📊  تصدير الكل Excel", style="Gold.TButton",
                   command=self._export_all).pack(fill="x", **pk)
        ttk.Button(p, text="🖨  طباعة تفاصيل", style="Ghost.TButton",
                   command=self._print_emp).pack(fill="x", **pk)

    def _table(self, p):
        top = tk.Frame(p, bg=C["bg"]); top.pack(fill="x", pady=(0,6))
        tk.Label(top, text="قائمة الموظفين", bg=C["bg"], fg=C["text"], font=HEAD_F).pack(side="right")
        self.sv = tk.StringVar(); self.sv.trace_add("write", lambda *_: self._refresh())
        ttk.Entry(top, textvariable=self.sv, width=22).pack(side="left")
        tk.Label(top, text="بحث:", bg=C["bg"], fg=C["muted"]).pack(side="left", padx=(0,4))

        cols = ("id","name","title","workplace","gender","start","raw","outside","net","earned","taken","balance")
        hdrs = ("الرقم الوظيفي","الاسم","العنوان الوظيفي","مكان العمل","الجنس","المباشرة",
                "أيام الخدمة","خارج الرصيد","الدوام المحسوبة","المستحقة","المأخوذة","الرصيد")
        wrap = tk.Frame(p, bg=C["bg"]); wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        widths = [80,120,110,110,50,90,75,80,100,70,70,70]
        for col,hd,w in zip(cols,hdrs,widths):
            self.tree.heading(col,text=hd); self.tree.column(col,width=w,anchor="center",stretch=True)
        set_treeview_rtl(self.tree, cols)
        vsb = ttk.Scrollbar(wrap,orient="vertical",command=self.tree.yview)
        xsb = ttk.Scrollbar(wrap,orient="horizontal",command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=xsb.set)
        vsb.pack(side="left",fill="y")
        xsb.pack(side="bottom",fill="x")
        self.tree.pack(side="right",fill="both",expand=True)
        self.tree.tag_configure("pos",foreground=C["accent"])
        self.tree.tag_configure("neg",foreground=C["neg"])
        self.tree.bind("<<TreeviewSelect>>", self._on_sel)
        
    def _detail_panel(self, p):
        f = tk.Frame(p, bg=C["card"], height=110)
        f.pack(fill="x", pady=(8,0)); f.pack_propagate(False)
        g = tk.Frame(f, bg=C["card"]); g.pack(expand=True, pady=8)
        self.dlbls = {}
        items = [("name","الاسم"), ("job_title","العنوان الوظيفي"), ("workplace","مكان العمل"),
                 ("gender","الجنس"), ("start_date","تاريخ المباشرة"), ("raw_days","أيام الخدمة"),
                 ("net_days","أيام الدوام المحسوبة"), ("earned","المستحقة"),
                 ("taken","المأخوذة"), ("balance","الرصيد")]
        
        total_cols = len(items)
        for i, (k, lb) in enumerate(items):
            col_idx = total_cols - i - 1
            tk.Label(g, text=lb, bg=C["card"], fg=C["muted"], font=SMALL_F).grid(row=0,column=col_idx,padx=8,sticky="s")
            font = BIG_F if k=="balance" else HEAD_F
            v = tk.Label(g, text="—", bg=C["card"], fg=C["text"], font=font)
            v.grid(row=1, column=col_idx, padx=8, sticky="n"); self.dlbls[k]=v

    # ── منطق ──
    def _refresh(self):
        q = self.sv.get().lower() if hasattr(self,"sv") else ""
        for r in self.tree.get_children(): self.tree.delete(r)
        for eid, emp in db.search(q).items():
            b = compute_balance(emp)
            tag = "pos" if b["balance"]>=0 else "neg"
            self.tree.insert("","end",iid=eid,tags=(tag,),values=(
                eid, emp.get("name",""), emp.get("job_title",""), emp.get("workplace",""), emp.get("gender",""),
                emp.get("start_date",""), b["raw_days"], b["outside"],
                b["net_days"], b["earned"], b["taken"], b["balance"]
            ))

    def _sel_id(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _on_sel(self, _):
        eid = self._sel_id()
        if not eid: return
        emp = db.get(eid)
        b   = compute_balance(emp)
        self._update_leave_types(emp.get("gender","ذكر"))
        for k,v in self.dlbls.items():
            if k in ("raw_days","net_days","earned","taken","balance"):
                val = b.get({"raw_days":"raw_days","net_days":"net_days",
                              "earned":"earned","taken":"taken","balance":"balance"}[k], "—")
                color = (C["accent"] if b["balance"]>=0 else C["neg"]) if k=="balance" else C["text"]
                suffix = " يوم"
            else:
                val = emp.get(k,"—")
                color = C["text"]; suffix=""
            v.config(text=f"{val}{suffix}", fg=color)

    def _update_leave_types(self, gender):
        types = LEAVE_TYPES_FEMALE if gender=="أنثى" else LEAVE_TYPES_MALE
        self.cb_ltype.configure(values=types)
        if self.v_ltype.get() not in types:
            self.v_ltype.set(types[0])

    def _add_emp(self):
        EmployeeDialog(self, on_save=self._refresh)

    def _edit_emp(self):
        eid = self._sel_id()
        if not eid: messagebox.showwarning("تنبيه","حدد موظفاً."); return
        EditEmployeeDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel(None)))

    def _delete_emp(self):
        eid = self._sel_id()
        if not eid: messagebox.showwarning("تنبيه","حدد موظفاً."); return
        name = db.get(eid).get("name","")
        if messagebox.askyesno("تأكيد",f"حذف '{name}'؟"):
            db.delete(eid)
            self._refresh()
            for v in self.dlbls.values(): v.config(text="—",fg=C["text"])

    def _view_leaves(self):
        eid = self._sel_id()
        if not eid: messagebox.showwarning("تنبيه","حدد موظفاً."); return
        LeavesRegisterDialog(self, eid, on_save=lambda: (self._refresh(), self._on_sel(None)))

    def _quick_leave(self):
        eid = self._sel_id()
        if not eid: messagebox.showwarning("تنبيه","حدد موظفاً."); return
        ltype  = self.v_ltype.get()
        amount_s = self.e_lamount.get().strip()
        unit   = self.v_lunit.get()
        outside= self.v_outside.get()
        reason = self.e_lreason.get().strip()
        start_d= self.e_lstart.get().strip()
        order_n= self.e_lorder.get().strip()
        order_d= self.e_lorder_date.get().strip()

        if not amount_s: messagebox.showwarning("تنبيه","أدخل عدد الأيام."); return
        try: amount = int(amount_s)
        except: messagebox.showwarning("تنبيه","أدخل عدداً صحيحاً للعدد."); return
        days = unit_to_days(amount, unit)

        emp = db.get(eid)
        b   = compute_balance(emp)
        if days > b["balance"] and not outside:
            if not messagebox.askyesno("تجاوز الرصيد",
                f"الرصيد المتاح: {b['balance']} يوم.\nهل تريد المتابعة؟"): return

        record = {
            "type": ltype,
            "start_date": start_d, "from_date": start_d,
            "amount": amount, "unit": unit, "days_actual": days,
            "order": order_n, "order_date": order_d,
            "outside_balance": outside, "reason": reason,
            "added_date": str(date.today()),
        }
        db.add_leave(eid, record)
        self.e_lamount.delete(0,tk.END); self.e_lreason.delete(0,tk.END)
        self.e_lorder.delete(0,tk.END); set_entry_value(self.e_lorder_date, "")
        self._refresh(); self._on_sel(None)

    # ── التصدير والاستيراد ──
    def _export_db(self):
        path = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("Database Files", "*.db")], initialfile="employees_backup.db")
        if not path: return
        try:
            shutil.copy2("employees_leave.db", path)
            messagebox.showinfo("نجاح", f"تم تصدير قاعدة البيانات بنجاح إلى:\n{path}")
        except Exception as e:
            messagebox.showerror("خطأ", f"حدث خطأ أثناء التصدير:\n{e}")

    def _import_db(self):
        path = filedialog.askopenfilename(filetypes=[("Database Files", "*.db")])
        if not path: return
        
        try:
            with sqlite3.connect(path) as imported_conn:
                imported_conn.row_factory = sqlite3.Row
                ic = imported_conn.cursor()
                
                # التأكد من أن الملف هو قاعدة بيانات صالحة للبرنامج
                ic.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees'")
                if not ic.fetchone():
                    messagebox.showerror("خطأ", "الملف المحدد لا يحتوي على قاعدة بيانات صالحة للبرنامج.")
                    return

                ic.execute("SELECT * FROM employees")
                imported_emps = ic.fetchall()

                added_count = 0
                updated_count = 0
                skipped_count = 0
                
                for imp_emp in imported_emps:
                    eid = imp_emp['emp_id']
                    
                    # جلب إجازات الموظف من قاعدة البيانات المستوردة
                    ic.execute("SELECT * FROM leaves WHERE emp_id=? ORDER BY id ASC", (eid,))
                    imp_leaves = ic.fetchall()

                    existing = db.get(eid)
                    if existing:
                        # سؤال المستخدم عن التعارض
                        ans = messagebox.askyesnocancel("تعارض بيانات", 
                            f"الموظف ( {imp_emp['name']} ) بالرقم الوظيفي ( {eid} ) موجود بالفعل في النظام.\n\n"
                            "• اضغط (Yes/نعم) لاستبدال بياناته القديمة بالبيانات المستوردة.\n"
                            "• اضغط (No/لا) للاحتفاظ ببياناته الحالية وتخطي الاستيراد له.\n"
                            "• اضغط (Cancel/إلغاء) لإيقاف عملية الاستيراد بالكامل.")
                        
                        if ans is None: # Cancel
                            messagebox.showinfo("إلغاء", "تم إيقاف عملية الاستيراد بناءً على طلبك.")
                            self._refresh()
                            return
                        elif ans is True: # Yes (Replace)
                            db.delete(eid)
                            self._insert_imported_emp(imp_emp, imp_leaves)
                            updated_count += 1
                        else: # No (Skip)
                            skipped_count += 1
                    else:
                        self._insert_imported_emp(imp_emp, imp_leaves)
                        added_count += 1
            
            messagebox.showinfo("اكتمل الاستيراد", f"تم الاستيراد بنجاح.\n\nتمت إضافة: {added_count} موظف جديد\nتم تحديث: {updated_count} موظف\nتم تخطي: {skipped_count} موظف")
            self._refresh()

        except Exception as e:
            messagebox.showerror("خطأ", f"حدث خطأ أثناء الاستيراد:\n{e}")

    def _insert_imported_emp(self, imp_emp, imp_leaves):
        """دالة مساعدة لإدراج الموظف المستورد وإجازاته"""
        db.add(imp_emp['emp_id'], dict(imp_emp))
        for lv in imp_leaves:
            lv_dict = dict(lv)
            lv_dict['order'] = lv_dict.pop('order_num', '')
            db.add_leave(imp_emp['emp_id'], lv_dict)

    def _export_all(self):
        if not HAS_XLSX: messagebox.showerror("خطأ","openpyxl غير مثبت."); return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
               filetypes=[("Excel","*.xlsx")])
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
        messagebox.showinfo("تم",f"تم التصدير:\n{path}")

    def _print_emp(self):
        eid = self._sel_id()
        if not eid: messagebox.showwarning("تنبيه","حدد موظفاً."); return
        emp = db.get(eid)
        b   = compute_balance(emp)

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
  
  .footer-signatures {{ 
      display: flex; 
      justify-content: space-between; 
      margin-top: 60px; 
      font-size: 14px; 
      font-weight: bold; 
      page-break-inside: avoid;
  }}
  
  @media print{{
      body{{padding:20px;}}
      .page-break {{ margin-top: 0; }}
  }}
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
    <thead>
      <tr>
        <th>#</th>
        <th>النوع</th>
        <th>بدءاً من</th>
        <th>العدد</th>
        <th>خارج الرصيد؟</th>
        <th>الأمر</th>
        <th>تاريخ الأمر</th>
        <th>السبب</th>
      </tr>
    </thead>
    <tbody>
      {history_rows}
    </tbody>
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
    MainApp().mainloop()