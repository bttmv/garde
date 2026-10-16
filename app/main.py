import html
import json
import os
import secrets
import tempfile
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import db
from routeros_api import RouterOS, RouterOSError

APPDATA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "WifiManager")
os.makedirs(APPDATA, exist_ok=True)
CFG_PATH = os.path.join(APPDATA, "config.json")
DEFAULT_CFG = {"host": "192.168.88.1", "port": "8728", "user": "admin", "password": "",
               "shop": "شبكة الواي فاي", "code_len": "8"}


def load_cfg():
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return {**DEFAULT_CFG, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULT_CFG)


def uptime_str(hours):
    m = max(1, round(float(hours) * 60))
    return f"{m // 60}h{m % 60}m"


def fmt_bytes(n):
    try:
        n = float(n)
    except ValueError:
        return "0"
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def make_tree(parent, cols):
    """cols: [(id, عنوان, عرض)]"""
    frame = ttk.Frame(parent)
    tv = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", selectmode="extended")
    for cid, title, w in cols:
        tv.heading(cid, text=title)
        tv.column(cid, width=w, anchor="center")
    sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tv


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("مدير شبكة الواي فاي - MikroTik")
        self.geometry("960x600")
        self.cfg = load_cfg()
        self.ros = None
        db.init(os.path.join(APPDATA, "data.db"))

        self.status = tk.StringVar(value="غير متصل")
        ttk.Label(self, textvariable=self.status, anchor="center").pack(fill="x", pady=2)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=4)
        self.t_conn, self.t_plans, self.t_gen = ttk.Frame(nb), ttk.Frame(nb), ttk.Frame(nb)
        self.t_cards, self.t_active, self.t_rep = ttk.Frame(nb), ttk.Frame(nb), ttk.Frame(nb)
        for t, name in [(self.t_conn, "الاتصال"), (self.t_plans, "الباقات"), (self.t_gen, "توليد كروت"),
                        (self.t_cards, "الكروت"), (self.t_active, "المتصلون الآن"), (self.t_rep, "التقارير")]:
            nb.add(t, text=name)
        self.build_conn()
        self.build_plans()
        self.build_gen()
        self.build_cards()
        self.build_active()
        self.build_report()
        nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh_all())
        self.refresh_all()

    # ---------------- الراوتر ----------------
    def connect(self):
        self.ros = RouterOS(self.cfg["host"], self.cfg["port"])
        self.ros.connect(self.cfg["user"], self.cfg["password"])
        self.status.set(f"متصل بـ {self.cfg['host']}")

    def rcall(self, cmd, attrs=None, queries=None):
        for attempt in (1, 2):
            try:
                if self.ros is None or self.ros.sock is None:
                    self.connect()
                return self.ros.call(cmd, attrs, queries)
            except (OSError, ConnectionError):
                self.ros = None
                self.status.set("غير متصل")
                if attempt == 2:
                    raise

    def guard(self, fn):
        try:
            return fn()
        except RouterOSError as e:
            messagebox.showerror("خطأ من الراوتر", str(e))
        except OSError as e:
            messagebox.showerror("تعذر الاتصال", f"تحقق من العنوان والمنفذ وتفعيل API:\n{e}")
        except ValueError as e:
            messagebox.showerror("قيمة غير صحيحة", str(e))

    def ensure_profile(self, hours):
        name = f"plan-{round(float(hours) * 60)}m"
        if not self.rcall("/ip/hotspot/user/profile/print", queries=[f"?name={name}"]):
            self.rcall("/ip/hotspot/user/profile/add",
                       {"name": name, "shared-users": "1", "keepalive-timeout": "2m"})
        return name

    # ---------------- تبويب الاتصال ----------------
    def build_conn(self):
        f = self.t_conn
        self.vars = {}
        rows = [("host", "عنوان الراوتر"), ("port", "منفذ API"), ("user", "اسم المستخدم"),
                ("password", "كلمة المرور"), ("shop", "اسم المحل (يظهر على الكرت)"),
                ("code_len", "طول رقم الكرت")]
        for i, (k, label) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=i, column=1, sticky="e", padx=8, pady=6)
            v = tk.StringVar(value=self.cfg[k])
            self.vars[k] = v
            ttk.Entry(f, textvariable=v, width=34, show="*" if k == "password" else "").grid(row=i, column=0, padx=8)
        ttk.Button(f, text="حفظ واتصال", command=self.save_conn).grid(row=len(rows), column=0, pady=14)

    def save_conn(self):
        self.cfg = {k: v.get().strip() for k, v in self.vars.items()}
        with open(CFG_PATH, "w", encoding="utf-8") as fh:
            json.dump(self.cfg, fh, ensure_ascii=False)
        self.ros = None

        def go():
            self.connect()
            ident = self.rcall("/system/identity/print")
            messagebox.showinfo("تم", f"تم الاتصال بنجاح بالراوتر: {ident[0].get('name', '')}")
        self.guard(go)

    # ---------------- تبويب الباقات ----------------
    def build_plans(self):
        fr, self.plans_tv = make_tree(self.t_plans, [("name", "الباقة", 260), ("hours", "الساعات", 100), ("price", "السعر", 100)])
        fr.pack(fill="both", expand=True, padx=6, pady=6)
        bar = ttk.Frame(self.t_plans)
        bar.pack(fill="x", pady=6)
        self.p_name, self.p_hours, self.p_price = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for var, label, w in [(self.p_name, "الاسم", 18), (self.p_hours, "الساعات", 7), (self.p_price, "السعر", 9)]:
            ttk.Label(bar, text=label).pack(side="right", padx=3)
            ttk.Entry(bar, textvariable=var, width=w).pack(side="right")
        ttk.Button(bar, text="إضافة باقة", command=self.add_plan).pack(side="right", padx=8)
        ttk.Button(bar, text="حذف المحدد", command=self.del_plan).pack(side="left", padx=8)

    def add_plan(self):
        def go():
            name = self.p_name.get().strip()
            if not name:
                raise ValueError("اكتب اسم الباقة")
            db.add_plan(name, float(self.p_hours.get()), float(self.p_price.get()))
            self.p_name.set(""); self.p_hours.set(""); self.p_price.set("")
            self.refresh_plans()
        self.guard(go)

    def del_plan(self):
        for iid in self.plans_tv.selection():
            db.delete_plan(int(iid))
        self.refresh_plans()

    def refresh_plans(self):
        self.plans_tv.delete(*self.plans_tv.get_children())
        for p in db.plans():
            self.plans_tv.insert("", "end", iid=str(p["id"]), values=(p["name"], p["hours"], p["price"]))
        self.plan_combo["values"] = [f"{p['id']} - {p['name']}" for p in db.plans()]

    # ---------------- تبويب التوليد ----------------
    def build_gen(self):
        f = self.t_gen
        ttk.Label(f, text="الباقة").grid(row=0, column=1, padx=8, pady=10, sticky="e")
        self.plan_combo = ttk.Combobox(f, state="readonly", width=32)
        self.plan_combo.grid(row=0, column=0)
        ttk.Label(f, text="عدد الكروت").grid(row=1, column=1, padx=8, pady=10, sticky="e")
        self.count = tk.StringVar(value="10")
        ttk.Entry(f, textvariable=self.count, width=10).grid(row=1, column=0, sticky="w")
        self.print_after = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="فتح صفحة الطباعة بعد التوليد", variable=self.print_after).grid(row=2, column=0, pady=6)
        ttk.Button(f, text="توليد الكروت", command=self.generate).grid(row=3, column=0, pady=14)

    def new_code(self):
        n = max(4, int(self.cfg.get("code_len", 8)))
        while True:
            code = "".join(secrets.choice("0123456789") for _ in range(n))
            if not db.code_exists(code):
                return code

    def generate(self):
        def go():
            sel = self.plan_combo.get()
            if not sel:
                raise ValueError("اختر باقة")
            plan = next(p for p in db.plans() if p["id"] == int(sel.split(" - ")[0]))
            n = int(self.count.get())
            if not 1 <= n <= 500:
                raise ValueError("العدد بين 1 و 500")
            profile = self.ensure_profile(plan["hours"])
            made = []
            for _ in range(n):
                code = self.new_code()
                self.rcall("/ip/hotspot/user/add", {
                    "name": code, "password": code, "profile": profile,
                    "limit-uptime": uptime_str(plan["hours"]), "comment": f"card:{plan['name']}"})
                db.add_card(code, plan["name"], plan["hours"], plan["price"])
                made.append(code)
            self.refresh_cards()
            if self.print_after.get():
                self.print_cards([c for c in db.cards() if c["code"] in made])
            else:
                messagebox.showinfo("تم", f"تم توليد {n} كرت")
        self.guard(go)

    # ---------------- تبويب الكروت ----------------
    def build_cards(self):
        fr, self.cards_tv = make_tree(self.t_cards, [
            ("code", "رقم الكرت", 130), ("plan", "الباقة", 160), ("price", "السعر", 80),
            ("state", "الحالة", 80), ("created", "تاريخ الإنشاء", 150), ("sold_at", "تاريخ البيع", 150)])
        fr.pack(fill="both", expand=True, padx=6, pady=6)
        bar = ttk.Frame(self.t_cards)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="تحديث", command=self.refresh_cards).pack(side="right", padx=4)
        ttk.Button(bar, text="تعيين كمباع", command=self.sell_selected).pack(side="right", padx=4)
        ttk.Button(bar, text="طباعة المحدد", command=lambda: self.print_selected(False)).pack(side="right", padx=4)
        ttk.Button(bar, text="طباعة غير المباعة", command=lambda: self.print_selected(True)).pack(side="right", padx=4)
        ttk.Button(bar, text="حذف المحدد (من الراوتر أيضًا)", command=self.delete_selected).pack(side="left", padx=4)

    def refresh_cards(self):
        self.cards_tv.delete(*self.cards_tv.get_children())
        for c in db.cards():
            self.cards_tv.insert("", "end", iid=c["code"], values=(
                c["code"], c["plan_name"], c["price"], "مباع" if c["sold"] else "متاح", c["created_at"], c["sold_at"] or ""))

    def sell_selected(self):
        for code in self.cards_tv.selection():
            db.mark_sold(code)
        self.refresh_cards(); self.refresh_report()

    def print_selected(self, unsold):
        if unsold:
            rows = db.cards(only_unsold=True)
        else:
            sel = set(self.cards_tv.selection())
            rows = [c for c in db.cards() if c["code"] in sel]
        if not rows:
            messagebox.showinfo("تنبيه", "لا توجد كروت للطباعة")
            return
        self.print_cards(rows)

    def delete_selected(self):
        sel = self.cards_tv.selection()
        if not sel or not messagebox.askyesno("تأكيد", f"حذف {len(sel)} كرت؟"):
            return

        def go():
            for code in sel:
                users = self.rcall("/ip/hotspot/user/print", queries=[f"?name={code}"])
                for u in users:
                    self.rcall("/ip/hotspot/user/remove", {".id": u[".id"]})
                db.delete_card(code)
            self.refresh_cards()
        self.guard(go)

    def print_cards(self, rows):
        shop = html.escape(self.cfg.get("shop", ""))
        cards = "".join(
            f"""<div class="c"><div class="s">{shop}</div><div class="p">{html.escape(r['plan_name'])}</div>
            <div class="code">{r['code']}</div><div class="s">السعر: {r['price']:g}</div></div>"""
            for r in rows)
        page = f"""<!doctype html><html dir="rtl" lang="ar"><meta charset="utf-8"><title>كروت</title>
        <style>body{{font-family:Tahoma,Arial;margin:10px}}
        .g{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}
        .c{{border:1.5px dashed #333;padding:8px;text-align:center;break-inside:avoid}}
        .code{{font-size:22px;font-weight:bold;letter-spacing:2px;margin:6px 0;direction:ltr}}
        .p{{font-size:15px}}.s{{font-size:12px;color:#444}}</style>
        <body onload="window.print()"><div class="g">{cards}</div></body></html>"""
        path = os.path.join(tempfile.gettempdir(), "wifi_cards.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        webbrowser.open("file:///" + path.replace("\\", "/"))

    # ---------------- المتصلون الآن ----------------
    def build_active(self):
        fr, self.act_tv = make_tree(self.t_active, [
            ("user", "الكرت", 110), ("addr", "العنوان", 120), ("mac", "MAC", 140),
            ("up", "مدة الاتصال", 100), ("left", "المتبقي", 100), ("rx", "تحميل", 90), ("tx", "رفع", 90)])
        fr.pack(fill="both", expand=True, padx=6, pady=6)
        bar = ttk.Frame(self.t_active)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="تحديث", command=self.refresh_active).pack(side="right", padx=4)
        ttk.Button(bar, text="فصل المحدد", command=self.kick).pack(side="right", padx=4)

    def refresh_active(self):
        def go():
            self.act_tv.delete(*self.act_tv.get_children())
            for a in self.rcall("/ip/hotspot/active/print"):
                self.act_tv.insert("", "end", iid=a[".id"], values=(
                    a.get("user", ""), a.get("address", ""), a.get("mac-address", ""), a.get("uptime", ""),
                    a.get("session-time-left", "-"), fmt_bytes(a.get("bytes-out", 0)), fmt_bytes(a.get("bytes-in", 0))))
        self.guard(go)

    def kick(self):
        def go():
            for iid in self.act_tv.selection():
                self.rcall("/ip/hotspot/active/remove", {".id": iid})
            self.refresh_active()
        self.guard(go)

    # ---------------- التقارير ----------------
    def build_report(self):
        self.rep_lbl = tk.StringVar()
        ttk.Label(self.t_rep, textvariable=self.rep_lbl, justify="right", font=("Tahoma", 12)).pack(pady=10)
        fr, self.rep_tv = make_tree(self.t_rep, [("day", "اليوم", 140), ("n", "عدد الكروت المباعة", 150), ("total", "الإيراد", 120)])
        fr.pack(fill="both", expand=True, padx=6, pady=6)

    def refresh_report(self):
        t = db.totals()
        self.rep_lbl.set(
            f"اليوم: {t['today'][0]} كرت  |  {t['today'][1]:g}\n"
            f"هذا الشهر: {t['month'][0]} كرت  |  {t['month'][1]:g}\n"
            f"الإجمالي: {t['all'][0]} كرت  |  {t['all'][1]:g}")
        self.rep_tv.delete(*self.rep_tv.get_children())
        for r in db.report_by_day():
            self.rep_tv.insert("", "end", values=(r["day"], r["n"], f"{r['total']:g}"))

    def refresh_all(self):
        self.refresh_plans(); self.refresh_cards(); self.refresh_report()


if __name__ == "__main__":
    App().mainloop()
