"""
attendance_system.py - ClassPulse — Smart Student Attendance & Analytics
Desktop Application (Windows / Cross-Platform Tkinter)

Developed by:
- Piyush Ojha (Enrollment: BTEL26O1083)
- Rahul Tyagi (Enrollment: BTEL26O1095)
"""
import calendar
import os
import sqlite3
import sys
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from attendance_db import (
    AttendanceDB,
    AttendanceError,
    DuplicateStudentError,
    StudentNotFoundError,
    ValidationError,
)

# PyInstaller-safe paths
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    ASSET_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ASSET_DIR = BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "classpulse.db")
ROW_LIMIT = 1000
ATTENDANCE_THRESHOLD = 75.0

# ---------------------------------------------------------------- colour theme
BG = "#f8fafc"
CARD = "#ffffff"
BORDER = "#e2e8f0"
TEXT = "#0f172a"
MUTED = "#64748b"
PRIMARY = "#2563eb"
PRIMARY_DARK = "#1e3a8a"
HEADER_BG = "#0f172a"
GREEN = "#15803d"
GREEN_SOFT = "#dcfce7"
RED = "#b91c1c"
RED_SOFT = "#fee2e2"
AMBER = "#b45309"
TEAL = "#0f766e"
PURPLE = "#6d28d9"
FONT = "Segoe UI"


# ============================================================ Calendar Popup
class CalendarPopup(tk.Toplevel):
    """Interactive monthly calendar popover to select any past or current date."""

    def __init__(self, parent: tk.Widget, current_date: date, on_select):
        super().__init__(parent)
        self.on_select = on_select
        self.selected = current_date
        self.today = date.today()
        self.view_year = current_date.year
        self.view_month = current_date.month

        self.title("Select Date")
        self.resizable(False, False)
        self.configure(bg=BORDER)
        self.transient(parent.winfo_toplevel())

        outer = tk.Frame(self, bg=CARD, padx=14, pady=12)
        outer.pack(padx=1, pady=1)

        # Month/Year header
        hdr = tk.Frame(outer, bg=CARD)
        hdr.pack(fill="x", pady=(0, 8))

        tk.Button(
            hdr, text="◀", bg="#f1f5f9", fg=TEXT, bd=0, padx=8, pady=2, cursor="hand2",
            font=(FONT, 9, "bold"), command=self._prev_month
        ).pack(side="left")

        self.month_lbl = tk.Label(hdr, text="", bg=CARD, fg=TEXT, font=(FONT, 10, "bold"))
        self.month_lbl.pack(side="left", expand=True)

        tk.Button(
            hdr, text="▶", bg="#f1f5f9", fg=TEXT, bd=0, padx=8, pady=2, cursor="hand2",
            font=(FONT, 9, "bold"), command=self._next_month
        ).pack(side="right")

        # Day names
        days_row = tk.Frame(outer, bg=CARD)
        days_row.pack(fill="x")
        for idx, d_name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            tk.Label(
                days_row, text=d_name, width=4, bg=CARD, fg=MUTED, font=(FONT, 8, "bold")
            ).grid(row=0, column=idx, pady=(0, 4))

        # Calendar grid
        self.grid_frame = tk.Frame(outer, bg=CARD)
        self.grid_frame.pack()

        # Footer quick-jump
        ftr = tk.Frame(outer, bg=CARD)
        ftr.pack(fill="x", pady=(8, 0))
        tk.Button(
            ftr, text="Jump to Today", bg=PRIMARY, fg="white", bd=0, padx=10, pady=4,
            font=(FONT, 8, "bold"), cursor="hand2", command=lambda: self._pick(self.today)
        ).pack(side="left")
        tk.Button(
            ftr, text="Close", bg="#e2e8f0", fg=TEXT, bd=0, padx=10, pady=4,
            font=(FONT, 8, "bold"), cursor="hand2", command=self.destroy
        ).pack(side="right")

        self._render_days()

        # Position right below trigger button
        self.update_idletasks()
        bx = parent.winfo_rootx() + parent.winfo_width() - self.winfo_width()
        by = parent.winfo_rooty() + parent.winfo_height() + 6
        self.geometry(f"+{max(10, bx)}+{by}")

        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.focus_set()

    def _prev_month(self):
        if self.view_month == 1:
            self.view_month = 12
            self.view_year -= 1
        else:
            self.view_month -= 1
        self._render_days()

    def _next_month(self):
        if (self.view_year, self.view_month) >= (self.today.year, self.today.month):
            return
        if self.view_month == 12:
            self.view_month = 1
            self.view_year += 1
        else:
            self.view_month += 1
        self._render_days()

    def _render_days(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.month_lbl.config(text=f"{calendar.month_name[self.view_month]} {self.view_year}")

        cal = calendar.monthcalendar(self.view_year, self.view_month)
        for r_idx, week in enumerate(cal):
            for c_idx, day_num in enumerate(week):
                if day_num == 0:
                    tk.Label(self.grid_frame, text="", width=4, bg=CARD).grid(row=r_idx, column=c_idx, padx=1, pady=1)
                    continue
                cell_date = date(self.view_year, self.view_month, day_num)
                is_future = cell_date > self.today
                is_selected = cell_date == self.selected
                is_today = cell_date == self.today

                bg = PRIMARY if is_selected else ("#e0e7ff" if is_today else CARD)
                fg = "#cbd5e1" if is_future else ("white" if is_selected else (PRIMARY_DARK if is_today else TEXT))
                font_spec = (FONT, 9, "bold") if (is_selected or is_today) else (FONT, 9)

                btn = tk.Button(
                    self.grid_frame,
                    text=str(day_num),
                    width=4,
                    bg=bg,
                    fg=fg,
                    bd=0,
                    pady=4,
                    font=font_spec,
                    state="disabled" if is_future else "normal",
                    cursor="arrow" if is_future else "hand2",
                    command=lambda d=cell_date: self._pick(d),
                )
                btn.grid(row=r_idx, column=c_idx, padx=1, pady=1)

    def _pick(self, chosen: date):
        self.on_select(chosen)
        self.destroy()


# ============================================================ Roll Call Modal
class RollCallDialog(tk.Toplevel):
    """Rapid keyboard-driven sequential roll call for unmarked students."""

    def __init__(self, parent: tk.Tk, target_date: date, unmarked: list[tuple[str, str]], on_mark):
        super().__init__(parent)
        self.unmarked = unmarked
        self.idx = 0
        self.on_mark = on_mark

        self.title(f"Quick Roll Call — {target_date.strftime('%d %b %Y')}")
        self.configure(bg=CARD)
        self.resizable(False, False)
        self.transient(parent)

        body = tk.Frame(self, bg=CARD, padx=28, pady=24)
        body.pack()

        self.progress_lbl = tk.Label(body, text="", bg=CARD, fg=MUTED, font=(FONT, 9, "bold"))
        self.progress_lbl.pack()

        self.roll_lbl = tk.Label(body, text="", bg=CARD, fg=PRIMARY, font=(FONT, 24, "bold"))
        self.roll_lbl.pack(pady=(10, 2))

        self.name_lbl = tk.Label(body, text="", bg=CARD, fg=TEXT, font=(FONT, 14, "bold"))
        self.name_lbl.pack(pady=(0, 18))

        btns = tk.Frame(body, bg=CARD)
        btns.pack()

        tk.Button(
            btns, text="✔ Present (P)", bg=GREEN, fg="white", bd=0, padx=16, pady=10,
            font=(FONT, 10, "bold"), cursor="hand2", command=lambda: self._step("Present")
        ).pack(side="left", padx=5)
        tk.Button(
            btns, text="✖ Absent (A)", bg=RED, fg="white", bd=0, padx=16, pady=10,
            font=(FONT, 10, "bold"), cursor="hand2", command=lambda: self._step("Absent")
        ).pack(side="left", padx=5)
        tk.Button(
            btns, text="Skip (S)", bg="#64748b", fg="white", bd=0, padx=14, pady=10,
            font=(FONT, 10, "bold"), cursor="hand2", command=self._skip
        ).pack(side="left", padx=5)

        tk.Label(
            body, text="Keyboard shortcuts: [P] Present   [A] Absent   [S] Skip   [Esc] Finish",
            bg=CARD, fg=MUTED, font=(FONT, 8)
        ).pack(pady=(14, 0))

        self.bind("p", lambda e: self._step("Present"))
        self.bind("P", lambda e: self._step("Present"))
        self.bind("a", lambda e: self._step("Absent"))
        self.bind("A", lambda e: self._step("Absent"))
        self.bind("s", lambda e: self._skip())
        self.bind("S", lambda e: self._skip())
        self.bind("<Escape>", lambda e: self.destroy())

        self._show_current()
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        self.grab_set()
        self.focus_set()

    def _show_current(self):
        if self.idx >= len(self.unmarked):
            self.destroy()
            return
        roll, name = self.unmarked[self.idx]
        self.progress_lbl.config(text=f"Student {self.idx + 1} of {len(self.unmarked)} remaining")
        self.roll_lbl.config(text=roll)
        self.name_lbl.config(text=name)

    def _step(self, status: str):
        if self.idx < len(self.unmarked):
            roll, _ = self.unmarked[self.idx]
            self.on_mark(roll, status)
            self.idx += 1
            self._show_current()

    def _skip(self):
        self.idx += 1
        self._show_current()


# ============================================================ Main Application
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.db = AttendanceDB(DB_PATH)
        self._day = date.today()
        self._today_ref = date.today()
        self._search_job = None
        self._sort_state: dict[ttk.Treeview, tuple[str | None, bool]] = {}
        self._undo_stack: list[tuple] = []

        self.roll_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Present")
        self.filter_var = tk.StringVar(value="All")
        self.shortage_only_var = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self.message_var = tk.StringVar(
            value="Ready • Double-click any student row to toggle Present/Absent, or press Ctrl+F to search."
        )
        self.date_var = tk.StringVar()
        self.list_note_var = tk.StringVar()
        self.log_note_var = tk.StringVar()
        self.stat_vars: dict[str, tk.StringVar] = {}

        self._setup_window()
        self._setup_styles()
        self._build_header()
        self._build_stat_cards()
        self._build_body()
        self._build_status_bar()
        self._bind_shortcuts()

        self.search_var.trace_add("write", self._on_search_change)
        self._update_date_label()
        self.refresh_all()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._tick()

    # ------------------------------------------------------------------ setup
    def _setup_window(self):
        self.root.title("ClassPulse — Smart Student Attendance & Analytics")
        self.root.geometry("1160x730")
        self.root.minsize(1020, 640)
        self.root.configure(bg=BG)

        for icon_name in ("classpulse.ico", "app_icon.ico"):
            icon_path = os.path.join(ASSET_DIR, icon_name)
            if os.path.exists(icon_path):
                try:
                    self.root.iconbitmap(default=icon_path)
                    break
                except tk.TclError:
                    pass

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Card.TLabel", background=CARD)
        s.configure("CardBold.TLabel", background=CARD, font=(FONT, 10, "bold"))
        s.configure("CardTitle.TLabel", background=CARD, font=(FONT, 11, "bold"))
        s.configure("Field.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
        s.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
        s.configure("Empty.TLabel", background="white", foreground=MUTED, font=(FONT, 10))
        s.configure("TEntry", padding=6, fieldbackground="white", bordercolor=BORDER)
        s.map("TEntry", bordercolor=[("focus", PRIMARY)])
        s.configure("Card.TRadiobutton", background=CARD, font=(FONT, 10))
        s.map("Card.TRadiobutton", background=[("active", CARD)])
        s.configure("Card.TCheckbutton", background=CARD, font=(FONT, 9, "bold"), foreground=RED)
        s.map("Card.TCheckbutton", background=[("active", CARD)])

        def button(name, bg, hover, pad=(12, 8), size=9):
            s.configure(
                name,
                background=bg,
                foreground="white",
                borderwidth=0,
                focusthickness=0,
                padding=pad,
                font=(FONT, size, "bold"),
            )
            s.map(name, background=[("active", hover), ("pressed", hover)])

        button("Primary.TButton", PRIMARY, PRIMARY_DARK, pad=(12, 8), size=10)
        button("Success.TButton", GREEN, "#166534", pad=(12, 8), size=10)
        button("Danger.TButton", RED, "#991b1b", pad=(12, 8), size=10)
        button("Warning.TButton", AMBER, "#92400e", pad=(12, 8), size=9)
        button("Ghost.TButton", "#64748b", "#475569", pad=(10, 7), size=9)
        button("Tool.TButton", TEAL, "#115e59", pad=(11, 7), size=9)
        button("Purple.TButton", PURPLE, "#5b21b6", pad=(12, 8), size=9)

        s.configure(
            "Treeview",
            rowheight=32,
            font=(FONT, 10),
            background="white",
            fieldbackground="white",
            bordercolor=BORDER,
            borderwidth=0,
        )
        s.configure(
            "Treeview.Heading",
            font=(FONT, 9, "bold"),
            background="#e2e8f0",
            foreground=TEXT,
            relief="flat",
            padding=(8, 7),
        )
        s.map("Treeview", background=[("selected", PRIMARY)], foreground=[("selected", "white")])
        s.map("Treeview.Heading", background=[("active", "#cbd5e1")])

        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure(
            "TNotebook.Tab",
            padding=(18, 9),
            font=(FONT, 10, "bold"),
            background="#e2e8f0",
            foreground=MUTED,
        )
        s.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", PRIMARY)])
        s.configure(
            "Green.Horizontal.TProgressbar",
            troughcolor="#e2e8f0",
            background=GREEN,
            lightcolor=GREEN,
            darkcolor=GREEN,
            bordercolor="#e2e8f0",
        )
        s.configure(
            "Red.Horizontal.TProgressbar",
            troughcolor="#e2e8f0",
            background=RED,
            lightcolor=RED,
            darkcolor=RED,
            bordercolor="#e2e8f0",
        )

    def _bind_shortcuts(self):
        self.root.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), self.search_entry.select_range(0, "end")))
        self.root.bind("<Control-F>", lambda e: (self.search_entry.focus_set(), self.search_entry.select_range(0, "end")))
        self.root.bind("<Control-z>", lambda e: self.undo_last_action())
        self.root.bind("<Control-Z>", lambda e: self.undo_last_action())
        self.root.bind("<Escape>", lambda e: self.clear_inputs())

    # --------------------------------------------------------------- layout
    def _build_header(self):
        bar = tk.Frame(self.root, bg=HEADER_BG)
        bar.pack(fill="x")

        brand = tk.Frame(bar, bg=HEADER_BG)
        brand.pack(side="left", padx=20, pady=12)

        top_brand = tk.Frame(brand, bg=HEADER_BG)
        top_brand.pack(anchor="w")
        tk.Label(
            top_brand, text="ClassPulse", bg=HEADER_BG, fg="white", font=(FONT, 18, "bold")
        ).pack(side="left")

        mode_text = "● Cloud Synced" if self.db.cloud_enabled else "● Local Mode"
        mode_bg = "#065f46" if self.db.cloud_enabled else "#1e293b"
        mode_fg = "#6ee7b7" if self.db.cloud_enabled else "#94a3b8"
        self.sync_badge = tk.Label(
            top_brand, text=mode_text, bg=mode_bg, fg=mode_fg, padx=8, pady=2, font=(FONT, 8, "bold")
        )
        self.sync_badge.pack(side="left", padx=(10, 0))

        tk.Label(
            brand,
            text="Smart Student Attendance & Analytics",
            bg=HEADER_BG,
            fg="#94a3b8",
            font=(FONT, 9),
        ).pack(anchor="w")

        controls = tk.Frame(bar, bg=HEADER_BG)
        controls.pack(side="right", padx=20)

        self.cal_btn = tk.Button(
            controls,
            textvariable=self.date_var,
            bg="#1e293b",
            fg="white",
            activebackground="#334155",
            activeforeground="white",
            bd=0,
            padx=14,
            pady=7,
            font=(FONT, 10, "bold"),
            cursor="hand2",
            command=self._open_calendar,
        )
        self.cal_btn.pack(side="left", padx=(0, 8))

        self.undo_btn = tk.Button(
            controls,
            text="↶ Undo",
            bg="#1e293b",
            fg="#cbd5e1",
            activebackground="#334155",
            activeforeground="white",
            bd=0,
            padx=12,
            pady=7,
            font=(FONT, 9, "bold"),
            cursor="hand2",
            command=self.undo_last_action,
        )
        self.undo_btn.pack(side="left", padx=(0, 8))

        tk.Button(
            controls,
            text="ⓘ About",
            bg=PRIMARY,
            fg="white",
            activebackground=PRIMARY_DARK,
            activeforeground="white",
            bd=0,
            padx=12,
            pady=7,
            font=(FONT, 9, "bold"),
            cursor="hand2",
            command=self.show_about_dialog,
        ).pack(side="left")

    def _build_stat_cards(self):
        row = ttk.Frame(self.root)
        row.pack(fill="x", padx=20, pady=(16, 12))
        cards = (
            ("students", "Registered Students", PRIMARY),
            ("present", "Present Today", GREEN),
            ("absent", "Absent Today", RED),
            ("unmarked", "Not Marked Yet", AMBER),
            ("rate", "Today's Attendance", PURPLE),
        )
        for i, (key, label, colour) in enumerate(cards):
            row.columnconfigure(i, weight=1, uniform="stat")
            box = tk.Frame(row, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
            tk.Frame(box, bg=colour, height=4).pack(fill="x", side="top")
            var = tk.StringVar(value="0%" if key == "rate" else "0")
            self.stat_vars[key] = var
            tk.Label(box, textvariable=var, font=(FONT, 21, "bold"), bg=CARD, fg=colour).pack(
                anchor="w", padx=14, pady=(8, 0)
            )
            tk.Label(box, text=label, font=(FONT, 9), bg=CARD, fg=MUTED).pack(
                anchor="w", padx=14, pady=(0, 10)
            )

    def _build_body(self):
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_left_panel(body)
        self._build_right_panel(body)

    def _card(self, parent, title):
        outer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="x", pady=(0, 12))
        ttk.Label(outer, text=title, style="CardTitle.TLabel").pack(anchor="w", padx=16, pady=(12, 6))
        inner = ttk.Frame(outer, style="Card.TFrame")
        inner.pack(fill="x", padx=16, pady=(0, 14))
        return inner

    def _build_left_panel(self, parent):
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 14))

        # --- Student Management Card
        card = self._card(left, "Student Management")
        ttk.Label(card, text="Roll number", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.roll_entry = ttk.Entry(card, textvariable=self.roll_var, width=34)
        self.roll_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        ttk.Label(card, text="Student name", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        self.name_entry = ttk.Entry(card, textvariable=self.name_var, width=34)
        self.name_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 10))

        ttk.Button(card, text="Add student", style="Primary.TButton", cursor="hand2", command=self.add_student).grid(
            row=4, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(card, text="Update name", style="Tool.TButton", cursor="hand2", command=self.update_student).grid(
            row=4, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Button(card, text="Remove student", style="Danger.TButton", cursor="hand2", command=self.remove_student).grid(
            row=5, column=0, sticky="ew", padx=(0, 4), pady=(8, 0)
        )
        ttk.Button(card, text="Clear (Esc)", style="Ghost.TButton", cursor="hand2", command=self.clear_inputs).grid(
            row=5, column=1, sticky="ew", padx=(4, 0), pady=(8, 0)
        )
        card.columnconfigure((0, 1), weight=1)
        self.name_entry.bind("<Return>", lambda e: self.add_student())

        # --- Attendance Actions Card
        card = self._card(left, "Mark Attendance")
        radios = ttk.Frame(card, style="Card.TFrame")
        radios.pack(fill="x")
        ttk.Radiobutton(
            radios, text="Present", value="Present", variable=self.status_var, style="Card.TRadiobutton"
        ).pack(side="left", padx=(0, 22))
        ttk.Radiobutton(
            radios, text="Absent", value="Absent", variable=self.status_var, style="Card.TRadiobutton"
        ).pack(side="left")

        ttk.Button(
            card, text="Mark Attendance (Enter)", style="Success.TButton", cursor="hand2", command=self.mark_attendance
        ).pack(fill="x", pady=(10, 6))
        ttk.Button(
            card, text="⚡ Quick Roll Call Mode", style="Purple.TButton", cursor="hand2", command=self.start_roll_call
        ).pack(fill="x", pady=(0, 6))
        ttk.Button(
            card, text="Mark All Unmarked Absent", style="Warning.TButton", cursor="hand2", command=self.mark_remaining_absent
        ).pack(fill="x")
        self.roll_entry.bind("<Return>", lambda e: self.mark_attendance())

    def _build_right_panel(self, parent):
        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew")

        tools = ttk.Frame(right)
        tools.pack(side="bottom", fill="x", pady=(10, 0))
        tool_buttons = (
            ("Student Report", self.student_report),
            ("Class Summary", self.class_summary),
            ("Shortage (<75%)", self.shortage_report),
            ("Import CSV", self.import_csv),
            ("Export CSV", self.export_csv),
            ("Backup Data", self.backup_database),
        )
        for text, command in tool_buttons:
            ttk.Button(tools, text=text, style="Tool.TButton", cursor="hand2", command=command).pack(
                side="left", padx=(0, 6)
            )

        notebook = ttk.Notebook(right)
        notebook.pack(side="top", fill="both", expand=True)

        # --- Tab 1: Students Directory
        tab1 = ttk.Frame(notebook, style="Card.TFrame", padding=14)
        notebook.add(tab1, text="Students & Attendance %")
        bar1 = ttk.Frame(tab1, style="Card.TFrame")
        bar1.pack(fill="x", pady=(0, 10))
        ttk.Label(bar1, text="Search", style="Card.TLabel").pack(side="left")
        self.search_entry = ttk.Entry(bar1, textvariable=self.search_var, width=26)
        self.search_entry.pack(side="left", padx=8)
        ttk.Button(
            bar1, text="Clear", style="Ghost.TButton", cursor="hand2", command=lambda: self.search_var.set("")
        ).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(
            bar1,
            text="Only <75% shortage",
            variable=self.shortage_only_var,
            style="Card.TCheckbutton",
            command=self.refresh_students,
        ).pack(side="left")
        ttk.Label(bar1, textvariable=self.list_note_var, style="Muted.TLabel").pack(side="right")

        self.students_tree, self.students_empty = self._make_tree(
            tab1,
            (
                ("roll", "Roll No", 120, "w"),
                ("name", "Student Name", 230, "w"),
                ("present", "Present", 80, "center"),
                ("total", "Total Days", 85, "center"),
                ("percent", "Attendance %", 110, "center"),
            ),
            "No students found. Register a student on the left or click 'Import CSV'.",
        )
        self.students_tree.bind("<<TreeviewSelect>>", self.on_student_select)
        self.students_tree.bind("<Double-1>", self.on_student_double_click)

        # --- Tab 2: Selected Day Log
        tab2 = ttk.Frame(notebook, style="Card.TFrame", padding=14)
        notebook.add(tab2, text="Daily Attendance Log")
        bar2 = ttk.Frame(tab2, style="Card.TFrame")
        bar2.pack(fill="x", pady=(0, 10))
        ttk.Label(bar2, text="Filter:", style="Card.TLabel").pack(side="left")
        for option in ("All", "Present", "Absent"):
            ttk.Radiobutton(
                bar2,
                text=option,
                value=option,
                variable=self.filter_var,
                style="Card.TRadiobutton",
                command=self.refresh_log,
            ).pack(side="left", padx=(12, 0))
        ttk.Label(bar2, textvariable=self.log_note_var, style="Muted.TLabel").pack(side="right")

        self.log_tree, self.log_empty = self._make_tree(
            tab2,
            (
                ("roll", "Roll No", 130, "w"),
                ("name", "Student Name", 300, "w"),
                ("status", "Status", 130, "center"),
            ),
            "No attendance entries recorded for this date yet.",
        )

        # --- Tab 3: Visual Analytics
        tab3 = ttk.Frame(notebook, style="Card.TFrame", padding=16)
        notebook.add(tab3, text="📊 Visual Analytics")
        self._build_analytics_tab(tab3)

    def _build_analytics_tab(self, parent):
        top_row = ttk.Frame(parent, style="Card.TFrame")
        top_row.pack(fill="x", pady=(0, 10))
        ttk.Label(top_row, text="7-Day Class Attendance Trend", style="CardTitle.TLabel").pack(side="left")
        ttk.Button(
            top_row, text="Copy Defaulter Notice (<75%)", style="Warning.TButton", cursor="hand2",
            command=self.copy_shortage_notice
        ).pack(side="right")

        self.chart_canvas = tk.Canvas(parent, height=230, bg="#f8fafc", highlightthickness=1, highlightbackground=BORDER)
        self.chart_canvas.pack(fill="x", pady=(0, 12))

        self.analytics_note = tk.Label(
            parent, text="", bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w", justify="left"
        )
        self.analytics_note.pack(fill="x")

    def _make_tree(self, parent, columns, empty_text):
        wrap = ttk.Frame(parent, style="Card.TFrame")
        wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(wrap, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        self._sort_state[tree] = (None, False)

        for cid, heading, width, anchor in columns:
            tree.heading(
                cid,
                text=heading,
                anchor=anchor,
                command=lambda t=tree, c=cid, h=heading, cols=columns: self._sort_tree(t, c, h, cols),
            )
            tree.column(cid, width=width, anchor=anchor, stretch=(cid == "name"))

        scroll = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        tree.tag_configure("odd", background="#f8fafc")
        tree.tag_configure("present", background=GREEN_SOFT, foreground=GREEN)
        tree.tag_configure("absent", background=RED_SOFT, foreground=RED)
        tree.tag_configure("shortage", background=RED_SOFT, foreground=RED)

        empty_lbl = ttk.Label(wrap, text=empty_text, style="Empty.TLabel")
        return tree, empty_lbl

    def _sort_tree(self, tree: ttk.Treeview, col: str, heading: str, columns: tuple):
        last_col, descending = self._sort_state[tree]
        descending = not descending if last_col == col else False
        self._sort_state[tree] = (col, descending)

        for cid, h_text, _, _ in columns:
            arrow = (" ▼" if descending else " ▲") if cid == col else ""
            tree.heading(cid, text=h_text + arrow)

        items = [(tree.set(k, col), k) for k in tree.get_children("")]

        def sort_key(pair):
            val = pair[0].replace("✔", "").replace("✖", "").rstrip("%").strip()
            if val == "-":
                return (1, 0.0)
            try:
                return (0, float(val))
            except ValueError:
                return (0, val.lower())

        items.sort(key=sort_key, reverse=descending)
        for index, (_, k) in enumerate(items):
            tree.move(k, "", index)

    def _build_status_bar(self):
        self.status_bar = tk.Frame(self.root, bg="#e2e8f0")
        self.status_bar.pack(fill="x", side="bottom")
        self.status_lbl = tk.Label(
            self.status_bar, textvariable=self.message_var, bg="#e2e8f0", fg=TEXT, anchor="w", font=(FONT, 9, "bold")
        )
        self.status_lbl.pack(fill="x", padx=20, pady=7)

    # --------------------------------------------------------------- helpers
    def toast(self, text: str, kind: str = "info"):
        palette = {
            "info": ("#e2e8f0", TEXT),
            "success": (GREEN_SOFT, GREEN),
            "warning": ("#fef3c7", AMBER),
            "error": (RED_SOFT, RED),
        }
        bg, fg = palette.get(kind, palette["info"])
        self.status_bar.config(bg=bg)
        self.status_lbl.config(bg=bg, fg=fg)
        self.message_var.set(text)

    def _update_date_label(self):
        suffix = " (Today)" if self._day == date.today() else ""
        self.date_var.set(f"📅  {self._day.strftime('%a, %d %b %Y')}{suffix}  ▾")

    def _open_calendar(self):
        CalendarPopup(self.cal_btn, self._day, self._on_date_chosen)

    def _on_date_chosen(self, chosen: date):
        self._day = chosen
        self._update_date_label()
        self.refresh_all()
        self.toast(f"Selected date: {self._day.strftime('%d %B %Y')}", "info")

    def _call(self, func, *args):
        try:
            return True, func(*args)
        except ValidationError as e:
            messagebox.showwarning("Check your input", str(e), parent=self.root)
        except DuplicateStudentError as e:
            messagebox.showerror("Duplicate roll number", str(e), parent=self.root)
        except StudentNotFoundError as e:
            messagebox.showerror("Student not found", str(e), parent=self.root)
        except (AttendanceError, sqlite3.Error) as e:
            messagebox.showerror("Database error", f"Something went wrong:\n{e}", parent=self.root)
        return False, None

    def clear_inputs(self):
        self.roll_var.set("")
        self.name_var.set("")
        self.students_tree.selection_remove(self.students_tree.selection())
        self.roll_entry.focus_set()

    # --------------------------------------------------------------- actions
    def add_student(self):
        ok, result = self._call(self.db.add_student, self.roll_var.get(), self.name_var.get())
        if ok:
            self.clear_inputs()
            self.refresh_all()
            self.toast(f"✔ Added student {result[1]} ({result[0]}).", "success")

    def update_student(self):
        ok, res = self._call(self.db.update_student_name, self.roll_var.get(), self.name_var.get())
        if ok:
            self.refresh_all()
            self.toast(f"Updated {res[0]}: '{res[1]}' → '{res[2]}'.", "info")

    def remove_student(self):
        ok, info = self._call(self.db.get_student, self.roll_var.get())
        if not ok:
            return
        roll, name, records = info
        if not messagebox.askyesno(
            "Confirm deletion",
            f"Remove {name} ({roll}) and {records} attendance record(s)?\n\nThis cannot be undone.",
            icon="warning",
            parent=self.root,
        ):
            return
        ok, _ = self._call(self.db.remove_student, roll)
        if ok:
            self.clear_inputs()
            self.refresh_all()
            self.toast(f"Removed {name} ({roll}) and {records} record(s).", "warning")

    def mark_attendance(self):
        status = self.status_var.get()
        ok, result = self._call(self.db.mark_attendance, self.roll_var.get(), status, self._day)
        if ok:
            roll, name, prev = result
            self._undo_stack.append(("single", roll, self._day, prev))
            self.refresh_all()
            self.toast(
                f"{'✔' if status == 'Present' else '✖'} {roll} ({name}) marked {status} for {self._day.isoformat()}.",
                "success" if status == "Present" else "warning",
            )

    def start_roll_call(self):
        ok, unmarked = self._call(self.db.get_unmarked_students, self._day)
        if not ok:
            return
        if not unmarked:
            self.toast("All registered students are already marked for this date!", "info")
            return

        def mark_from_modal(roll: str, status: str):
            ok_m, res = self._call(self.db.mark_attendance, roll, status, self._day)
            if ok_m:
                self._undo_stack.append(("single", roll, self._day, res[2]))
                self.refresh_all()
                self.toast(f"Roll Call: {roll} ({res[1]}) → {status}", "success" if status == "Present" else "warning")

        RollCallDialog(self.root, self._day, unmarked, mark_from_modal)

    def mark_remaining_absent(self):
        summary = self.db.day_summary(self._day)
        if summary["unmarked"] == 0:
            self.toast("All registered students already have attendance marked for this date.", "info")
            return
        if not messagebox.askyesno(
            "Bulk Mark Absent",
            f"Mark all {summary['unmarked']} unmarked student(s) as Absent for {self._day.strftime('%d %b %Y')}?",
            parent=self.root,
        ):
            return
        ok, affected = self._call(self.db.mark_unmarked_absent, self._day)
        if ok:
            self._undo_stack.append(("bulk_absent", list(affected), self._day))
            self.refresh_all()
            self.toast(f"Marked {len(affected)} remaining student(s) Absent (Press Ctrl+Z to undo).", "warning")

    def undo_last_action(self):
        if not self._undo_stack:
            self.toast("Nothing to undo.", "info")
            return
        action = self._undo_stack.pop()
        if action[0] == "single":
            _, roll, day_obj, prev_status = action
            if prev_status is None:
                ok, _ = self._call(self.db.clear_attendance_for_day, roll, day_obj)
            else:
                ok, _ = self._call(self.db.mark_attendance, roll, prev_status, day_obj)
            if ok:
                self.refresh_all()
                self.toast(f"↶ Undid attendance change for {roll} on {day_obj.isoformat()}.", "info")
        elif action[0] == "bulk_absent":
            _, rolls, day_obj = action
            for r in rolls:
                self._call(self.db.clear_attendance_for_day, r, day_obj)
            self.refresh_all()
            self.toast(f"↶ Undid bulk Absent marking for {len(rolls)} student(s).", "info")

    def student_report(self):
        ok, r = self._call(self.db.student_report, self.roll_var.get())
        if ok:
            self._report_dialog(
                r["name"],
                f"Roll Number: {r['roll_no']}",
                (
                    ("Total days recorded", r["total"]),
                    ("Days present", r["present"]),
                    ("Days absent", r["absent"]),
                ),
                r["percent"],
                "attendance",
            )

    def class_summary(self):
        ok, r = self._call(self.db.class_summary)
        if ok:
            self._report_dialog(
                "Class Summary Report",
                f"As of {self._day.isoformat()}",
                (
                    ("Registered students", r["students"]),
                    ("Class days recorded", r["days"]),
                    ("Attendance entries", r["entries"]),
                    ("Entries marked present", r["present"]),
                ),
                r["percent"],
                "overall attendance",
            )

    def shortage_report(self):
        ok, rows = self._call(self.db.shortage_list, ATTENDANCE_THRESHOLD)
        if not ok:
            return
        if not rows:
            messagebox.showinfo(
                "Attendance Shortage (<75%)",
                "Great news! No students are currently below the 75.0% attendance threshold.",
                parent=self.root,
            )
            return
        lines = [f"{r[0]}  |  {r[1]}  —  {r[4]:.1f}% ({r[2]}/{r[3]} days)" for r in rows[:25]]
        extra = f"\n...and {len(rows) - 25} more (use Export CSV for full register)." if len(rows) > 25 else ""
        messagebox.showwarning(
            f"Shortage Alert: {len(rows)} Student(s) Below 75%",
            "\n".join(lines) + extra,
            parent=self.root,
        )

    def copy_shortage_notice(self):
        ok, rows = self._call(self.db.shortage_list, ATTENDANCE_THRESHOLD)
        if not ok:
            return
        if not rows:
            self.toast("No students are below 75% attendance.", "info")
            return
        header = f"ATTENDANCE SHORTAGE NOTICE (<75%) — Date: {date.today().strftime('%d %b %Y')}\n"
        body = "\n".join([f"- {r[0]} ({r[1]}): {r[4]:.1f}% [{r[2]}/{r[3]} days]" for r in rows])
        self.root.clipboard_clear()
        self.root.clipboard_append(header + body)
        self.toast(f"Copied shortage list ({len(rows)} students) to clipboard!", "success")

    def import_csv(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Import Student Roster CSV (Roll No, Name)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        ok, result = self._call(self.db.import_students_csv, path)
        if ok:
            added, skipped = result
            self.refresh_all()
            self.toast(f"CSV Import: {added} student(s) added, {skipped} duplicate/invalid skipped.", "success")

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export Attendance Register CSV",
            defaultextension=".csv",
            initialfile=f"ClassPulse_Register_{date.today().isoformat()}.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        ok, count = self._call(self.db.export_register_csv, path)
        if ok:
            self.toast(f"Exported {count} student record(s) to {os.path.basename(path)}.", "success")

    def backup_database(self):
        ext = ".json" if self.db.cloud_enabled else ".db"
        ftype = [("JSON Cloud Snapshot", "*.json")] if self.db.cloud_enabled else [("SQLite Database", "*.db")]
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save Database Backup",
            defaultextension=ext,
            initialfile=f"ClassPulse_Backup_{date.today().isoformat()}{ext}",
            filetypes=ftype,
        )
        if not path:
            return
        ok, _ = self._call(self.db.backup_to, path)
        if ok:
            self.toast(f"Backup saved to {os.path.basename(path)}.", "success")

    # -------------------------------------------------------------- refreshing
    def refresh_all(self):
        self.refresh_students()
        self.refresh_log()
        self.refresh_stats()
        self.refresh_analytics()

    def refresh_students(self):
        rows, total = self.db.list_students(
            self.search_var.get(), ROW_LIMIT, shortage_only=self.shortage_only_var.get()
        )
        tree = self.students_tree
        tree.delete(*tree.get_children())
        if not rows:
            self.students_empty.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.students_empty.place_forget()

        for i, (roll, name, days, present) in enumerate(rows):
            pct_val = (present / days * 100.0) if days else None
            percent = f"{pct_val:.1f}%" if pct_val is not None else "-"
            tags = []
            if pct_val is not None and pct_val < ATTENDANCE_THRESHOLD:
                tags.append("shortage")
            elif i % 2:
                tags.append("odd")
            tree.insert("", "end", iid=roll, tags=tuple(tags), values=(roll, name, present, days, percent))

        self.list_note_var.set(
            f"Showing {len(rows)} of {total} students" if total > len(rows) else f"{total} student(s)"
        )

    def refresh_log(self):
        choice = self.filter_var.get()
        rows, total = self.db.attendance_for_day(self._day, None if choice == "All" else choice, ROW_LIMIT)
        tree = self.log_tree
        tree.delete(*tree.get_children())
        if not rows:
            self.log_empty.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.log_empty.place_forget()

        for i, (roll, name, status) in enumerate(rows):
            badge = f"✔  {status}" if status == "Present" else f"✖  {status}"
            tags = (status.lower(),)
            tree.insert("", "end", tags=tags, values=(roll, name, badge))
        self.log_note_var.set(
            f"Showing {len(rows)} of {total} records" if total > len(rows) else f"{total} record(s)"
        )

    def refresh_stats(self):
        s = self.db.day_summary(self._day)
        for key in ("students", "present", "absent", "unmarked"):
            self.stat_vars[key].set(f"{s[key]:,}")
        self.stat_vars["rate"].set(f"{s['rate']:.1f}%")

    def refresh_analytics(self):
        if not hasattr(self, "chart_canvas"):
            return
        self.root.update_idletasks()
        c = self.chart_canvas
        c.delete("all")
        w = max(560, c.winfo_width())
        h = max(220, c.winfo_height())

        trend = self.db.recent_trend(self._day, days=7)
        pad_l, pad_r, pad_t, pad_b = 48, 24, 24, 34
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        for pct_line, col, dash in ((0, BORDER, ()), (50, BORDER, (2, 4)), (75, "#fca5a5", (4, 4)), (100, BORDER, ())):
            y = pad_t + plot_h - (pct_line / 100.0) * plot_h
            c.create_line(pad_l, y, w - pad_r, y, fill=col, dash=dash)
            c.create_text(
                pad_l - 8, y, text=f"{pct_line}%", anchor="e", fill=RED if pct_line == 75 else MUTED, font=(FONT, 8)
            )

        slot_w = plot_w / len(trend)
        bar_w = min(46, slot_w * 0.52)

        for idx, (lbl, present, total, pct) in enumerate(trend):
            cx = pad_l + idx * slot_w + slot_w / 2
            x0, x1 = cx - bar_w / 2, cx + bar_w / 2
            y1 = pad_t + plot_h
            bar_h = (pct / 100.0) * plot_h if total > 0 else 4
            y0 = y1 - bar_h

            fill_col = "#cbd5e1" if total == 0 else (RED if pct < ATTENDANCE_THRESHOLD else PRIMARY)
            c.create_rectangle(x0, y0, x1, y1, fill=fill_col, outline="")

            val_txt = f"{pct:.0f}%" if total > 0 else "—"
            c.create_text(cx, y0 - 8, text=val_txt, fill=TEXT if total > 0 else MUTED, font=(FONT, 8, "bold"))
            c.create_text(cx, y1 + 14, text=lbl, fill=MUTED, font=(FONT, 8))

        summary = self.db.class_summary()
        shortage_cnt = len(self.db.shortage_list(ATTENDANCE_THRESHOLD))
        self.analytics_note.config(
            text=(
                f"Overall Class Attendance: {summary['percent']:.1f}% across {summary['days']} recorded class day(s)   •   "
                f"Students below 75% threshold: {shortage_cnt}   •   Red dashed line indicates 75% minimum eligibility."
            )
        )

    # ----------------------------------------------------------------- events
    def on_student_select(self, _event):
        selection = self.students_tree.selection()
        if selection:
            self.roll_var.set(selection[0])
            self.name_var.set(self.students_tree.item(selection[0], "values")[1])

    def on_student_double_click(self, _event):
        selection = self.students_tree.selection()
        if not selection:
            return
        roll = selection[0]
        ok, res = self._call(self.db.toggle_attendance, roll, self._day)
        if ok:
            r_no, name, new_st, prev_st = res
            self._undo_stack.append(("single", r_no, self._day, prev_st))
            self.refresh_all()
            self.toast(
                f"Toggled {r_no} ({name}) → {new_st} for {self._day.isoformat()}.",
                "success" if new_st == "Present" else "warning",
            )

    def _on_search_change(self, *_):
        if self._search_job:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(250, self.refresh_students)

    def _tick(self):
        now_today = date.today()
        if now_today != self._today_ref:
            if self._day == self._today_ref:
                self._day = now_today
            self._today_ref = now_today
            self._update_date_label()
            self.refresh_all()
        self.root.after(30_000, self._tick)

    def on_close(self):
        self.db.close()
        self.root.destroy()

    # ---------------------------------------------------------------- dialogs
    def show_about_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("About ClassPulse")
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.transient(self.root)

        banner = tk.Frame(win, bg=HEADER_BG, padx=28, pady=18)
        banner.pack(fill="x")
        tk.Label(banner, text="ClassPulse", bg=HEADER_BG, fg="white", font=(FONT, 18, "bold")).pack(anchor="w")
        tk.Label(
            banner, text="Smart Student Attendance & Analytics System  •  v2.0",
            bg=HEADER_BG, fg="#93c5fd", font=(FONT, 9)
        ).pack(anchor="w")

        body = tk.Frame(win, bg=CARD, padx=28, pady=20)
        body.pack(fill="both")

        tk.Label(
            body, text="DEVELOPED BY", bg=CARD, fg=PRIMARY, font=(FONT, 8, "bold")
        ).pack(anchor="w", pady=(0, 8))

        devs = (
            ("Piyush Ojha", "Enrollment No: BTEL26O1083"),
            ("Rahul Tyagi", "Enrollment No: BTEL26O1095"),
        )
        for name, enr in devs:
            card = tk.Frame(body, bg="#f8fafc", highlightbackground=BORDER, highlightthickness=1, padx=14, pady=10)
            card.pack(fill="x", pady=(0, 8))
            tk.Label(card, text=name, bg="#f8fafc", fg=TEXT, font=(FONT, 11, "bold")).pack(anchor="w")
            tk.Label(card, text=enr, bg="#f8fafc", fg=MUTED, font=(FONT, 9)).pack(anchor="w")

        backend_txt = (
            f"Storage Backend: Firebase Realtime Cloud ({self.db.base_url})"
            if self.db.cloud_enabled
            else f"Storage Backend: Local SQLite ({os.path.basename(DB_PATH)})"
        )
        tk.Label(
            body,
            text="Department of Electronics Engineering\nMadhav Institute of Technology & Science (MITS), Gwalior",
            bg=CARD, fg=TEXT, font=(FONT, 9), justify="left"
        ).pack(anchor="w", pady=(8, 6))
        tk.Label(body, text=backend_txt, bg=CARD, fg=MUTED, font=(FONT, 8)).pack(anchor="w")

        ttk.Button(body, text="Close", style="Primary.TButton", cursor="hand2", command=win.destroy).pack(
            pady=(16, 0), anchor="e"
        )

        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        win.focus_set()

    def _report_dialog(self, title, subtitle, rows, percent, caption):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.transient(self.root)
        body = ttk.Frame(win, style="Card.TFrame", padding=24)
        body.pack()
        ttk.Label(body, text=title, style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=subtitle, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        for i, (label, value) in enumerate(rows, start=2):
            ttk.Label(body, text=label, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(body, text=f"{value:,}", style="CardBold.TLabel").grid(
                row=i, column=1, sticky="e", padx=(40, 0), pady=2
            )
        r = 2 + len(rows)
        bar_style = (
            "Red.Horizontal.TProgressbar" if percent < ATTENDANCE_THRESHOLD else "Green.Horizontal.TProgressbar"
        )
        ttk.Progressbar(body, maximum=100, value=percent, length=310, style=bar_style).grid(
            row=r, column=0, columnspan=2, pady=(14, 4)
        )
        status_note = " (Below 75% threshold)" if percent < ATTENDANCE_THRESHOLD else ""
        ttk.Label(body, text=f"{percent:.1f}% {caption}{status_note}", style="CardBold.TLabel").grid(
            row=r + 1, column=0, columnspan=2
        )
        btn_row = ttk.Frame(body, style="Card.TFrame")
        btn_row.grid(row=r + 2, column=0, columnspan=2, pady=(16, 0))
        ttk.Button(btn_row, text="Export Full CSV", style="Tool.TButton", cursor="hand2", command=self.export_csv).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(btn_row, text="Close", style="Primary.TButton", cursor="hand2", command=win.destroy).pack(
            side="left"
        )

        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        win.focus_set()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()