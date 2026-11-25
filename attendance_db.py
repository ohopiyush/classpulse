"""
attendance_db.py - Cached Cloud (Firebase Realtime DB) & Local SQLite Database Layer
for ClassPulse — Smart Student Attendance & Analytics.
"""
import csv
import json
import os
import re
import sqlite3
import time
from datetime import date, timedelta

try:
    import requests
except ImportError:
    requests = None


class AttendanceError(Exception):
    """Base exception for database and business-logic errors."""


class ValidationError(AttendanceError):
    """Raised when user input fails validation rules."""


class DuplicateStudentError(AttendanceError):
    """Raised when attempting to register an existing roll number."""


class StudentNotFoundError(AttendanceError):
    """Raised when querying or modifying a non-existent roll number."""


# Paste your Firebase Realtime Database URL here (no trailing slash).
# Leave as-is to run immediately in Local SQLite mode with zero setup.
FIREBASE_URL = "https://classpulse-attendance-24f4e-default-rtdb.asia-southeast1.firebasedatabase.app"


class AttendanceDB:
    ROLL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,24}$")

    def __init__(self, db_path: str, firebase_url: str = FIREBASE_URL):
        self.db_path = db_path
        self.base_url = (firebase_url or "").rstrip("/")
        self.cloud_enabled = bool(
            requests is not None
            and self.base_url.startswith("https://")
            and "YOUR-PROJECT-ID" not in self.base_url
        )
        self.cloud_online = False
        self.conn = None
        self._cache_data: dict | None = None
        self._cache_ts: float = 0.0

        if self.cloud_enabled:
            try:
                resp = requests.get(f"{self.base_url}/.json", timeout=6)
                resp.raise_for_status()
                self._cache_data = resp.json() or {}
                self._cache_ts = time.monotonic()
                self.cloud_online = True
            except Exception:
                self.cloud_enabled = False
                self.cloud_online = False

        if not self.cloud_enabled:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            self.conn = sqlite3.connect(db_path)
            self.conn.execute("PRAGMA foreign_keys = ON;")
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self._init_local_schema()

    def _init_local_schema(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    roll_no TEXT PRIMARY KEY COLLATE NOCASE,
                    name    TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_DATE
                );
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS attendance (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    roll_no  TEXT NOT NULL,
                    att_date TEXT NOT NULL,
                    status   TEXT NOT NULL CHECK (status IN ('Present', 'Absent')),
                    UNIQUE(roll_no, att_date),
                    FOREIGN KEY (roll_no) REFERENCES students(roll_no) ON DELETE CASCADE
                );
                """
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_att_date ON attendance(att_date);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_att_roll ON attendance(roll_no);")

    # --------------------------------------------------------- cloud helpers
    def _req(self, method: str, path: str, payload=None):
        url = f"{self.base_url}/{path.lstrip('/')}.json"
        try:
            resp = requests.request(method, url, json=payload, timeout=8)
            resp.raise_for_status()
            self.cloud_online = True
            if method != "GET":
                self._cache_data = None
            return resp.json()
        except Exception as e:
            self.cloud_online = False
            raise AttendanceError(f"Cloud sync error (check internet connection):\n{e}")

    def _cloud_snapshot(self, force_refresh: bool = False) -> dict:
        now = time.monotonic()
        if force_refresh or self._cache_data is None or (now - self._cache_ts) > 15.0:
            self._cache_data = self._req("GET", "") or {}
            self._cache_ts = now
        return self._cache_data

    # ------------------------------------------------------------- validation
    def _clean_roll(self, roll: str) -> str:
        roll = (roll or "").strip().upper()
        if not roll:
            raise ValidationError("Please enter a roll number.")
        if not self.ROLL_PATTERN.match(roll):
            raise ValidationError("Roll number must be 1–24 characters (letters, numbers, '-' or '_').")
        return roll

    def _clean_name(self, name: str) -> str:
        name = " ".join((name or "").strip().split())
        if not name:
            raise ValidationError("Please enter the student's name.")
        if len(name) > 80:
            raise ValidationError("Student name must be 80 characters or fewer.")
        return name

    # -------------------------------------------------------- student actions
    def add_student(self, roll: str, name: str) -> tuple[str, str]:
        roll = self._clean_roll(roll)
        name = self._clean_name(name)
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            if roll in students:
                raise DuplicateStudentError(f"Roll number '{roll}' is already registered.")
            self._req("PUT", f"students/{roll}", {"roll_no": roll, "name": name, "created_at": date.today().isoformat()})
            return roll, name

        try:
            with self.conn:
                self.conn.execute("INSERT INTO students (roll_no, name) VALUES (?, ?);", (roll, name))
        except sqlite3.IntegrityError:
            raise DuplicateStudentError(f"Roll number '{roll}' is already registered.")
        return roll, name

    def update_student_name(self, roll: str, new_name: str) -> tuple[str, str, str]:
        roll = self._clean_roll(roll)
        new_name = self._clean_name(new_name)
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            if roll not in students:
                raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
            old_name = students[roll].get("name", "")
            self._req("PATCH", f"students/{roll}", {"name": new_name})
            return roll, old_name, new_name

        cur = self.conn.execute("SELECT name FROM students WHERE roll_no = ?;", (roll,))
        row = cur.fetchone()
        if not row:
            raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
        with self.conn:
            self.conn.execute("UPDATE students SET name = ? WHERE roll_no = ?;", (new_name, roll))
        return roll, row[0], new_name

    def get_student(self, roll: str) -> tuple[str, str, int]:
        roll = self._clean_roll(roll)
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            if roll not in students:
                raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
            all_att = snap.get("attendance") or {}
            cnt = sum(1 for d in all_att.values() if isinstance(d, dict) and roll in d)
            return students[roll]["roll_no"], students[roll]["name"], cnt

        cur = self.conn.execute(
            """
            SELECT s.roll_no, s.name, COUNT(a.id)
            FROM students s
            LEFT JOIN attendance a ON a.roll_no = s.roll_no
            WHERE s.roll_no = ?
            GROUP BY s.roll_no, s.name;
            """,
            (roll,),
        )
        row = cur.fetchone()
        if not row:
            raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
        return row[0], row[1], row[2]

    def remove_student(self, roll: str) -> None:
        roll = self._clean_roll(roll)
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            if roll not in students:
                raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
            self._req("DELETE", f"students/{roll}")
            all_att = snap.get("attendance") or {}
            for iso_day, recs in all_att.items():
                if isinstance(recs, dict) and roll in recs:
                    self._req("DELETE", f"attendance/{iso_day}/{roll}")
            return

        with self.conn:
            cur = self.conn.execute("DELETE FROM students WHERE roll_no = ?;", (roll,))
            if cur.rowcount == 0:
                raise StudentNotFoundError(f"No student found with roll number '{roll}'.")

    # ----------------------------------------------------- attendance actions
    def get_status_for_day(self, roll: str, target_date: date) -> str | None:
        roll = self._clean_roll(roll)
        iso_day = target_date.isoformat()
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            day_recs = (snap.get("attendance") or {}).get(iso_day) or {}
            return day_recs.get(roll)
        row = self.conn.execute(
            "SELECT status FROM attendance WHERE roll_no = ? AND att_date = ?;", (roll, iso_day)
        ).fetchone()
        return row[0] if row else None

    def clear_attendance_for_day(self, roll: str, target_date: date) -> None:
        roll = self._clean_roll(roll)
        iso_day = target_date.isoformat()
        if self.cloud_enabled:
            self._req("DELETE", f"attendance/{iso_day}/{roll}")
            return
        with self.conn:
            self.conn.execute("DELETE FROM attendance WHERE roll_no = ? AND att_date = ?;", (roll, iso_day))

    def mark_attendance(self, roll: str, status: str, target_date: date) -> tuple[str, str, str | None]:
        """Marks attendance and returns (roll_no, name, previous_status)."""
        roll = self._clean_roll(roll)
        if status not in ("Present", "Absent"):
            raise ValidationError("Status must be either 'Present' or 'Absent'.")
        iso_day = target_date.isoformat()

        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            if roll not in students:
                raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
            day_recs = (snap.get("attendance") or {}).get(iso_day) or {}
            prev = day_recs.get(roll)
            self._req("PUT", f"attendance/{iso_day}/{roll}", status)
            return students[roll]["roll_no"], students[roll]["name"], prev

        st = self.conn.execute("SELECT roll_no, name FROM students WHERE roll_no = ?;", (roll,)).fetchone()
        if not st:
            raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
        prev_row = self.conn.execute(
            "SELECT status FROM attendance WHERE roll_no = ? AND att_date = ?;", (st[0], iso_day)
        ).fetchone()
        prev = prev_row[0] if prev_row else None

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO attendance (roll_no, att_date, status)
                VALUES (?, ?, ?)
                ON CONFLICT(roll_no, att_date)
                DO UPDATE SET status = excluded.status;
                """,
                (st[0], iso_day, status),
            )
        return st[0], st[1], prev

    def toggle_attendance(self, roll: str, target_date: date) -> tuple[str, str, str, str | None]:
        roll = self._clean_roll(roll)
        prev = self.get_status_for_day(roll, target_date)
        new_status = "Absent" if prev == "Present" else "Present"
        r_no, name, _ = self.mark_attendance(roll, new_status, target_date)
        return r_no, name, new_status, prev

    def mark_unmarked_absent(self, target_date: date) -> list[str]:
        """Marks all unmarked students Absent and returns list of affected roll numbers."""
        iso_day = target_date.isoformat()
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            day_recs = (snap.get("attendance") or {}).get(iso_day) or {}
            affected = [r for r in students if r not in day_recs]
            if affected:
                self._req("PATCH", f"attendance/{iso_day}", {r: "Absent" for r in affected})
            return affected

        rows = self.conn.execute(
            """
            SELECT s.roll_no FROM students s
            WHERE NOT EXISTS (
                SELECT 1 FROM attendance a WHERE a.roll_no = s.roll_no AND a.att_date = ?
            );
            """,
            (iso_day,),
        ).fetchall()
        affected = [r[0] for r in rows]
        if affected:
            with self.conn:
                self.conn.executemany(
                    "INSERT INTO attendance (roll_no, att_date, status) VALUES (?, ?, 'Absent');",
                    [(r, iso_day) for r in affected],
                )
        return affected

    def get_unmarked_students(self, target_date: date) -> list[tuple[str, str]]:
        iso_day = target_date.isoformat()
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            day_recs = (snap.get("attendance") or {}).get(iso_day) or {}
            return sorted(
                [(r, info.get("name", "")) for r, info in students.items() if isinstance(info, dict) and r not in day_recs],
                key=lambda x: x[0],
            )

        return self.conn.execute(
            """
            SELECT s.roll_no, s.name FROM students s
            WHERE NOT EXISTS (
                SELECT 1 FROM attendance a WHERE a.roll_no = s.roll_no AND a.att_date = ?
            )
            ORDER BY s.roll_no ASC;
            """,
            (iso_day,),
        ).fetchall()

    # --------------------------------------------------------------- queries
    def list_students(
        self, search: str = "", limit: int = 1000, shortage_only: bool = False
    ) -> tuple[list[tuple], int]:
        search_q = (search or "").strip().lower()
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            all_att = snap.get("attendance") or {}
            rows = []
            for roll, info in sorted(students.items(), key=lambda x: x[0]):
                if not isinstance(info, dict):
                    continue
                name = info.get("name", "")
                if search_q and (search_q not in roll.lower() and search_q not in name.lower()):
                    continue
                total_days = sum(1 for d in all_att.values() if isinstance(d, dict) and roll in d)
                present_days = sum(1 for d in all_att.values() if isinstance(d, dict) and d.get(roll) == "Present")
                if shortage_only and (total_days == 0 or (present_days * 100.0 / total_days) >= 75.0):
                    continue
                rows.append((roll, name, total_days, present_days))
            return rows[:limit], len(rows)

        like = f"%{search_q}%"
        having = (
            "HAVING COUNT(a.id) > 0 AND (SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) * 100.0 / COUNT(a.id)) < 75.0"
            if shortage_only
            else ""
        )
        sql = f"""
            SELECT
                s.roll_no,
                s.name,
                COUNT(a.id) AS total_days,
                COALESCE(SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END), 0) AS present_days
            FROM students s
            LEFT JOIN attendance a ON a.roll_no = s.roll_no
            WHERE (? = '' OR LOWER(s.roll_no) LIKE ? OR LOWER(s.name) LIKE ?)
            GROUP BY s.roll_no, s.name
            {having}
            ORDER BY s.roll_no ASC;
        """
        rows = self.conn.execute(sql, (search_q, like, like)).fetchall()
        return rows[:limit], len(rows)

    def attendance_for_day(
        self, target_date: date, status_filter: str | None = None, limit: int = 1000
    ) -> tuple[list[tuple], int]:
        iso_day = target_date.isoformat()
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            day_recs = (snap.get("attendance") or {}).get(iso_day) or {}
            rows = []
            for roll, st in sorted(day_recs.items(), key=lambda x: x[0]):
                if roll not in students:
                    continue
                if status_filter in ("Present", "Absent") and st != status_filter:
                    continue
                rows.append((roll, students[roll].get("name", ""), st))
            return rows[:limit], len(rows)

        params: list = [iso_day]
        extra = ""
        if status_filter in ("Present", "Absent"):
            extra = "AND a.status = ?"
            params.append(status_filter)
        rows = self.conn.execute(
            f"""
            SELECT s.roll_no, s.name, a.status
            FROM attendance a
            JOIN students s ON s.roll_no = a.roll_no
            WHERE a.att_date = ? {extra}
            ORDER BY s.roll_no ASC;
            """,
            params,
        ).fetchall()
        return rows[:limit], len(rows)

    def day_summary(self, target_date: date) -> dict:
        iso_day = target_date.isoformat()
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            day_recs = (snap.get("attendance") or {}).get(iso_day) or {}
            total_st = len(students)
            present = sum(1 for r, st in day_recs.items() if r in students and st == "Present")
            absent = sum(1 for r, st in day_recs.items() if r in students and st == "Absent")
        else:
            total_st = self.conn.execute("SELECT COUNT(*) FROM students;").fetchone()[0]
            present, absent = self.conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END), 0)
                FROM attendance WHERE att_date = ?;
                """,
                (iso_day,),
            ).fetchone()

        unmarked = max(0, total_st - (present + absent))
        marked = present + absent
        rate = (present / marked * 100.0) if marked else 0.0
        return {
            "students": total_st,
            "present": present,
            "absent": absent,
            "unmarked": unmarked,
            "rate": rate,
        }

    def recent_trend(self, anchor_date: date, days: int = 7) -> list[tuple[str, int, int, float]]:
        """Returns list of (DD Mon label, present, total_marked, percent) ending on anchor_date."""
        result = []
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            all_att = snap.get("attendance") or {}
            for offset in range(days - 1, -1, -1):
                d = anchor_date - timedelta(days=offset)
                iso = d.isoformat()
                recs = all_att.get(iso) if isinstance(all_att.get(iso), dict) else {}
                present = sum(1 for r, st in recs.items() if r in students and st == "Present")
                total = sum(1 for r in recs if r in students)
                pct = (present / total * 100.0) if total else 0.0
                result.append((d.strftime("%d %b"), present, total, pct))
            return result

        for offset in range(days - 1, -1, -1):
            d = anchor_date - timedelta(days=offset)
            iso = d.isoformat()
            present, total = self.conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END), 0),
                    COUNT(id)
                FROM attendance WHERE att_date = ?;
                """,
                (iso,),
            ).fetchone()
            pct = (present / total * 100.0) if total else 0.0
            result.append((d.strftime("%d %b"), present, total, pct))
        return result

    # --------------------------------------------------------------- reports
    def student_report(self, roll: str) -> dict:
        roll = self._clean_roll(roll)
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            if roll not in students:
                raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
            all_att = snap.get("attendance") or {}
            total = sum(1 for d in all_att.values() if isinstance(d, dict) and roll in d)
            present = sum(1 for d in all_att.values() if isinstance(d, dict) and d.get(roll) == "Present")
            name = students[roll]["name"]
        else:
            row = self.conn.execute(
                """
                SELECT s.name, COUNT(a.id), COALESCE(SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END), 0)
                FROM students s LEFT JOIN attendance a ON a.roll_no = s.roll_no
                WHERE s.roll_no = ? GROUP BY s.roll_no, s.name;
                """,
                (roll,),
            ).fetchone()
            if not row:
                raise StudentNotFoundError(f"No student found with roll number '{roll}'.")
            name, total, present = row[0], row[1], row[2]

        absent = total - present
        percent = (present / total * 100.0) if total else 0.0
        return {
            "roll_no": roll,
            "name": name,
            "total": total,
            "present": present,
            "absent": absent,
            "percent": percent,
        }

    def class_summary(self) -> dict:
        if self.cloud_enabled:
            snap = self._cloud_snapshot()
            students = snap.get("students") or {}
            all_att = snap.get("attendance") or {}
            st_count = len(students)
            days = len(all_att)
            entries = 0
            present = 0
            for recs in all_att.values():
                if isinstance(recs, dict):
                    for r, st in recs.items():
                        if r in students:
                            entries += 1
                            if st == "Present":
                                present += 1
        else:
            st_count = self.conn.execute("SELECT COUNT(*) FROM students;").fetchone()[0]
            days, entries, present = self.conn.execute(
                """
                SELECT COUNT(DISTINCT att_date), COUNT(id),
                       COALESCE(SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END), 0)
                FROM attendance;
                """
            ).fetchone()

        percent = (present / entries * 100.0) if entries else 0.0
        return {
            "students": st_count,
            "days": days,
            "entries": entries,
            "present": present,
            "percent": percent,
        }

    def shortage_list(self, threshold: float = 75.0) -> list[tuple]:
        rows, _ = self.list_students(limit=100_000, shortage_only=True)
        out = []
        for roll, name, total, present in rows:
            pct = (present / total * 100.0) if total else 0.0
            if pct < threshold:
                out.append((roll, name, present, total, pct))
        out.sort(key=lambda x: (x[4], x[0]))
        return out

    # ------------------------------------------------------- CSV & backups
    def import_students_csv(self, csv_path: str) -> tuple[int, int]:
        added = 0
        skipped = 0
        if self.cloud_enabled:
            snap = self._cloud_snapshot(force_refresh=True)
            existing = snap.get("students") or {}
            batch = {}
            with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
                for idx, row in enumerate(csv.reader(f)):
                    if len(row) < 2:
                        continue
                    r_raw, n_raw = row[0].strip(), row[1].strip()
                    if idx == 0 and r_raw.lower() in ("roll", "roll_no", "roll no", "roll number"):
                        continue
                    try:
                        roll = self._clean_roll(r_raw)
                        name = self._clean_name(n_raw)
                    except ValidationError:
                        skipped += 1
                        continue
                    if roll in existing or roll in batch:
                        skipped += 1
                    else:
                        batch[roll] = {"roll_no": roll, "name": name, "created_at": date.today().isoformat()}
                        added += 1
            if batch:
                self._req("PATCH", "students", batch)
            return added, skipped

        with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
            for idx, row in enumerate(csv.reader(f)):
                if len(row) < 2:
                    continue
                r_raw, n_raw = row[0].strip(), row[1].strip()
                if idx == 0 and r_raw.lower() in ("roll", "roll_no", "roll no", "roll number"):
                    continue
                try:
                    roll = self._clean_roll(r_raw)
                    name = self._clean_name(n_raw)
                except ValidationError:
                    skipped += 1
                    continue
                with self.conn:
                    cur = self.conn.execute(
                        "INSERT OR IGNORE INTO students (roll_no, name) VALUES (?, ?);", (roll, name)
                    )
                    if cur.rowcount == 1:
                        added += 1
                    else:
                        skipped += 1
        return added, skipped

    def export_register_csv(self, csv_path: str) -> int:
        rows, _ = self.list_students(limit=100_000)
        with open(csv_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Roll No", "Student Name", "Days Present", "Total Days", "Attendance %", "Status"])
            for roll, name, total, present in rows:
                pct = (present / total * 100.0) if total else 0.0
                pct_str = f"{pct:.1f}%" if total else "N/A"
                flag = "Shortage (<75%)" if (total > 0 and pct < 75.0) else ("Eligible" if total > 0 else "No Records")
                writer.writerow([roll, name, present, total, pct_str, flag])
        return len(rows)

    def backup_to(self, dest_path: str) -> None:
        if self.cloud_enabled:
            snapshot = self._cloud_snapshot(force_refresh=True)
            with open(dest_path, mode="w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            return
        with sqlite3.connect(dest_path) as dest_conn:
            self.conn.backup(dest_conn)

    def close(self):
        if self.conn is not None:
            self.conn.close()