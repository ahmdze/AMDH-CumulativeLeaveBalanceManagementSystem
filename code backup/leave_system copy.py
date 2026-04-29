#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام إدارة الإجازات التراكمية - النسخة المتقدمة
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime, timedelta
import json, os, csv, math, subprocess, sys

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
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
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# ═══════════════════════════════════════════════
#  الثوابت
# ═══════════════════════════════════════════════
DAYS_PER_LEAVE = 10
MAX_ANNUAL = 36

LEAVE_TYPES_MALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات"]
LEAVE_TYPES_FEMALE = ["اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات",
                      "قبل الوضع", "بعد الوضع", "أمومة"]

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
    """أيام من تاريخ المباشرة حتى اليوم."""
    try:
        sd = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        return max(0, (date.today() - sd).days)
    except:
        return 0

def earned_from_days(net_days: int) -> int:
    return net_days // DAYS_PER_LEAVE

def total_leave_days(leaves: list) -> int:
    """مجموع أيام الإجازات المسجلة."""
    total = 0
    for lv in leaves:
        total += lv.get("days_actual", lv.get("days", 0))
    return total

def leave_days_outside(leaves: list) -> int:
    """مجموع أيام الإجازات التي مؤشر عليها 'خارج الرصيد'."""
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
#  قاعدة البيانات
# ═══════════════════════════════════════════════
DB_FILE = "employees_leave.json"

class DB:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except:
                self.data = {}

    def save(self):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add(self, emp_id, fields: dict):
        self.data[emp_id] = fields
        self.save()

    def update(self, emp_id, fields: dict):
        if emp_id in self.data:
            self.data[emp_id].update(fields)
            self.save()

    def delete(self, emp_id):
        if emp_id in self.data:
            del self.data[emp_id]
            self.save()

    def get(self, emp_id):
        return self.data.get(emp_id)

    def all(self):
        return self.data


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

def lbl(parent, text, fg=None, font=None, bg=None):
    return tk.Label(parent, text=text,
                    bg=bg or C["card"], fg=fg or C["text"],
                    font=font or BODY_F)

def hsep(parent, bg=None):
    tk.Frame(parent, bg=bg or C["border"], height=1).pack(fill="x", padx=10, pady=5)

def card_frame(parent, **kwargs):
    return tk.Frame(parent, bg=C["card"], **kwargs)

def field_row(parent, label_text, widget_factory):
    fr = tk.Frame(parent, bg=C["card"])
    fr.pack(fill="x", padx=14, pady=3)
    tk.Label(fr, text=label_text, bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
    w = widget_factory(fr)
    return fr, w

def make_entry(parent):
    e = ttk.Entry(parent)
    e.pack(fill="x")
    return e

def make_combo(parent, values, var=None):
    v = var or tk.StringVar()
    cb = ttk.Combobox(parent, textvariable=v, values=values, state="readonly", font=BODY_F)
    cb.pack(fill="x")
    return cb, v

def num(s, default=0):
    try:
        return int(float(s.strip()))
    except:
        return default


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
        self.geometry("480x600")
        self.configure(bg=C["bg"])
        self.resizable(False, True)
        self.grab_set()
        self.transient(master)

        apply_styles(self)
        self._build()

        if self.edit_mode:
            self._load_emp()

    def _build(self):
        # ─ رأس ─
        hdr = tk.Frame(self, bg=C["surface"], height=48)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        title = "تعديل بيانات الموظف" if self.edit_mode else "إضافة موظف جديد"
        tk.Label(hdr, text=title, bg=C["surface"], fg=C["accent"], font=TITLE_F).pack(side="right", padx=16, pady=10)

        # ─ محتوى قابل للتمرير ─
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

        p = self.body
        pk = dict(padx=14, pady=4)

        def row(lbl_text, factory):
            fr = tk.Frame(p, bg=C["card"]); fr.pack(fill="x", **pk)
            tk.Label(fr, text=lbl_text, bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
            return factory(fr)

        # الحقول
        self.v_id    = row("الرقم الوظيفي *", lambda f: (ttk.Entry(f), ttk.Entry(f).pack(fill="x") or None))
        # إعادة بناء صحيحة
        p2 = p

        def make_row(lbl_t):
            fr = tk.Frame(p2, bg=C["card"]); fr.pack(fill="x", **pk)
            tk.Label(fr, text=lbl_t, bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
            e = ttk.Entry(fr); e.pack(fill="x")
            return e

        def make_combo_row(lbl_t, values):
            fr = tk.Frame(p2, bg=C["card"]); fr.pack(fill="x", **pk)
            tk.Label(fr, text=lbl_t, bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
            v = tk.StringVar()
            cb = ttk.Combobox(fr, textvariable=v, values=values, state="readonly", font=BODY_F)
            cb.pack(fill="x")
            return cb, v

        self.e_id      = make_row("الرقم الوظيفي *")
        self.e_name    = make_row("الاسم الكامل *")
        self.e_title   = make_row("العنوان الوظيفي")
        self.cb_gender, self.v_gender = make_combo_row("الجنس", ["ذكر", "أنثى"])
        self.e_start   = make_row("تاريخ المباشرة (YYYY-MM-DD) *")
        self.e_notes   = make_row("ملاحظات")

        if self.edit_mode:
            self.e_id.configure(state="disabled")

        # أزرار
        btn_fr = tk.Frame(p, bg=C["bg"]); btn_fr.pack(fill="x", padx=14, pady=12)
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
        self.v_gender.set(emp.get("gender","ذكر"))
        self.e_start.delete(0, tk.END); self.e_start.insert(0, emp.get("start_date",""))
        self.e_notes.delete(0, tk.END); self.e_notes.insert(0, emp.get("notes",""))

    def _save(self):
        eid   = self.e_id.get().strip() if not self.edit_mode else self.emp_id
        name  = self.e_name.get().strip()
        start = self.e_start.get().strip()

        if not eid or not name:
            messagebox.showwarning("تنبيه", "الرقم الوظيفي والاسم إلزاميان.", parent=self); return
        if not self.edit_mode and eid in db.all():
            messagebox.showwarning("تنبيه", "الرقم الوظيفي مسجل مسبقاً.", parent=self); return
        try:
            datetime.strptime(start, "%Y-%m-%d")
        except:
            messagebox.showwarning("تنبيه", "تاريخ المباشرة غير صحيح. الصيغة: YYYY-MM-DD", parent=self); return

        fields = {
            "name":       name,
            "job_title":  self.e_title.get().strip(),
            "gender":     self.v_gender.get() or "ذكر",
            "start_date": start,
            "notes":      self.e_notes.get().strip(),
        }
        if self.edit_mode:
            db.update(eid, fields)
        else:
            fields["history"] = []
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
        self.geometry("420x380")
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

        def row(lbl_t, factory):
            fr = tk.Frame(p, bg=C["card"]); fr.pack(**pk)
            tk.Label(fr, text=lbl_t, bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
            return factory(fr)

        # نوع الإجازة
        ltypes = LEAVE_TYPES_FEMALE if self.gender == "أنثى" else LEAVE_TYPES_MALE
        fr_t = tk.Frame(p, bg=C["card"]); fr_t.pack(**pk)
        tk.Label(fr_t, text="نوع الإجازة", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.v_type = tk.StringVar(value=ltypes[0])
        ttk.Combobox(fr_t, textvariable=self.v_type, values=ltypes, state="readonly", font=BODY_F).pack(fill="x")

        # تاريخ البداية والنهاية
        fr_d = tk.Frame(p, bg=C["card"]); fr_d.pack(**pk)
        tk.Label(fr_d, text="من تاريخ (YYYY-MM-DD)", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_from = ttk.Entry(fr_d); self.e_from.pack(fill="x")

        fr_d2 = tk.Frame(p, bg=C["card"]); fr_d2.pack(**pk)
        tk.Label(fr_d2, text="إلى تاريخ (YYYY-MM-DD)", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        self.e_to = ttk.Entry(fr_d2); self.e_to.pack(fill="x")

        # عدد + وحدة
        fr_n = tk.Frame(p, bg=C["card"]); fr_n.pack(**pk)
        tk.Label(fr_n, text="العدد والوحدة", bg=C["card"], fg=C["muted"], font=SMALL_F).pack(anchor="e")
        inner = tk.Frame(fr_n, bg=C["card"]); inner.pack(fill="x")
        self.e_amount = ttk.Entry(inner, width=8); self.e_amount.pack(side="right", padx=(4,0))
        self.v_unit = tk.StringVar(value="يوم")
        ttk.Combobox(inner, textvariable=self.v_unit, values=["يوم","شهر","سنة"],
                     state="readonly", font=BODY_F, width=8).pack(side="right")

        # خارج الرصيد
        fr_ob = tk.Frame(p, bg=C["card"]); fr_ob.pack(**pk)
        self.v_outside = tk.BooleanVar(value=False)
        ttk.Checkbutton(fr_ob, text="هل يتم احتساب الخدمة أيام الإجازة خارج الرصيد؟",
                        variable=self.v_outside, style="TCheckbutton").pack(anchor="e")

        # السبب
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
        self.e_from.insert(0, lv.get("from_date",""))
        self.e_to.insert(0, lv.get("to_date",""))
        self.e_amount.insert(0, str(lv.get("amount","")))
        self.v_unit.set(lv.get("unit","يوم"))
        self.v_outside.set(lv.get("outside_balance", False))
        self.e_reason.insert(0, lv.get("reason",""))

    def _save(self):
        ltype  = self.v_type.get()
        amount_s = self.e_amount.get().strip()
        unit   = self.v_unit.get()
        frm    = self.e_from.get().strip()
        to     = self.e_to.get().strip()

        if not ltype:
            messagebox.showwarning("تنبيه","اختر نوع الإجازة.", parent=self); return

        # إذا أدخل تاريخين احسب الأيام تلقائياً
        days_actual = 0
        if frm and to:
            try:
                fd = datetime.strptime(frm,"%Y-%m-%d").date()
                td = datetime.strptime(to,"%Y-%m-%d").date()
                days_actual = max(0,(td-fd).days)
            except:
                messagebox.showwarning("تنبيه","تواريخ غير صحيحة.", parent=self); return
        elif amount_s:
            try:
                amount = int(amount_s)
                days_actual = unit_to_days(amount, unit)
            except:
                messagebox.showwarning("تنبيه","أدخل عدداً صحيحاً.", parent=self); return
        else:
            messagebox.showwarning("تنبيه","أدخل التواريخ أو العدد.", parent=self); return

        amount_val = int(amount_s) if amount_s else days_actual

        record = {
            "type":           ltype,
            "from_date":      frm,
            "to_date":        to,
            "amount":         amount_val,
            "unit":           unit,
            "days_actual":    days_actual,
            "outside_balance": self.v_outside.get(),
            "reason":         self.e_reason.get().strip(),
            "added_date":     str(date.today()),
        }

        emp = db.get(self.emp_id)
        if self.edit_mode:
            emp["history"][self.leave_idx] = record
        else:
            emp["history"].append(record)
        db.save()

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
        self.geometry("860x480")
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

        cols = ("idx","type","from","to","amount","unit","days","outside","reason","added")
        hdrs = ("#","النوع","من","إلى","العدد","الوحدة","الأيام الفعلية","خارج الرصيد","السبب","تاريخ الإضافة")
        wrap = tk.Frame(self, bg=C["bg"]); wrap.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        widths = [35,90,90,90,55,60,90,90,140,100]
        for col,hd,w in zip(cols,hdrs,widths):
            self.tree.heading(col, text=hd); self.tree.column(col, width=w, anchor="center")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="left", fill="y"); self.tree.pack(side="right", fill="both", expand=True)

    def _refresh(self):
        for r in self.tree.get_children(): self.tree.delete(r)
        emp = db.get(self.emp_id)
        for i, lv in enumerate(emp.get("history", [])):
            self.tree.insert("","end", values=(
                i+1, lv.get("type",""), lv.get("from_date",""), lv.get("to_date",""),
                lv.get("amount",""), lv.get("unit","يوم"), lv.get("days_actual",0),
                "نعم" if lv.get("outside_balance") else "لا",
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
            emp = db.get(self.emp_id)
            emp["history"].pop(idx)
            db.save()
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
        hdrs = ["#","النوع","من","إلى","العدد","الوحدة","الأيام الفعلية","خارج الرصيد","السبب","تاريخ الإضافة"]
        ws.append(hdrs)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="1C2D3E")
            cell.font = Font(bold=True, color="00C896")
        for i,lv in enumerate(emp.get("history",[])):
            ws.append([i+1, lv.get("type",""), lv.get("from_date",""), lv.get("to_date",""),
                       lv.get("amount",""), lv.get("unit",""), lv.get("days_actual",0),
                       "نعم" if lv.get("outside_balance") else "لا",
                       lv.get("reason",""), lv.get("added_date","")])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 18
        wb.save(path)
        messagebox.showinfo("تم", f"تم التصدير:\n{path}", parent=self)

    def _export_pdf(self):
        if not HAS_PDF:
            messagebox.showerror("خطأ","reportlab غير مثبت.", parent=self); return
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
               filetypes=[("PDF","*.pdf")], parent=self)
        if not path: return
        emp = db.get(self.emp_id)
        doc = SimpleDocTemplate(path, pagesize=A4,
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph(f"سجل إجازات: {emp.get('name','')}", styles["Title"]))
        story.append(Spacer(1, 0.5*cm))
        data = [["#","النوع","من","إلى","الأيام","خارج الرصيد","السبب"]]
        for i,lv in enumerate(emp.get("history",[])):
            data.append([str(i+1), lv.get("type",""), lv.get("from_date",""),
                         lv.get("to_date",""), str(lv.get("days_actual",0)),
                         "نعم" if lv.get("outside_balance") else "لا", lv.get("reason","")])
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#1C2D3E")),
            ("TEXTCOLOR",  (0,0),(-1,0), colors.HexColor("#00C896")),
            ("FONTNAME",   (0,0),(-1,-1),"Helvetica"),
            ("GRID",       (0,0),(-1,-1), 0.5, colors.grey),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f5f5f5")]),
            ("ALIGN",      (0,0),(-1,-1),"CENTER"),
        ]))
        story.append(t)
        doc.build(story)
        messagebox.showinfo("تم", f"تم التصدير:\n{path}", parent=self)


# ═══════════════════════════════════════════════
#  النافذة الرئيسية
# ═══════════════════════════════════════════════
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("نظام إدارة الإجازات التراكمية")
        self.geometry("1200x740")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        apply_styles(self)
        self._ui()
        self._refresh()

    # ── بناء الواجهة ──
    def _ui(self):
        # رأس
        hdr = tk.Frame(self, bg=C["surface"], height=54)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="نظام إدارة الإجازات التراكمية",
                 bg=C["surface"], fg=C["accent"], font=TITLE_F).pack(side="right", padx=20, pady=12)
        tk.Label(hdr, text=f"يوم إجازة لكل {DAYS_PER_LEAVE} أيام دوام  |  سقف سنوي {MAX_ANNUAL} يوم",
                 bg=C["surface"], fg=C["muted"], font=BODY_F).pack(side="left", padx=20)

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=10)

        # شريط جانبي
        side = tk.Frame(body, bg=C["card"], width=265)
        side.pack(side="right", fill="y", padx=(8,0)); side.pack_propagate(False)
        self._sidebar(side)

        # مركز
        center = tk.Frame(body, bg=C["bg"])
        center.pack(side="right", fill="both", expand=True)
        self._table(center)
        self._detail_panel(center)

    def _sidebar(self, p):
        pk = dict(padx=12, pady=5)

        ttk.Button(p, text="➕  إضافة موظف جديد", style="Accent.TButton",
                   command=self._add_emp).pack(fill="x", padx=12, pady=(16,6))

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

        cols = ("id","name","title","gender","start","raw","outside","net","earned","taken","balance")
        hdrs = ("الرقم الوظيفي","الاسم","العنوان الوظيفي","الجنس","تاريخ المباشرة",
                "أيام الخدمة","خارج الرصيد","أيام الدوام المحسوبة","المستحقة","المأخوذة","الرصيد")
        wrap = tk.Frame(p, bg=C["bg"]); wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        widths = [90,140,120,60,100,80,90,120,75,75,75]
        for col,hd,w in zip(cols,hdrs,widths):
            self.tree.heading(col,text=hd); self.tree.column(col,width=w,anchor="center")
        vsb = ttk.Scrollbar(wrap,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="left",fill="y"); self.tree.pack(side="right",fill="both",expand=True)
        self.tree.tag_configure("pos",foreground=C["accent"])
        self.tree.tag_configure("neg",foreground=C["neg"])
        self.tree.bind("<<TreeviewSelect>>", self._on_sel)

    def _detail_panel(self, p):
        f = tk.Frame(p, bg=C["card"], height=110)
        f.pack(fill="x", pady=(8,0)); f.pack_propagate(False)
        g = tk.Frame(f, bg=C["card"]); g.pack(expand=True, pady=8)
        self.dlbls = {}
        items = [("name","الاسم"),("job_title","العنوان الوظيفي"),("gender","الجنس"),
                 ("start_date","تاريخ المباشرة"),("raw_days","أيام الخدمة"),
                 ("net_days","أيام الدوام المحسوبة"),("earned","المستحقة"),
                 ("taken","المأخوذة"),("balance","الرصيد")]
        for i,(k,lb) in enumerate(items):
            tk.Label(g, text=lb, bg=C["card"], fg=C["muted"], font=SMALL_F).grid(row=0,column=i,padx=10,sticky="s")
            font = BIG_F if k=="balance" else HEAD_F
            v = tk.Label(g, text="—", bg=C["card"], fg=C["text"], font=font)
            v.grid(row=1, column=i, padx=10, sticky="n"); self.dlbls[k]=v

    # ── منطق ──
    def _refresh(self):
        q = self.sv.get().lower() if hasattr(self,"sv") else ""
        for r in self.tree.get_children(): self.tree.delete(r)
        for eid, emp in db.all().items():
            name = emp.get("name","")
            if q and q not in name.lower() and q not in eid.lower(): continue
            b = compute_balance(emp)
            tag = "pos" if b["balance"]>=0 else "neg"
            self.tree.insert("","end",iid=eid,tags=(tag,),values=(
                eid, name, emp.get("job_title",""), emp.get("gender",""),
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
            db.delete(eid); self._refresh()
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
        if not amount_s: messagebox.showwarning("تنبيه","أدخل عدد الأيام."); return
        try: amount = int(amount_s)
        except: messagebox.showwarning("تنبيه","أدخل عدداً صحيحاً."); return
        days = unit_to_days(amount, unit)

        emp = db.get(eid)
        b   = compute_balance(emp)
        if days > b["balance"] and not outside:
            if not messagebox.askyesno("تجاوز الرصيد",
                f"الرصيد المتاح: {b['balance']} يوم.\nهل تريد المتابعة؟"): return

        emp["history"].append({
            "type": ltype, "from_date":"", "to_date":"",
            "amount": amount, "unit": unit, "days_actual": days,
            "outside_balance": outside, "reason": reason,
            "added_date": str(date.today()),
        })
        db.save()
        self.e_lamount.delete(0,tk.END); self.e_lreason.delete(0,tk.END)
        self._refresh(); self._on_sel(None)

    def _export_all(self):
        if not HAS_XLSX: messagebox.showerror("خطأ","openpyxl غير مثبت."); return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
               filetypes=[("Excel","*.xlsx")])
        if not path: return
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "الموظفون"
        ws.sheet_view.rightToLeft = True
        hdrs = ["الرقم الوظيفي","الاسم","العنوان الوظيفي","الجنس","تاريخ المباشرة",
                "أيام الخدمة","خارج الرصيد","أيام الدوام المحسوبة","المستحقة","المأخوذة","الرصيد","ملاحظات"]
        ws.append(hdrs)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="00C896")
            cell.fill = PatternFill("solid", fgColor="1C2D3E")
        for eid, emp in db.all().items():
            b = compute_balance(emp)
            ws.append([eid, emp.get("name",""), emp.get("job_title",""),
                       emp.get("gender",""), emp.get("start_date",""),
                       b["raw_days"], b["outside"], b["net_days"],
                       b["earned"], b["taken"], b["balance"], emp.get("notes","")])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 20
        wb.save(path)
        messagebox.showinfo("تم",f"تم التصدير:\n{path}")

    def _print_emp(self):
        eid = self._sel_id()
        if not eid: messagebox.showwarning("تنبيه","حدد موظفاً."); return
        emp = db.get(eid)
        b   = compute_balance(emp)

        # إنشاء HTML للطباعة
        html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="UTF-8">
<style>
  body{{font-family:'Segoe UI',Arial,sans-serif;direction:rtl;padding:40px;color:#1a1a2e;}}
  h1{{font-size:22px;border-bottom:3px solid #00C896;padding-bottom:10px;color:#0f3460;}}
  .grid{{display:flex;flex-wrap:wrap;gap:20px;margin-top:20px;}}
  .item{{min-width:180px;}}
  .item label{{font-size:11px;color:#666;display:block;}}
  .item span{{font-size:14px;font-weight:bold;color:#1a1a2e;}}
  .balance{{font-size:24px;color:{'#00C896' if b['balance']>=0 else '#FF4757'};}}
  @media print{{body{{padding:20px;}}}}
</style>
</head>
<body>
<h1>{emp.get('name','')}</h1>
<div class="grid">
  <div class="item"><label>الرقم الوظيفي</label><span>{eid}</span></div>
  <div class="item"><label>العنوان الوظيفي</label><span>{emp.get('job_title','-')}</span></div>
  <div class="item"><label>الجنس</label><span>{emp.get('gender','-')}</span></div>
  <div class="item"><label>تاريخ المباشرة</label><span>{emp.get('start_date','-')}</span></div>
  <div class="item"><label>ملاحظات</label><span>{emp.get('notes','-') or '-'}</span></div>
  <div class="item"><label>أيام الخدمة الكلية</label><span>{b['raw_days']} يوم</span></div>
  <div class="item"><label>أيام خارج الرصيد</label><span>{b['outside']} يوم</span></div>
  <div class="item"><label>أيام الدوام المحسوبة</label><span>{b['net_days']} يوم</span></div>
  <div class="item"><label>الإجازات المستحقة</label><span>{b['earned']} يوم</span></div>
  <div class="item"><label>الإجازات المأخوذة</label><span>{b['taken']} يوم</span></div>
  <div class="item"><label>الرصيد المتبقي</label><span class="balance">{b['balance']} يوم</span></div>
  <div class="item"><label>تاريخ الطباعة</label><span>{date.today()}</span></div>
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
