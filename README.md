![LOGO](classpulse.png)

# ClassPulse — Smart Student Attendance & Analytics System

A lightweight, cloud-connected Windows desktop application built with Python (`tkinter`/`ttk`), **Firebase Realtime Database**, and **SQLite** to streamline classroom attendance tracking, automate `<75%` eligibility alerts, and generate real-time visual analytics.

Developed as a B.Tech. Micro Project in the **Department of Electronics Engineering, Madhav Institute of Technology & Science (MITS), Gwalior** (Session 2026–2027).

---

## Key Features

* **Dual-Mode Cloud & Offline Persistence:** Synchronizes live with **Firebase Realtime Database** via REST APIs using a 15-second in-memory snapshot cache for zero UI lag, while automatically falling back to local **SQLite** (`WAL` mode) when offline.
* **Interactive Calendar Date Picker:** Select any current or historical date to view, record, or update attendance logs.
* **Quick Roll-Call Mode:** Sequential keyboard-driven attendance flow (`P` = Present, `A` = Absent, `S` = Skip) alongside single-click row toggling and bulk absent marking.
* **Action Undo Stack (`Ctrl+Z`):** Instantly revert single or bulk attendance changes.
* **Automated `<75%` Shortage Detection:** Highlights students below the 75% attendance threshold in red, filters defaulters in one click, and copies formatted shortage notices to the clipboard.
* **7-Day Visual Analytics:** Native Canvas bar chart displaying daily class attendance trends against the 75% eligibility line.
* **CSV Import/Export & Backups:** Bulk-import student rosters from CSV, export formatted attendance registers, and save JSON or SQLite snapshots.

---

## Project Structure

```text
ClassPulse/
├── attendance_system.py   # Main Tkinter GUI, CalendarPopup, RollCallDialog, & Analytics
├── attendance_db.py       # Dual-mode Firebase RTDB (cached) & SQLite persistence layer
├── classpulse.ico         # Custom application icon (optional)
├── sample_roster.csv      # Sample CSV template (Roll No, Student Name)
└── README.md              # Project documentation
```

---

## Setup & Installation

### 1. Clone the Repository
```bash
git clone [https://github.com/your-username/ClassPulse.git](https://github.com/your-username/ClassPulse.git)
cd ClassPulse
```

### 2. Create a Virtual Environment & Install Dependencies
```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install requests pyinstaller
```

### 3. Configure Firebase Realtime Database (Optional)
ClassPulse runs immediately in **Local Mode** (`classpulse.db`) with zero configuration. To enable **Cloud Synced** mode:
1. Create a **Realtime Database** in the [Firebase Console](https://console.firebase.google.com/) in test mode.
2. Copy your database URL (e.g., `https://your-project-id-default-rtdb.asia-southeast1.firebasedatabase.app`).
3. Open `attendance_db.py` and update `FIREBASE_URL` on line 34:
   ```python
   FIREBASE_URL = "[https://your-project-id-default-rtdb.asia-southeast1.firebasedatabase.app](https://your-project-id-default-rtdb.asia-southeast1.firebasedatabase.app)"
   ```

### 4. Run the Application
```bash
python attendance_system.py
```

---

## Building the Standalone Windows `.exe`

Package ClassPulse into a single-file Windows executable with no Python runtime dependency:

```bash
pyinstaller --onefile --windowed --icon=classpulse.ico --add-data "classpulse.ico;." --name "ClassPulse" attendance_system.py
```

The compiled executable will be generated at `dist/ClassPulse.exe`.

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Enter` | Mark attendance for the entered/selected roll number |
| `Double-Click` | Toggle a student's status (`Present` / `Absent`) for the selected date |
| `P` / `A` / `S` | Mark **Present**, **Absent**, or **Skip** inside Quick Roll-Call mode |
| `Ctrl + Z` | Undo the last single or bulk attendance entry |
| `Ctrl + F` | Focus the live student search bar |
| `Esc` | Clear input fields or close active popups |

---

## Authors

* **Piyush Ojha** — Enrollment No.: `BTEL26O1083`
* **Rahul Tyagi** — Enrollment No.: `BTEL26O1095`

**Department of Electronics Engineering**  
Madhav Institute of Technology & Science (MITS), Gwalior
