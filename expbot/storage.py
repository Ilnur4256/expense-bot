import csv
import io
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime

from expbot.parser import Entry

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    comment TEXT NOT NULL,
    is_income INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_user_date ON entries(user_id, created_at);
CREATE TABLE IF NOT EXISTS budgets (
    user_id INTEGER PRIMARY KEY,
    monthly REAL NOT NULL
);
"""


@dataclass(frozen=True)
class Saved:
    id: int
    entry: Entry
    created_at: datetime


class Storage:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def add(self, user_id: int, entry: Entry, when: datetime) -> Saved:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO entries (user_id, amount, category, comment, is_income, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    entry.amount,
                    entry.category,
                    entry.comment,
                    int(entry.is_income),
                    when.isoformat(),
                ),
            )
            self.conn.commit()
        return Saved(cur.lastrowid, entry, when)

    def undo_last(self, user_id: int) -> Saved | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM entries WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
            ).fetchone()
            if row is None:
                return None
            self.conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))
            self.conn.commit()
        return self._to_saved(row)

    def between(self, user_id: int, start: date, end: date) -> list[Saved]:
        """Записи за даты [start, end] включительно."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM entries WHERE user_id = ? "
                "AND substr(created_at, 1, 10) BETWEEN ? AND ? ORDER BY created_at",
                (user_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [self._to_saved(r) for r in rows]

    def set_budget(self, user_id: int, monthly: float) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO budgets (user_id, monthly) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET monthly = excluded.monthly",
                (user_id, monthly),
            )
            self.conn.commit()

    def get_budget(self, user_id: int) -> float | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT monthly FROM budgets WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row["monthly"] if row else None

    def export_csv(self, user_id: int) -> bytes:
        with self.lock:
            rows = self.conn.execute(
                "SELECT created_at, amount, category, comment, is_income FROM entries "
                "WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Дата", "Сумма", "Категория", "Комментарий", "Тип"])
        for r in rows:
            w.writerow(
                [
                    r["created_at"][:16].replace("T", " "),
                    r["amount"],
                    r["category"],
                    r["comment"],
                    "доход" if r["is_income"] else "расход",
                ]
            )
        return buf.getvalue().encode("utf-8-sig")

    @staticmethod
    def _to_saved(row) -> Saved:
        entry = Entry(row["amount"], row["category"], row["comment"], bool(row["is_income"]))
        return Saved(row["id"], entry, datetime.fromisoformat(row["created_at"]))
