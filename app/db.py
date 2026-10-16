import sqlite3
from datetime import datetime

_path = None


def _conn():
    c = sqlite3.connect(_path)
    c.row_factory = sqlite3.Row
    return c


def init(path):
    global _path
    _path = path
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS plans(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hours REAL NOT NULL,
                price REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cards(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                plan_name TEXT NOT NULL,
                hours REAL NOT NULL,
                price REAL NOT NULL,
                sold INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                sold_at TEXT
            );
            """
        )
        if c.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO plans(name,hours,price) VALUES(?,?,?)",
                [("ساعة", 1, 500), ("3 ساعات", 3, 1200), ("يوم كامل (24 ساعة)", 24, 3000)],
            )


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ----- الباقات -----
def plans():
    with _conn() as c:
        return c.execute("SELECT * FROM plans ORDER BY hours").fetchall()


def add_plan(name, hours, price):
    with _conn() as c:
        c.execute("INSERT INTO plans(name,hours,price) VALUES(?,?,?)", (name, hours, price))


def delete_plan(pid):
    with _conn() as c:
        c.execute("DELETE FROM plans WHERE id=?", (pid,))


# ----- الكروت -----
def add_card(code, plan_name, hours, price):
    with _conn() as c:
        c.execute(
            "INSERT INTO cards(code,plan_name,hours,price,created_at) VALUES(?,?,?,?,?)",
            (code, plan_name, hours, price, now()),
        )


def code_exists(code):
    with _conn() as c:
        return c.execute("SELECT 1 FROM cards WHERE code=?", (code,)).fetchone() is not None


def cards(only_unsold=False):
    q = "SELECT * FROM cards" + (" WHERE sold=0" if only_unsold else "") + " ORDER BY id DESC"
    with _conn() as c:
        return c.execute(q).fetchall()


def mark_sold(code):
    with _conn() as c:
        c.execute("UPDATE cards SET sold=1, sold_at=? WHERE code=? AND sold=0", (now(), code))


def delete_card(code):
    with _conn() as c:
        c.execute("DELETE FROM cards WHERE code=?", (code,))


# ----- التقارير -----
def report_by_day():
    with _conn() as c:
        return c.execute(
            """SELECT substr(sold_at,1,10) AS day, COUNT(*) AS n, SUM(price) AS total
               FROM cards WHERE sold=1 GROUP BY day ORDER BY day DESC"""
        ).fetchall()


def totals():
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    with _conn() as c:
        def s(where, arg=()):
            r = c.execute(f"SELECT COUNT(*), COALESCE(SUM(price),0) FROM cards WHERE sold=1 {where}", arg).fetchone()
            return r[0], r[1]
        return {
            "today": s("AND substr(sold_at,1,10)=?", (today,)),
            "month": s("AND substr(sold_at,1,7)=?", (month,)),
            "all": s(""),
        }
