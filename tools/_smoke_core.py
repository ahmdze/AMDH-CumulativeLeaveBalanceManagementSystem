"""فحص سريع (غير رسمي) للطبقات غير المرئية أثناء التطوير."""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"G:\Download\AMDH-Calculator")
sys.path.insert(0, str(ROOT))

from amdh_leave import config
from amdh_leave.db import Database
from amdh_leave.logging_setup import setup_logging
from amdh_leave.services import balance as B
from amdh_leave.services import reports
from amdh_leave.services.backup import BackupService

tmp = Path(tempfile.mkdtemp(prefix="amdh_check_"))
shutil.copy2(ROOT / "employees_leave.db", tmp / "employees_leave.db")
setup_logging(tmp / "logs")

paths = config.Paths(tmp).ensure()
db = Database(paths.db_path, paths.backups_dir)
print("schema_version:", db.schema_version, "| migrated:", db.migrated)
print("stats:", db.stats())

policy = db.policy()
print("rules:", sorted(policy.rules))
print("types for female:", policy.types_for_gender("أنثى"))

emp = db.get_employee("57454545")
print("employee:", emp.emp_id, emp.name, emp.start_date, "| leaves:", len(emp.leaves))
for lv in emp.leaves:
    print("   ", lv.id, lv.type, lv.start_date, "->", lv.end_date, lv.amount, lv.unit,
          "days=", lv.days_actual, "excl=", B.is_service_exclusion(policy, lv),
          "consumes=", B.consumes_balance(policy, lv), "status=", lv.status)

bal = B.compute_balance(emp, emp.leaves, policy)
print("BALANCE:", bal)
from datetime import date as _d
raw = (min(_d.today(), emp.end_date) if emp.end_date else _d.today()) - emp.start_date
raw = max(0, raw.days)
net = max(0, raw - 1825)
earned = net // policy.days_per_leave
assert (bal.raw_days, bal.outside, bal.net_days) == (raw, 1825, net), "انحرفت أيام الخدمة!"
assert (bal.earned, bal.taken, bal.balance) == (earned, 20, earned - 20), "انحرفت الأرقام المعتمدة!"

st = B.yearly_statement(emp, emp.leaves, policy)
print("statement lines:", len(st.lines), "| note:", st.policy_note)
print("  first:", st.lines[0])
print("  last :", st.lines[-1])
tot_out = sum(x.outside_days for x in st.lines)
tot_taken = sum(x.taken for x in st.lines)
tot_net = sum(x.net_days for x in st.lines)
tot_earned = sum(x.earned for x in st.lines)
print(f"  totals: outside={tot_out} taken={tot_taken} net={tot_net} earned={tot_earned}")
print(f"  headline: outside={bal.outside} taken={bal.taken} net={bal.net_days} earned={bal.earned}")
assert tot_out == bal.outside, f"كشف الحساب لا يطابق الرصيد في خارج الرصيد ({tot_out} != {bal.outside})"
assert tot_taken == bal.taken, f"كشف الحساب لا يطابق الرصيد في المأخوذة ({tot_taken} != {bal.taken})"
assert tot_net <= bal.net_days + 1, "صافي الدوام غير متسق"

assert policy.basis == config.BASIS_CONTINUOUS
annual = B.compute_annual(emp, emp.leaves, policy)
print("annual basis balance:", annual.balance, "earned:", annual.earned)

alerts = reports.collect_alerts([emp], policy)
print("alerts:", [a.message for a in alerts])
dash = reports.dashboard_data([emp], policy)
print("kpis:", dash["kpis"])

backup = BackupService(db, paths.backups_dir)
b1 = backup.create("manual")
print("backup:", b1.name if b1 else None, "| valid:", backup.list_backups()[0]["valid"])

# سجل الحذف الناعم والاستعادة
db.add_employee("T1", {"name": "اختبار", "start_date": "2024-01-01", "gender": "ذكر"})
print("after add:", db.stats()["employees"])
db.soft_delete_employee("T1", "tester")
print("after soft delete:", db.stats()["employees"], "| deleted:", db.stats()["employees_deleted"])
print("deleted list:", [e.emp_id for e in db.list_employees(include_deleted=True)])
db.restore_employee("T1", "tester")
print("after restore:", db.stats()["employees"])
db.purge_employee("T1")
print("after purge:", db.stats()["employees"])

audit = db.list_audit()
print("audit entries:", len(audit), "| last:", audit[0].action, audit[0].entity if audit else None)

print("meta:", {k: db.get_meta()[k] for k in list(db.get_meta())[:6]})
print("integrity:", db.integrity_check())

db.close()
print("TMP:", tmp)
print("OK")
