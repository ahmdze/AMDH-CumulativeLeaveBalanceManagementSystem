#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date
import json, os, csv

DAYS_PER_LEAVE = 10
MAX_ANNUAL_LEAVE = 36

class LeaveCalculator:
    def __init__(self):
        self.employees = {}
        self.load_data()

    @staticmethod
    def earned_leave(working_days):
        return round(working_days / DAYS_PER_LEAVE, 2)

    def get_balance(self, eid):
        emp = self.employees.get(eid, {})
        if not emp: return {}
        earned = self.earned_leave(emp["working_days"])
        taken  = emp["ordinary_leave"] + emp["long_leave"]
        return {
            "name": emp["name"], "working_days": emp["working_days"],
            "earned": earned, "ordinary_leave": emp["ordinary_leave"],
            "long_leave": emp["long_leave"], "total_taken": round(taken, 2),
            "balance": round(earned - taken, 2), "notes": emp.get("notes", ""),
        }

    def add_employee(self, eid, name, working_days, ordinary_leave=0.0, long_leave=0.0, notes=""):
        self.employees[eid] = {
            "name": name, "working_days": float(working_days),
            "ordinary_leave": float(ordinary_leave), "long_leave": float(long_leave),
            "notes": notes, "created": str(date.today()), "history": []
        }
        self.save_data()

    def add_leave(self, eid, leave_type, days, reason=""):
        emp = self.employees.get(eid)
        if not emp: return
        if leave_type == "ordinary": emp["ordinary_leave"] += days
        else: emp["long_leave"] += days
        emp["history"].append({"date": str(date.today()), "type": leave_type, "days": days, "reason": reason})
        self.save_data()

    def delete_employee(self, eid):
        if eid in self.employees:
            del self.employees[eid]; self.save_data()

    def save_data(self):
        with open("employees_leave.json", "w", encoding="utf-8") as f:
            json.dump(self.employees, f, ensure_ascii=False, indent=2)

    def load_data(self):
        if os.path.exists("employees_leave.json"):
            try:
                with open("employees_leave.json", "r", encoding="utf-8") as f:
                    self.employees = json.load(f)
            except: self.employees = {}

    def export_csv(self, filepath):
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["رقم الموظف","الاسم","أيام الدوام","المستحقة","اعتيادية","طويلة","المأخوذة","الرصيد","ملاحظات"])
            for eid in self.employees:
                b = self.get_balance(eid)
                w.writerow([eid,b["name"],b["working_days"],b["earned"],b["ordinary_leave"],b["long_leave"],b["total_taken"],b["balance"],b["notes"]])

C = {"bg":"#0F1923","surface":"#182534","card":"#1C2D3E","accent":"#00C896","blue":"#0096FF",
     "warn":"#FF6135","text":"#E0EAF5","muted":"#6A8099","border":"#243447","neg":"#FF4757"}
TITLE_F=("Segoe UI",13,"bold"); HEAD_F=("Segoe UI",10,"bold"); BODY_F=("Segoe UI",10); BIG_F=("Segoe UI",20,"bold")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.calc = LeaveCalculator()
        self.title("نظام إدارة الإجازات التراكمية")
        self.geometry("1150x720")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self._styles(); self._ui(); self._refresh()

    def _styles(self):
        s = ttk.Style(self); s.theme_use("clam")
        s.configure("TFrame", background=C["bg"])
        s.configure("TLabel", background=C["bg"], foreground=C["text"], font=BODY_F)
        s.configure("TEntry", fieldbackground=C["surface"], foreground=C["text"],
                    insertcolor=C["accent"], font=BODY_F, bordercolor=C["border"],
                    lightcolor=C["border"], darkcolor=C["border"])
        s.configure("TCombobox", fieldbackground=C["surface"], foreground=C["text"],
                    background=C["surface"], font=BODY_F)
        s.configure("Treeview", background=C["surface"], foreground=C["text"],
                    fieldbackground=C["surface"], rowheight=30, font=BODY_F, borderwidth=0)
        s.configure("Treeview.Heading", background=C["card"], foreground=C["accent"], font=HEAD_F, relief="flat")
        s.map("Treeview", background=[("selected",C["blue"])], foreground=[("selected","#fff")])
        for nm,bg,fg in [("Accent",C["accent"],C["bg"]),("Warn",C["warn"],"#fff"),("Ghost",C["surface"],C["text"])]:
            s.configure(f"{nm}.TButton", background=bg, foreground=fg, font=HEAD_F, relief="flat", borderwidth=0, padding=(12,6))
            s.map(f"{nm}.TButton", relief=[("active","flat")])

    def _ui(self):
        hdr=tk.Frame(self,bg=C["surface"],height=56); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr,text="نظام إدارة الإجازات التراكمية",bg=C["surface"],fg=C["accent"],font=TITLE_F).pack(side="right",padx=20,pady=10)
        tk.Label(hdr,text=f"يوم إجازة لكل {DAYS_PER_LEAVE} أيام دوام  |  الحد السنوي: {MAX_ANNUAL_LEAVE} يوم",
                 bg=C["surface"],fg=C["muted"],font=BODY_F).pack(side="left",padx=20)
        body=tk.Frame(self,bg=C["bg"]); body.pack(fill="both",expand=True,padx=14,pady=10)
        side=tk.Frame(body,bg=C["card"],width=275); side.pack(side="right",fill="y",padx=(8,0)); side.pack_propagate(False)
        self._sidebar(side)
        center=tk.Frame(body,bg=C["bg"]); center.pack(side="right",fill="both",expand=True)
        self._table(center); self._detail(center)

    def _sidebar(self,p):
        pk=dict(padx=14)
        tk.Label(p,text="إضافة موظف",bg=C["card"],fg=C["accent"],font=HEAD_F).pack(anchor="e",padx=14,pady=(14,2))
        tk.Frame(p,bg=C["border"],height=1).pack(fill="x",padx=12,pady=4)
        fields=[("f_id","رقم الموظف *"),("f_name","الاسم الكامل *"),("f_wd","أيام الدوام الفعلية"),
                ("f_ol","إجازة اعتيادية مسبقة"),("f_ll","إجازة طويلة مسبقة"),("f_notes","ملاحظات")]
        self._entries={}
        for key,lbl in fields:
            fr=tk.Frame(p,bg=C["card"]); fr.pack(fill="x",padx=14,pady=5)
            tk.Label(fr,text=lbl,bg=C["card"],fg=C["text"],font=BODY_F).pack(anchor="e")
            e=ttk.Entry(fr); e.pack(fill="x"); self._entries[key]=e
        ttk.Button(p,text="حفظ الموظف",style="Accent.TButton",command=self._do_add).pack(fill="x",padx=14,pady=(6,2))
        tk.Frame(p,bg=C["border"],height=1).pack(fill="x",padx=12,pady=4)
        tk.Label(p,text="تسجيل إجازة للموظف المحدد",bg=C["card"],fg=C["blue"],font=HEAD_F).pack(anchor="e",padx=14,pady=5)
        fr=tk.Frame(p,bg=C["card"]); fr.pack(fill="x",padx=14,pady=5)
        tk.Label(fr,text="نوع الإجازة",bg=C["card"],fg=C["text"]).pack(anchor="e")
        self.ltype=tk.StringVar(value="ordinary (اعتيادية)")
        ttk.Combobox(fr,textvariable=self.ltype,values=["ordinary (اعتيادية)","long (طويلة)"],state="readonly").pack(fill="x")
        fr2=tk.Frame(p,bg=C["card"]); fr2.pack(fill="x",**pk)
        tk.Label(fr2,text="عدد الأيام",bg=C["card"],fg=C["text"]).pack(anchor="e")
        self.ldays=ttk.Entry(fr2); self.ldays.pack(fill="x")
        fr3=tk.Frame(p,bg=C["card"]); fr3.pack(fill="x",**pk)
        tk.Label(fr3,text="السبب",bg=C["card"],fg=C["text"]).pack(anchor="e")
        self.lreason=ttk.Entry(fr3); self.lreason.pack(fill="x")
        ttk.Button(p,text="تسجيل الإجازة",style="Accent.TButton",command=self._do_leave).pack(fill="x",**pk,pady=(6,2))
        tk.Frame(p,bg=C["border"],height=1).pack(fill="x",padx=12,pady=4)
        ttk.Button(p,text="حذف الموظف المحدد",style="Warn.TButton",command=self._do_delete).pack(fill="x",**pk)
        ttk.Button(p,text="تصدير إلى CSV",style="Ghost.TButton",command=self._do_export).pack(fill="x",**pk)

    def _table(self,p):
        top=tk.Frame(p,bg=C["bg"]); top.pack(fill="x",pady=(0,6))
        tk.Label(top,text="قائمة الموظفين",bg=C["bg"],fg=C["text"],font=HEAD_F).pack(side="right")
        self.search_var=tk.StringVar(); self.search_var.trace_add("write",lambda *_:self._refresh())
        ttk.Entry(top,textvariable=self.search_var,width=20).pack(side="left")
        tk.Label(top,text="بحث:",bg=C["bg"],fg=C["muted"]).pack(side="left",padx=(0,3))
        cols=("id","name","wd","earned","ol","ll","taken","balance")
        hdrs=("الرقم","الاسم","أيام الدوام","المستحقة","اعتيادية","طويلة","المأخوذة","الرصيد")
        wrap=tk.Frame(p,bg=C["bg"]); wrap.pack(fill="both",expand=True)
        self.tree=ttk.Treeview(wrap,columns=cols,show="headings",selectmode="browse")
        for col,hd,w in zip(cols,hdrs,[65,160,95,90,85,75,90,90]):
            self.tree.heading(col,text=hd); self.tree.column(col,width=w,anchor="center")
        vsb=ttk.Scrollbar(wrap,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set); vsb.pack(side="left",fill="y")
        self.tree.pack(side="right",fill="both",expand=True)
        self.tree.tag_configure("pos",foreground=C["accent"])
        self.tree.tag_configure("neg",foreground=C["neg"])
        self.tree.bind("<<TreeviewSelect>>",self._on_sel)

    def _detail(self,p):
        f=tk.Frame(p,bg=C["card"],height=130); f.pack(fill="x",pady=(8,0)); f.pack_propagate(False)
        g=tk.Frame(f,bg=C["card"]); g.pack(expand=True)
        self.dlbls={}
        items=[("name","الموظف"),("working_days","أيام الدوام"),("earned","المستحقة"),
               ("ordinary_leave","اعتيادية"),("long_leave","طويلة"),("total_taken","المأخوذة"),("balance","الرصيد")]
        for i,(k,lbl) in enumerate(items):
            tk.Label(g,text=lbl,bg=C["card"],fg=C["muted"],font=BODY_F).grid(row=0,column=i,padx=12,sticky="s")
            v=tk.Label(g,text="—",bg=C["card"],fg=C["text"],font=BIG_F if k=="balance" else HEAD_F)
            v.grid(row=1,column=i,padx=12,sticky="n"); self.dlbls[k]=v

    def _do_add(self):
        eid=self._entries["f_id"].get().strip(); name=self._entries["f_name"].get().strip()
        if not eid or not name: messagebox.showwarning("تنبيه","رقم الموظف والاسم إلزاميان."); return
        if eid in self.calc.employees: messagebox.showwarning("تنبيه","رقم الموظف مسجل مسبقاً."); return
        def num(k):
            v=self._entries[k].get().strip(); return float(v) if v else 0.0
        self.calc.add_employee(eid,name,num("f_wd"),num("f_ol"),num("f_ll"),self._entries["f_notes"].get().strip())
        for e in self._entries.values(): e.delete(0,tk.END)
        self._refresh(); messagebox.showinfo("تم",f"تمت إضافة الموظف: {name}")

    def _do_leave(self):
        sel=self.tree.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد موظفاً من الجدول."); return
        eid=self.tree.item(sel[0],"values")[0]
        ltype="ordinary" if "ordinary" in self.ltype.get() else "long"
        try: days=float(self.ldays.get())
        except: messagebox.showwarning("تنبيه","أدخل عدد أيام صحيح."); return
        bal=self.calc.get_balance(eid)
        if days>bal["balance"]:
            if not messagebox.askyesno("تجاوز الرصيد",f"الرصيد المتاح: {bal['balance']} يوم.\nهل تريد المتابعة؟"): return
        self.calc.add_leave(eid,ltype,days,self.lreason.get().strip())
        self.ldays.delete(0,tk.END); self.lreason.delete(0,tk.END)
        self._refresh(); self._show_detail(eid)

    def _do_delete(self):
        sel=self.tree.selection()
        if not sel: messagebox.showwarning("تنبيه","حدد موظفاً."); return
        eid=self.tree.item(sel[0],"values")[0]; name=self.tree.item(sel[0],"values")[1]
        if messagebox.askyesno("تأكيد",f"حذف '{name}'؟"):
            self.calc.delete_employee(eid); self._refresh()
            for v in self.dlbls.values(): v.config(text="—",fg=C["text"])

    def _do_export(self):
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],title="تصدير البيانات")
        if path: self.calc.export_csv(path); messagebox.showinfo("تم",f"تم التصدير:\n{path}")

    def _refresh(self):
        q=self.search_var.get().lower() if hasattr(self,"search_var") else ""
        for row in self.tree.get_children(): self.tree.delete(row)
        for eid in self.calc.employees:
            b=self.calc.get_balance(eid)
            if q and q not in b["name"].lower() and q not in eid.lower(): continue
            tag="pos" if b["balance"]>=0 else "neg"
            self.tree.insert("","end",iid=eid,tags=(tag,),
                values=(eid,b["name"],b["working_days"],b["earned"],
                        b["ordinary_leave"],b["long_leave"],b["total_taken"],b["balance"]))

    def _on_sel(self,_):
        sel=self.tree.selection()
        if sel: self._show_detail(sel[0])

    def _show_detail(self,eid):
        b=self.calc.get_balance(eid)
        if not b: return
        for k,v in self.dlbls.items():
            val=b.get(k,"—")
            color=(C["accent"] if b["balance"]>=0 else C["neg"]) if k=="balance" else C["text"]
            suffix=" يوم" if k!="name" else ""
            v.config(text=f"{val}{suffix}",fg=color)

if __name__=="__main__":
    App().mainloop()