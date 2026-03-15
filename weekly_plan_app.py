# weekly_plan_app.py
# 東小松川小学校 週案管理システム 安定版 V5.4 修正版
# 修正点:
# - 時間割表が確実に表示されるよう、教員画面内のインデント崩れを修正
# - 「週案自動生成（提案）」ボタン処理と、時間割表描画処理を分離
# - ボタン押下時のみ自動生成し、通常時は必ず時間割表を表示

import io
import json
import re
import sqlite3
from datetime import date
from typing import Optional, List

import pandas as pd
import streamlit as st

DEFAULT_ADMIN_PASSWORD = "higakoma2025"
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
DEFAULT_SCHOOL_YEAR = "令和8年度"
DEFAULT_WEEKS_PER_YEAR = 35
DB_PATH = "weekly_plans.db"

st.set_page_config(page_title="週案管理システム", layout="wide")

st.markdown(
    '''
    <style>
    html, body, [class*="css"]  { font-size: 16px; }
    div[data-baseweb="select"] {
        font-size: 14px !important;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
        width: 100% !important;
        min-width: 140px !important;
    }
    div[data-baseweb="select"] span {
        font-size: 14px !important;
        white-space: normal !important;
        line-height: 1.3 !important;
    }
    textarea { font-size: 14px !important; }
    .status-label {
        display: inline-block; padding: 2px 8px; border-radius: 999px;
        font-size: 12px; color: white;
    }
    .status-teishutsu { background-color: #f39c12; }
    .status-shonin    { background-color: #27ae60; }
    .status-sashimodoshi { background-color: #c0392b; }
    .status-shitagaki { background-color: #7f8c8d; }
    .tt-cell {
        border: 1px solid #999 !important; border-radius: 6px !important;
        padding: 6px 6px 2px 6px !important; margin: 2px 0 6px 0 !important;
        background: rgba(255,255,255,0.80);
    }
    .tt-rowlabel {
        border: 1px solid #999 !important; border-radius: 6px !important;
        padding: 8px 6px !important; margin: 2px 0 6px 0 !important;
        background: rgba(245,245,245,0.95); font-weight: 700; text-align: center;
    }
    .tt-headcell {
        border: 1px solid #999 !important; border-radius: 6px !important;
        padding: 8px 6px !important; margin: 2px 0 6px 0 !important;
        background: rgba(235,235,235,0.95); font-weight: 800; text-align: center;
    }
    .tt-section {
        font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 999px;
        display: inline-block; margin: 2px 0 4px 0; border: 1px solid #777;
    }
    .tt-event { background: rgba(255,244,204,0.95); }
    .tt-main  { background: rgba(231,240,255,0.95); }
    .tt-mini  { font-size: 12px; opacity: 0.9; }
    .dataframe td, .dataframe th {
        white-space: pre-wrap !important; word-break: break-word !important;
        line-height: 1.35 !important; vertical-align: top !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]{
        border: 1px solid #000 !important; border-radius: 0px !important; box-shadow: none !important;
    }
    @media print {
        header, footer, .stSidebar { display: none !important; }
        .main .block-container { padding-top: 0px !important; padding-bottom: 0px !important; }
        table { width: 100% !important; font-size: 11px !important; border-collapse: collapse !important; }
        th, td { border: 1px solid #000 !important; padding: 4px !important; white-space: pre-wrap !important; }
    }
    </style>
    ''',
    unsafe_allow_html=True,
)

COLUMN_WIDTHS = [0.7] + [1.6] * 6
DAYS = ["月", "火", "水", "木", "金", "土"]
PERIODS = ["1校時", "2校時", "3校時", "4校時", "5校時", "学校裁量", "6校時"]

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()


def normalize_teacher_name(name: str) -> str:
    return str(name or "").strip()


def ensure_settings_table():
    cur.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()


def get_setting(key: str, default: str) -> str:
    ensure_settings_table()
    cur.execute("SELECT value FROM app_settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else default


def set_setting(key: str, value: str):
    ensure_settings_table()
    cur.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_current_school_year() -> str:
    return get_setting("current_school_year", DEFAULT_SCHOOL_YEAR)


def set_current_school_year(year_str: str):
    set_setting("current_school_year", year_str)


def ensure_weekly_plans_table():
    cur.execute('''
        CREATE TABLE IF NOT EXISTS weekly_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_year TEXT, teacher TEXT, grade TEXT, class TEXT,
            teacher_type TEXT, week TEXT, plan_json TEXT, status TEXT,
            submitted_at TEXT, approved_at TEXT, approved_by TEXT
        )
    ''')
    for col in ["school_year", "teacher", "grade", "class", "teacher_type", "week", "plan_json", "status", "submitted_at", "approved_at", "approved_by"]:
        try:
            cur.execute(f"ALTER TABLE weekly_plans ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def ensure_hours_total_table():
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hours_total (
            school_year TEXT, grade TEXT, subject TEXT, consumed REAL,
            PRIMARY KEY(school_year, grade, subject)
        )
    ''')
    for col in ["school_year", "grade", "subject", "consumed"]:
        try:
            ctype = "REAL" if col == "consumed" else "TEXT"
            cur.execute(f"ALTER TABLE hours_total ADD COLUMN {col} {ctype}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def ensure_year_init_table():
    cur.execute('''
        CREATE TABLE IF NOT EXISTS year_init (
            school_year TEXT PRIMARY KEY, initialized_at TEXT, initialized_by TEXT
        )
    ''')
    conn.commit()


def ensure_inquiry_logs_table():
    cur.execute('''
        CREATE TABLE IF NOT EXISTS inquiry_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_year TEXT, week TEXT, grade TEXT, class TEXT, teacher TEXT,
            theme TEXT, goals TEXT, activities TEXT, evidence TEXT, reflection TEXT,
            created_at TEXT
        )
    ''')
    for col in ["school_year", "week", "grade", "class", "teacher", "theme", "goals", "activities", "evidence", "reflection", "created_at"]:
        try:
            cur.execute(f"ALTER TABLE inquiry_logs ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def ensure_autosave_table():
    cur.execute('''
        CREATE TABLE IF NOT EXISTS auto_save_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_year TEXT, teacher TEXT, grade TEXT, class TEXT,
            teacher_type TEXT, week TEXT, plan_json TEXT, meta_json TEXT, saved_at TEXT
        )
    ''')
    for col in ["school_year", "teacher", "grade", "class", "teacher_type", "week", "plan_json", "meta_json", "saved_at"]:
        try:
            cur.execute(f"ALTER TABLE auto_save_sessions ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def ensure_backup_log_table():
    cur.execute('''
        CREATE TABLE IF NOT EXISTS backup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_year TEXT, created_at TEXT, created_by TEXT, filename TEXT
        )
    ''')
    conn.commit()


ensure_weekly_plans_table()
ensure_hours_total_table()
ensure_year_init_table()
ensure_inquiry_logs_table()
ensure_autosave_table()
ensure_backup_log_table()

try:
    cur.execute(
        "UPDATE weekly_plans SET school_year=? WHERE school_year IS NULL OR school_year=''",
        (DEFAULT_SCHOOL_YEAR,),
    )
    cur.execute(
        "UPDATE hours_total SET school_year=? WHERE school_year IS NULL OR school_year=''",
        (DEFAULT_SCHOOL_YEAR,),
    )
    conn.commit()
except Exception:
    pass

STANDARD_HOURS = {
    "1年": {"国語": 306, "算数": 140, "生活": 102, "音楽": 68, "図工": 68, "体育": 102, "道徳": 34, "特活": 34, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "2年": {"国語": 280, "算数": 140, "生活": 102, "音楽": 68, "図工": 68, "体育": 102, "道徳": 35, "特活": 35, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "3年": {"国語": 210, "社会": 70, "算数": 175, "理科": 70, "音楽": 50, "図工": 50, "体育": 105, "道徳": 35, "特活": 35, "外国語活動": 35, "総合的な学習の時間": 70, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "4年": {"国語": 175, "社会": 105, "算数": 175, "理科": 105, "音楽": 50, "図工": 50, "体育": 105, "道徳": 35, "特活": 35, "外国語活動": 35, "総合的な学習の時間": 70, "家庭科": 0, "クラブ": 10, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "5年": {"国語": 175, "社会": 105, "算数": 175, "理科": 105, "音楽": 45, "図工": 45, "家庭科": 70, "体育": 90, "道徳": 35, "特活": 35, "外国語": 70, "総合的な学習の時間": 70, "クラブ": 10, "委員会": 10, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "6年": {"国語": 175, "社会": 105, "算数": 140, "理科": 105, "音楽": 45, "図工": 45, "家庭科": 70, "体育": 90, "道徳": 35, "特活": 35, "外国語": 70, "総合的な学習の時間": 70, "クラブ": 10, "委員会": 10, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
}
ALL_SUBJECTS = sorted({subj for g in STANDARD_HOURS.values() for subj in g.keys()})

PERIOD_MINUTES = {}
for day in DAYS:
    PERIOD_MINUTES[day] = {}
    for period in PERIODS:
        if period == "学校裁量":
            PERIOD_MINUTES[day][period] = 45 if day in ["月", "火", "木", "金"] else 0
        else:
            num = int(period[0])
            PERIOD_MINUTES[day][period] = 40 if num <= 5 else 45

EVENT_FRACTIONS = [("なし", 0.0), ("3/8", 3.0 / 8.0), ("6/8", 6.0 / 8.0), ("8/8（＝1）", 1.0)]


def get_subjects_for_grade(grade: str) -> List[str]:
    return list(STANDARD_HOURS[grade].keys())


def fraction_label_to_value(label: str) -> float:
    for l, v in EVENT_FRACTIONS:
        if l == label:
            return v
    return 0.0


def fraction_value_to_label(v: float) -> str:
    v = float(v or 0.0)
    for l, vv in EVENT_FRACTIONS:
        if abs(v - vv) < 1e-9:
            return l
    return "なし"


def fraction_to_8th(v: float) -> int:
    v = float(v or 0.0)
    return max(0, min(8, int(round(v * 8))))


def convert_to_45(mins: float) -> float:
    return float(mins) / 45.0


def detect_grade_from_class(klass: str) -> Optional[str]:
    if not klass:
        return None
    for ch in str(klass):
        if ch.isdigit():
            g = f"{ch}年"
            return g if g in STANDARD_HOURS else None
    return None


def status_badge(status: str) -> str:
    cls = "status-teishutsu"
    if status == "承認":
        cls = "status-shonin"
    elif status == "差戻":
        cls = "status-sashimodoshi"
    elif status == "下書き":
        cls = "status-shitagaki"
    return f'<span class="status-label {cls}">{status}</span>'


def to_reiwa_short(year_str: str) -> str:
    m = re.search(r"令和\s*([0-9]+)\s*年度", str(year_str))
    return f"R{m.group(1)}" if m else str(year_str).replace("年度", "")


def safe_year_str(s: str) -> str:
    return str(s).replace(" ", "").replace("/", "_").replace("\\", "_")


def empty_cell() -> dict:
    return {
        "class": "",
        "event": {"fraction": 0.0, "content": ""},
        "main": {"subject": "（空欄）", "content": ""}
    }


def normalize_timetable(tt):
    out = {}
    src = tt if isinstance(tt, dict) else {}
    for day in DAYS:
        out.setdefault(day, {})
        day_src = src.get(day, {}) if isinstance(src.get(day, {}), dict) else {}
        for period in PERIODS:
            cell = day_src.get(period)
            if not isinstance(cell, dict):
                out[day][period] = empty_cell()
                continue
            event = cell.get("event") if isinstance(cell.get("event"), dict) else {}
            main = cell.get("main") if isinstance(cell.get("main"), dict) else {}
            legacy_subject = cell.get("subject", "")
            legacy_content = cell.get("content", "")
            out[day][period] = {
                "class": cell.get("class", "") or "",
                "event": {
                    "fraction": float(event.get("fraction", 0.0) or 0.0),
                    "content": event.get("content", "") or ""
                },
                "main": {
                    "subject": (main.get("subject", "") or legacy_subject or "（空欄）"),
                    "content": (main.get("content", "") or legacy_content or "")
                },
            }
    return out


def apply_timetable_to_widget_state(timetable: dict, teacher_type: str, class_name: str):
    tt = normalize_timetable(timetable)
    for day in DAYS:
        for period in PERIODS:
            cell = tt.get(day, {}).get(period, empty_cell())
            event = cell.get("event") or {}
            main = cell.get("main") or {}

            st.session_state[f"{day}_{period}_eventfrac"] = fraction_value_to_label(
                float(event.get("fraction", 0.0) or 0.0)
            )
            st.session_state[f"{day}_{period}_eventcont"] = event.get("content", "") or ""
            st.session_state[f"{day}_{period}_mainsubj"] = main.get("subject", "（空欄）") or "（空欄）"
            st.session_state[f"{day}_{period}_maincont"] = main.get("content", "") or ""

            if teacher_type.startswith("専科"):
                klass = cell.get("class", "") or ""
                st.session_state[f"{day}_{period}_class"] = klass if klass else "（未選択）"


def cell_to_segments(cell: dict, slot_minutes: float):
    if not cell or slot_minutes <= 0:
        return []
    klass = cell.get("class", "")
    segs = []
    event = cell.get("event") or {}
    frac = max(0.0, min(1.0, float(event.get("fraction", 0.0) or 0.0)))
    event_minutes = slot_minutes * frac
    remain_minutes = slot_minutes - event_minutes

    if event_minutes > 0:
        segs.append({
            "class": klass,
            "subject": "学校行事",
            "content": (event.get("content") or "").strip(),
            "minutes": event_minutes,
            "event_fraction": frac
        })

    main = cell.get("main") or {}
    main_subj = (main.get("subject") or "").strip()
    main_cont = (main.get("content") or "").strip()
    if remain_minutes > 0 and (main_subj and main_subj != "（空欄）"):
        segs.append({
            "class": klass,
            "subject": main_subj,
            "content": main_cont,
            "minutes": remain_minutes,
            "event_fraction": 0.0
        })

    if frac == 0.0 and not segs:
        subj = (cell.get("subject") or "").strip()
        cont = (cell.get("content") or "").strip()
        if subj and subj != "（空欄）":
            segs.append({
                "class": klass,
                "subject": subj,
                "content": cont,
                "minutes": slot_minutes,
                "event_fraction": 0.0
            })
    return segs


def compute_week_subject_minutes(timetable: dict, base_grade: str):
    result = {}
    for day in DAYS:
        for period in PERIODS:
            slot_minutes = PERIOD_MINUTES.get(day, {}).get(period, 0)
            if slot_minutes <= 0:
                continue
            cell = (timetable or {}).get(day, {}).get(period)
            if not cell:
                continue
            segs = cell_to_segments(cell, slot_minutes)
            for seg in segs:
                subject = seg.get("subject", "")
                klass = seg.get("class", "")
                mins = float(seg.get("minutes", 0) or 0)
                grade_for_slot = detect_grade_from_class(klass) or base_grade
                if grade_for_slot not in STANDARD_HOURS:
                    continue
                if subject not in STANDARD_HOURS[grade_for_slot]:
                    continue
                result.setdefault(grade_for_slot, {})
                result[grade_for_slot][subject] = result[grade_for_slot].get(subject, 0) + mins
    return result


def build_print_df(timetable: dict) -> pd.DataFrame:
    rows, index = [], []
    for period in PERIODS:
        if not any(PERIOD_MINUTES[day][period] > 0 for day in DAYS):
            continue
        row = []
        for day in DAYS:
            slot_minutes = PERIOD_MINUTES[day][period]
            if slot_minutes <= 0:
                row.append("")
                continue
            cell = (timetable or {}).get(day, {}).get(period, {}) or {}
            segs = cell_to_segments(cell, slot_minutes)
            parts = []
            for seg in segs:
                klass = (seg.get("class") or "").strip()
                subj = (seg.get("subject") or "").strip()
                cont = (seg.get("content") or "").strip()
                mins = float(seg.get("minutes") or 0)
                head = f"[{int(round(mins))}分]"
                if klass:
                    head += f" {klass}"
                if subj:
                    head += f" {subj}"
                parts.append(head + (("\n" + cont) if cont else ""))
            row.append("\n\n".join(parts).strip())
        rows.append(row)
        index.append(period)
    return pd.DataFrame(rows, index=index, columns=DAYS) if rows else pd.DataFrame()


def validate_timetable_for_submit(tt: dict):
    errors = []
    for day in DAYS:
        for period in PERIODS:
            slot_minutes = PERIOD_MINUTES.get(day, {}).get(period, 0)
            if slot_minutes <= 0:
                continue
            cell = (tt or {}).get(day, {}).get(period)
            if not cell:
                continue
            event = cell.get("event") or {}
            frac = max(0.0, min(1.0, float(event.get("fraction", 0.0) or 0.0)))
            if 0.0 < frac < 1.0:
                main = cell.get("main") or {}
                subj = (main.get("subject") or "").strip()
                e8 = fraction_to_8th(frac)
                r8 = 8 - e8
                if not subj or subj == "（空欄）":
                    errors.append(f"{day} {period}: 学校行事が {e8}/8 のため、残り {r8}/8（{int(round(slot_minutes * (1 - frac)))}分）の教科等が必要です。")
    return errors


def swap_cells_in_timetable(tt: dict, day_a: str, period_a: str, day_b: str, period_b: str):
    tt = normalize_timetable(tt)
    cell_a = tt[day_a][period_a]
    cell_b = tt[day_b][period_b]
    tt[day_a][period_a] = cell_b
    tt[day_b][period_b] = cell_a
    return tt


def add_hours(school_year: str, grade: str, subject: str, minutes: float):
    add_45 = convert_to_45(minutes)
    cur.execute("SELECT consumed FROM hours_total WHERE school_year=? AND grade=? AND subject=?", (school_year, grade, subject))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE hours_total SET consumed=? WHERE school_year=? AND grade=? AND subject=?", (float(row[0]) + add_45, school_year, grade, subject))
    else:
        cur.execute("INSERT INTO hours_total (school_year, grade, subject, consumed) VALUES (?, ?, ?, ?)", (school_year, grade, subject, add_45))
    conn.commit()


def is_year_initialized(school_year: str) -> bool:
    cur.execute("SELECT 1 FROM year_init WHERE school_year=? LIMIT 1", (school_year,))
    return cur.fetchone() is not None


def init_year_hours_zero(school_year: str, initialized_by: str = "管理職"):
    for g in STANDARD_HOURS.keys():
        for s in get_subjects_for_grade(g):
            cur.execute("INSERT OR IGNORE INTO hours_total (school_year, grade, subject, consumed) VALUES (?, ?, ?, 0.0)", (school_year, g, s))
    cur.execute("INSERT OR REPLACE INTO year_init (school_year, initialized_at, initialized_by) VALUES (?, DATETIME('now'), ?)", (school_year, initialized_by))
    conn.commit()


def fetch_hours_total_for_year(school_year: str):
    cur.execute("SELECT school_year, grade, subject, consumed FROM hours_total WHERE school_year=?", (school_year,))
    return cur.fetchall()


def build_hours_progress_df(school_year: str):
    hours_rows = fetch_hours_total_for_year(school_year)
    consumed_map = {(g, s): float(c) for (_sy, g, s, c) in hours_rows}
    out = []
    for gg in STANDARD_HOURS.keys():
        for ss in get_subjects_for_grade(gg):
            std = float(STANDARD_HOURS[gg][ss])
            used = float(consumed_map.get((gg, ss), 0.0))
            remain = std - used
            pct = (used / std * 100.0) if std > 0 else 0.0
            out.append({"年度": school_year, "学年": gg, "教科等": ss, "標準(45分コマ)": round(std, 2), "実施累積(45分コマ)": round(used, 2), "残り(45分コマ)": round(remain, 2), "進捗(%)": round(pct, 1)})
    return pd.DataFrame(out)


def hours_warning_messages(school_year: str):
    df = build_hours_progress_df(school_year)
    msgs = []
    for _, r in df.iterrows():
        remain = float(r["残り(45分コマ)"])
        if remain > 20:
            msgs.append(f"{r['学年']} {r['教科等']}：不足 {round(remain, 1)} コマ")
        if remain < -5:
            msgs.append(f"{r['学年']} {r['教科等']}：超過 {round(abs(remain), 1)} コマ")
    return msgs


def get_weeks_elapsed(school_year: str, grade: str) -> int:
    cur.execute("SELECT COUNT(DISTINCT week) FROM weekly_plans WHERE school_year=? AND grade=? AND status='承認'", (school_year, grade))
    row = cur.fetchone()
    return int(row[0] or 0)


def build_optimization_suggestions(school_year: str) -> pd.DataFrame:
    df = build_hours_progress_df(school_year)
    rows = []
    for gg in STANDARD_HOURS.keys():
        elapsed = get_weeks_elapsed(school_year, gg)
        remaining_weeks = max(1, DEFAULT_WEEKS_PER_YEAR - elapsed)
        sub = df[df["学年"] == gg]
        for _, r in sub.iterrows():
            remain = float(r["残り(45分コマ)"])
            rows.append({"年度": school_year, "学年": gg, "教科等": r["教科等"], "残り(45分コマ)": round(remain, 2), "残り週(概算)": remaining_weeks, "今後の必要/週(45分コマ)": round(remain / remaining_weeks, 2)})
    return pd.DataFrame(rows)


def teacher_where_clause(column="teacher"):
    return f"TRIM(COALESCE({column},'')) = ?"


def upsert_draft(school_year: str, teacher: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    teacher = normalize_teacher_name(teacher)
    cur.execute(
        f"SELECT id FROM weekly_plans WHERE school_year=? AND {teacher_where_clause()} AND week=? AND status='下書き' ORDER BY id DESC LIMIT 1",
        (school_year, teacher, week_str)
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE weekly_plans SET teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, submitted_at=DATETIME('now') WHERE id=?",
            (teacher, base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), row[0])
        )
    else:
        cur.execute(
            "INSERT INTO weekly_plans (school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, '下書き', DATETIME('now'))",
            (school_year, teacher, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False))
        )
    conn.commit()


def list_my_drafts(school_year: str, teacher: str):
    teacher = normalize_teacher_name(teacher)
    cur.execute(
        f"SELECT id, week, grade, class, teacher_type, plan_json, submitted_at FROM weekly_plans WHERE school_year=? AND {teacher_where_clause()} AND status='下書き' ORDER BY week DESC, id DESC",
        (school_year, teacher)
    )
    return cur.fetchall()


def load_plan_by_id(wid: int):
    cur.execute("SELECT id, school_year, teacher, grade, class, teacher_type, week, plan_json, status FROM weekly_plans WHERE id=?", (wid,))
    return cur.fetchone()


def fetch_latest_plan_before_week(school_year: str, teacher: str, week_str: str):
    teacher = normalize_teacher_name(teacher)
    cur.execute(
        f"SELECT plan_json, week, status FROM weekly_plans WHERE school_year=? AND {teacher_where_clause()} AND week < ? AND status IN ('提出','承認','差戻','下書き') ORDER BY week DESC, id DESC LIMIT 1",
        (school_year, teacher, week_str)
    )
    return cur.fetchone()


def submit_plan_from_current(school_year: str, teacher: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    teacher = normalize_teacher_name(teacher)
    cur.execute(
        f"SELECT id FROM weekly_plans WHERE school_year=? AND {teacher_where_clause()} AND week=? AND status='下書き' ORDER BY id DESC LIMIT 1",
        (school_year, teacher, week_str)
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE weekly_plans SET teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, status='提出', submitted_at=DATETIME('now') WHERE id=?",
            (teacher, base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), row[0])
        )
    else:
        cur.execute(
            "INSERT INTO weekly_plans (school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, '提出', DATETIME('now'))",
            (school_year, teacher, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False))
        )
    conn.commit()


def upsert_autosave(school_year: str, teacher: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    teacher = normalize_teacher_name(teacher)
    cur.execute(
        f"SELECT id FROM auto_save_sessions WHERE school_year=? AND {teacher_where_clause()} AND week=? ORDER BY id DESC LIMIT 1",
        (school_year, teacher, week_str)
    )
    row = cur.fetchone()
    meta = {"school_year": school_year, "teacher": teacher, "grade": base_grade, "class": class_name, "teacher_type": teacher_type, "week": week_str}
    if row:
        cur.execute(
            "UPDATE auto_save_sessions SET teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, meta_json=?, saved_at=DATETIME('now') WHERE id=?",
            (teacher, base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), json.dumps(meta, ensure_ascii=False), row[0])
        )
    else:
        cur.execute(
            "INSERT INTO auto_save_sessions (school_year, teacher, grade, class, teacher_type, week, plan_json, meta_json, saved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, DATETIME('now'))",
            (school_year, teacher, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False), json.dumps(meta, ensure_ascii=False))
        )
    conn.commit()


def list_autosaves(school_year: str, teacher: str):
    teacher = normalize_teacher_name(teacher)
    cur.execute(
        f"SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE school_year=? AND {teacher_where_clause()} ORDER BY saved_at DESC, id DESC",
        (school_year, teacher)
    )
    return cur.fetchall()


def fetch_latest_autosave(school_year: str, teacher: str):
    teacher = normalize_teacher_name(teacher)
    cur.execute(
        f"SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE school_year=? AND {teacher_where_clause()} ORDER BY saved_at DESC, id DESC LIMIT 1",
        (school_year, teacher)
    )
    return cur.fetchone()


def load_autosave_by_id(sid: int):
    cur.execute("SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE id=?", (sid,))
    return cur.fetchone()


def add_inquiry_log(school_year: str, week: str, grade: str, class_name: str, teacher: str, theme: str, goals: str, activities: str, evidence: str, reflection: str):
    teacher = normalize_teacher_name(teacher)
    cur.execute(
        "INSERT INTO inquiry_logs (school_year, week, grade, class, teacher, theme, goals, activities, evidence, reflection, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATETIME('now'))",
        (school_year, week, grade, class_name, teacher, theme, goals, activities, evidence, reflection)
    )
    conn.commit()


def fetch_inquiry_logs(school_year: str, grade: str = None, class_name: str = None, teacher: str = None):
    q = "SELECT id, school_year, week, grade, class, teacher, theme, goals, activities, evidence, reflection, created_at FROM inquiry_logs WHERE school_year=?"
    args = [school_year]
    if grade and grade != "すべて":
        q += " AND grade=?"
        args.append(grade)
    if class_name and class_name.strip():
        q += " AND class=?"
        args.append(class_name.strip())
    if teacher and teacher.strip():
        q += " AND TRIM(COALESCE(teacher,''))=?"
        args.append(normalize_teacher_name(teacher))
    q += " ORDER BY created_at DESC, id DESC"
    cur.execute(q, tuple(args))
    return cur.fetchall()


def aggregate_events_from_plans(plans_rows) -> pd.DataFrame:
    out = []
    for (wid, sy, teacher, grade, class_name, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by) in plans_rows:
        try:
            plan = json.loads(plan_json) if plan_json else {}
        except Exception:
            plan = {}
        timetable = plan.get("timetable", {}) if isinstance(plan, dict) else {}
        week_mins = compute_week_subject_minutes(timetable, grade)
        for gg, mp in week_mins.items():
            ev = float(mp.get("学校行事", 0.0))
            if ev > 0:
                out.append({"年度": sy, "週": week, "学年": gg, "教員": teacher, "状態": status, "学校行事(分)": int(round(ev)), "学校行事(45分コマ)": round(convert_to_45(ev), 2)})
    return pd.DataFrame(out)


def suggest_subject_sequence_for_grade(school_year: str, grade: str):
    df = build_optimization_suggestions(school_year)
    gdf = df[df["学年"] == grade].copy()
    if gdf.empty:
        return []
    gdf = gdf[gdf["教科等"] != "学校行事"].sort_values(by="今後の必要/週(45分コマ)", ascending=False)
    seq = list(gdf["教科等"].values)
    return seq if seq else [s for s in get_subjects_for_grade(grade) if s != "学校行事"]


def auto_fill_timetable_proposal(school_year: str, teacher_type: str, base_grade: str, class_name: str, class_candidates: list, timetable: dict):
    tt = normalize_timetable(timetable)
    seq = suggest_subject_sequence_for_grade(school_year, base_grade)
    if not seq:
        return tt
    idx = 0
    for period in PERIODS:
        for day in DAYS:
            mins = PERIOD_MINUTES.get(day, {}).get(period, 0)
            if mins <= 0:
                continue
            cell = tt[day][period]
            main = cell.get("main") or {}
            if (main.get("subject") or "").strip() not in ("", "（空欄）"):
                continue
            frac = max(0.0, min(1.0, float((cell.get("event") or {}).get("fraction", 0.0) or 0.0)))
            remain = mins - mins * frac
            if remain <= 0:
                continue
            subj = seq[idx % len(seq)]
            idx += 1
            klass = class_name or ""
            if teacher_type.startswith("専科") and class_candidates:
                klass = class_candidates[idx % len(class_candidates)]
            tt[day][period] = {
                "class": klass,
                "event": {"fraction": frac, "content": ((cell.get("event") or {}).get("content") or "")},
                "main": {"subject": subj, "content": "（提案）単元名／ねらい／評価観点を入力"}
            }
    return tt


if "manager_authenticated" not in st.session_state:
    st.session_state["manager_authenticated"] = False


def require_manager_login():
    if st.session_state["manager_authenticated"]:
        return
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔐 管理職ログイン")
    pw = st.sidebar.text_input("管理職用パスワード", type="password", key="admin_pw")
    if st.sidebar.button("ログイン", key="admin_login_btn"):
        if pw == ADMIN_PASSWORD:
            st.session_state["manager_authenticated"] = True
            st.sidebar.success("管理職としてログインしました。")
        else:
            st.sidebar.error("パスワードが違います")
    if not st.session_state["manager_authenticated"]:
        st.warning("管理職専用画面です。サイドバーからパスワードを入力してください。")
        st.stop()


st.title("小学校 週の指導計画（週案）管理システム（クラウド版）")
role = st.sidebar.selectbox("利用者区分", ["教員", "管理職"], key="role_select")
current_school_year = get_current_school_year()
st.sidebar.markdown("---")
st.sidebar.write(f"📅 現在の年度：**{current_school_year}**")

# 教員画面
if role == "教員":
    st.header("📘 週案の作成・提出（教員用）")
    st.caption(f"提出先年度：{current_school_year}（管理職が設定）")

    st.session_state.setdefault("teacher_name", "")
    st.session_state.setdefault("teacher_type", "担任")
    st.session_state.setdefault("base_grade", "3年")
    st.session_state.setdefault("class_name", "")
    st.session_state.setdefault("week_date", date.today())
    st.session_state.setdefault("restore_notice", False)
    st.session_state.setdefault("restore_plan", {"timetable": normalize_timetable({})})

    teacher = st.text_input("教員名", value=st.session_state.get("teacher_name", ""), key="teacher_name_input")
    if teacher is not None:
        st.session_state["teacher_name"] = teacher

    teacher_key = normalize_teacher_name(teacher)

    st.markdown("---")
    st.subheader("🗂 下書き一覧（復元）")
    if teacher_key:
        drafts = list_my_drafts(current_school_year, teacher_key)
        if drafts:
            options, id_map = [], {}
            for (wid, w, g, c, ttype, _pj, subat) in drafts:
                label = f"ID:{wid} / 週:{w} / {g} {c or ''} / {ttype} / 保存:{subat}"
                options.append(label)
                id_map[label] = wid
            sel = st.selectbox("自分の下書きを選択して復元", ["（選択しない）"] + options, key="draft_pick")
            if sel != "（選択しない）" and st.button("📥 この下書きを復元する", key="draft_restore_btn"):
                row = load_plan_by_id(id_map[sel])
                if row:
                    _id, _sy, _t, _g, _c, _tt, _wk, _pj, _stt = row
                    try:
                        plan = json.loads(_pj) if _pj else {}
                    except Exception:
                        plan = {}
                    restored_tt = normalize_timetable(plan.get("timetable", {}))
                    restored_teacher_type = _tt if _tt in ["担任", "専科（音楽・家庭科など）"] else "担任"
                    restored_class = _c or ""

                    st.session_state["restore_plan"] = {"timetable": restored_tt}
                    st.session_state["teacher_type"] = restored_teacher_type
                    st.session_state["base_grade"] = _g if _g in STANDARD_HOURS else st.session_state["base_grade"]
                    st.session_state["class_name"] = restored_class
                    try:
                        st.session_state["week_date"] = date.fromisoformat(_wk)
                    except Exception:
                        pass

                    apply_timetable_to_widget_state(restored_tt, restored_teacher_type, restored_class)

                    st.session_state["restore_notice"] = True
                    st.success("下書きを復元しました。")
                    st.rerun()
        else:
            st.caption("下書きはまだありません。")
    else:
        st.caption("※ 教員名を入力すると下書き一覧が表示されます。")

    st.markdown("---")
    st.subheader("🛟 前回の続きから再開 / 自動保存")
    if teacher_key:
        latest_auto = fetch_latest_autosave(current_school_year, teacher_key)
        autosaves = list_autosaves(current_school_year, teacher_key)

        col_as1, col_as2 = st.columns([2, 3])
        with col_as1:
            if st.button("⏯ 前回の続きから再開する", key="resume_latest_btn"):
                if latest_auto:
                    _sid, _wk, _g, _c, _tt, _saved_at, _plan_json, _meta_json = latest_auto
                    try:
                        plan = json.loads(_plan_json) if _plan_json else {}
                    except Exception:
                        plan = {}

                    restored_tt = normalize_timetable(plan.get("timetable", {}))
                    restored_teacher_type = _tt if _tt in ["担任", "専科（音楽・家庭科など）"] else "担任"
                    restored_class = _c or ""

                    st.session_state["restore_plan"] = {"timetable": restored_tt}
                    st.session_state["teacher_type"] = restored_teacher_type
                    st.session_state["base_grade"] = _g if _g in STANDARD_HOURS else st.session_state["base_grade"]
                    st.session_state["class_name"] = restored_class
                    try:
                        st.session_state["week_date"] = date.fromisoformat(_wk)
                    except Exception:
                        pass

                    apply_timetable_to_widget_state(restored_tt, restored_teacher_type, restored_class)

                    st.session_state["restore_notice"] = True
                    st.success("前回の自動保存から再開しました。")
                    st.rerun()
                else:
                    st.info("再開できる自動保存データがありません。")
        with col_as2:
            if latest_auto:
                st.caption(f"最新の自動保存: {latest_auto[5]} / 週: {latest_auto[1]} / {latest_auto[2]} {latest_auto[3] or ''}")
            else:
                st.caption("自動保存データはまだありません。")
            st.caption(f"自動保存件数: {len(autosaves)} 件")

        if autosaves:
            options, id_map = [], {}
            for sid, w, g, c, ttype, saved_at, _plan_json, _meta_json in autosaves:
                label = f"ID:{sid} / 保存:{saved_at} / 週:{w} / {g} {c or ''} / {ttype}"
                options.append(label)
                id_map[label] = sid
            sel_auto = st.selectbox("自動保存データ一覧から復元", ["（選択しない）"] + options, key="autosave_pick")
            if sel_auto != "（選択しない）" and st.button("📂 この自動保存を復元", key="autosave_restore_btn"):
                row = load_autosave_by_id(id_map[sel_auto])
                if row:
                    _sid, _wk, _g, _c, _tt, _saved_at, _plan_json, _meta_json = row
                    try:
                        plan = json.loads(_plan_json) if _plan_json else {}
                    except Exception:
                        plan = {}

                    restored_tt = normalize_timetable(plan.get("timetable", {}))
                    restored_teacher_type = _tt if _tt in ["担任", "専科（音楽・家庭科など）"] else "担任"
                    restored_class = _c or ""

                    st.session_state["restore_plan"] = {"timetable": restored_tt}
                    st.session_state["teacher_type"] = restored_teacher_type
                    st.session_state["base_grade"] = _g if _g in STANDARD_HOURS else st.session_state["base_grade"]
                    st.session_state["class_name"] = restored_class
                    try:
                        st.session_state["week_date"] = date.fromisoformat(_wk)
                    except Exception:
                        pass

                    apply_timetable_to_widget_state(restored_tt, restored_teacher_type, restored_class)

                    st.session_state["restore_notice"] = True
                    st.success("自動保存データを復元しました。")
                    st.rerun()
        else:
            st.caption("自動保存データ一覧はまだありません。")
    else:
        st.caption("※ 教員名を入力すると、自動保存の再開機能が使えます。")

    if st.session_state.get("restore_notice"):
        st.info("復元しました（勤務形態／基準学年／週／学級／表の中身を反映）。")
        st.session_state["restore_notice"] = False

    teacher_type = st.radio(
        "勤務形態",
        ["担任", "専科（音楽・家庭科など）"],
        index=0 if st.session_state["teacher_type"] == "担任" else 1,
        key="teacher_type_radio"
    )
    st.session_state["teacher_type"] = teacher_type

    grade_keys = list(STANDARD_HOURS.keys())
    base_grade = st.selectbox(
        "基準学年",
        grade_keys,
        index=grade_keys.index(st.session_state["base_grade"]) if st.session_state["base_grade"] in grade_keys else 0,
        key="base_grade_select"
    )
    st.session_state["base_grade"] = base_grade

    class_name = st.text_input(
        "自分の担任学級（例：3-1）※担任でなければ空欄可",
        value=st.session_state.get("class_name", ""),
        key="class_name_input"
    )
    st.session_state["class_name"] = class_name

    week = st.date_input("対象週（週の初日：月曜日など）", value=st.session_state.get("week_date", date.today()), key="week_date_input")
    st.session_state["week_date"] = week
    week_str = str(week)

    if teacher_type == "担任":
        subject_options = ["（空欄）"] + get_subjects_for_grade(base_grade)
        st.caption("※ 担任は、その学年で扱う教科のみ選択できます。")
        class_candidates = [class_name] if class_name else []
    else:
        subject_options = ["（空欄）"] + ALL_SUBJECTS
        st.caption("※ 専科は、各コマで学級・教科を自由に選択できます。")
        st.info("この週に指導する学級をカンマ区切りで入力してください。（例：3-1,3-2,4-1）")
        classes_input = st.text_input("指導学級一覧", value=class_name, key="classes_input")
        class_candidates = [c.strip() for c in classes_input.split(",") if c.strip()]
        if class_candidates:
            st.caption("この週に指導する学級：" + "、".join(class_candidates))
        else:
            st.caption("※ 学級が未入力の場合、学級欄は空欄のままとなります。")

    st.markdown("---")
    st.subheader("⭐ 前週コピー")
    if st.button("⬅ 前週の週案をコピーする", key="copy_prev_week"):
        if not teacher_key:
            st.error("教員名を入力してください。")
        else:
            row = fetch_latest_plan_before_week(current_school_year, teacher_key, week_str)
            if not row:
                st.warning("前週データが見つかりませんでした。")
            else:
                plan_json, prev_week, prev_status = row
                try:
                    prev_plan = json.loads(plan_json) if plan_json else {}
                except Exception:
                    prev_plan = {}

                restored_tt = normalize_timetable(prev_plan.get("timetable", {}))
                st.session_state["restore_plan"] = {"timetable": restored_tt}
                apply_timetable_to_widget_state(restored_tt, teacher_type, class_name)

                st.success(f"前週（{prev_week}）をコピーしました。")
                st.rerun()

    st.subheader("⭐ 週案自動生成（提案）")
    st.caption("※外部AIは使いません。年間時数の残り状況から、空欄コマに教科を提案して埋めます（既存入力は保持）。")

    if st.button("🤖 空欄コマに教科を提案して自動入力", key="auto_fill_btn"):
        restore_plan = st.session_state.get("restore_plan") or {"timetable": normalize_timetable({})}
        tt = normalize_timetable(restore_plan.get("timetable", {}))

        tt = auto_fill_timetable_proposal(
            current_school_year,
            teacher_type,
            base_grade,
            class_name,
            class_candidates,
            tt
        )

        st.session_state["restore_plan"] = {"timetable": tt}
        apply_timetable_to_widget_state(tt, teacher_type, class_name)

        st.success("空欄コマへ教科提案を反映しました。")
        st.rerun()

    timetable = normalize_timetable((st.session_state.get("restore_plan") or {"timetable": normalize_timetable({})}).get("timetable", {}))

    st.markdown("---")
    st.subheader("⭐ 授業入替")
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        day_from = st.selectbox("曜日（元）", DAYS, key="swap_day_from")
        period_from = st.selectbox("校時（元）", PERIODS, key="swap_period_from")
    with c2:
        day_to = st.selectbox("曜日（先）", DAYS, key="swap_day_to")
        period_to = st.selectbox("校時（先）", PERIODS, key="swap_period_to")
    with c3:
        if st.button("🔄 入替する", key="swap_btn"):
            timetable = swap_cells_in_timetable(timetable, day_from, period_from, day_to, period_to)
            st.session_state["restore_plan"] = {"timetable": timetable}
            apply_timetable_to_widget_state(timetable, teacher_type, class_name)
            st.success("入替しました。")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    st.caption("行：校時／列：曜日。各マスで『学校行事(3/8等)＋残り教科』『内容』を入力します。")

    header_cols = st.columns(COLUMN_WIDTHS)
    header_cols[0].markdown('<div class="tt-headcell">　</div>', unsafe_allow_html=True)
    for i, day in enumerate(DAYS, start=1):
        header_cols[i].markdown(f'<div class="tt-headcell">{day}</div>', unsafe_allow_html=True)

    for period in PERIODS:
        if not any(PERIOD_MINUTES[day][period] > 0 for day in DAYS):
            continue
        row_cols = st.columns(COLUMN_WIDTHS)
        row_cols[0].markdown(f'<div class="tt-rowlabel">{period}</div>', unsafe_allow_html=True)

        for j, day in enumerate(DAYS, start=1):
            minutes = PERIOD_MINUTES[day][period]
            with row_cols[j]:
                with st.container(border=True):
                    st.markdown('<div class="tt-cell">', unsafe_allow_html=True)

                    if minutes <= 0:
                        st.write("―")
                        timetable[day][period] = empty_cell()
                        st.markdown("</div>", unsafe_allow_html=True)
                        continue

                    st.caption(f"{minutes}分")

                    default_cell = timetable.get(day, {}).get(period, empty_cell())

                    default_class = (default_cell.get("class") or "").strip()
                    default_event = default_cell.get("event") or {}
                    default_main = default_cell.get("main") or {}

                    default_event_frac_label = fraction_value_to_label(float(default_event.get("fraction", 0.0) or 0.0))
                    default_event_content = (default_event.get("content") or "").strip()
                    default_main_subject = (default_main.get("subject") or "（空欄）").strip()
                    default_main_content = (default_main.get("content") or "").strip()

                    if f"{day}_{period}_eventfrac" not in st.session_state:
                        st.session_state[f"{day}_{period}_eventfrac"] = default_event_frac_label
                    if f"{day}_{period}_eventcont" not in st.session_state:
                        st.session_state[f"{day}_{period}_eventcont"] = default_event_content
                    if f"{day}_{period}_mainsubj" not in st.session_state:
                        st.session_state[f"{day}_{period}_mainsubj"] = default_main_subject
                    if f"{day}_{period}_maincont" not in st.session_state:
                        st.session_state[f"{day}_{period}_maincont"] = default_main_content
                    if teacher_type.startswith("専科") and f"{day}_{period}_class" not in st.session_state:
                        st.session_state[f"{day}_{period}_class"] = default_class if default_class else "（未選択）"

                    if teacher_type.startswith("専科"):
                        if class_candidates:
                            opts = ["（未選択）"] + class_candidates
                            current_class_value = st.session_state.get(f"{day}_{period}_class", "（未選択）")
                            if current_class_value not in opts:
                                current_class_value = "（未選択）"
                                st.session_state[f"{day}_{period}_class"] = current_class_value

                            klass_selected = st.selectbox(
                                "学級",
                                opts,
                                index=opts.index(current_class_value),
                                key=f"{day}_{period}_class",
                                label_visibility="collapsed"
                            )
                            klass = "" if klass_selected == "（未選択）" else klass_selected
                        else:
                            klass = ""
                    else:
                        klass = class_name

                    event_opts = [x[0] for x in EVENT_FRACTIONS]
                    current_event_label = st.session_state.get(f"{day}_{period}_eventfrac", "なし")
                    if current_event_label not in event_opts:
                        current_event_label = "なし"
                        st.session_state[f"{day}_{period}_eventfrac"] = current_event_label

                    st.markdown('<div class="tt-section tt-event">🟨 学校行事（配分）</div>', unsafe_allow_html=True)
                    event_label = st.selectbox(
                        "学校行事（配分）",
                        event_opts,
                        index=event_opts.index(current_event_label),
                        key=f"{day}_{period}_eventfrac",
                        label_visibility="collapsed"
                    )
                    st.markdown('<div class="tt-mini">※ 3/8・6/8・8/8 を選択できます。</div>', unsafe_allow_html=True)

                    event_frac = fraction_label_to_value(event_label)
                    event_minutes = minutes * event_frac
                    remain_minutes = minutes - event_minutes

                    event_content = ""
                    if event_frac > 0:
                        st.markdown('<div class="tt-section tt-event">🟨 学校行事（内容）</div>', unsafe_allow_html=True)
                        event_content = st.text_area(
                            "学校行事 内容",
                            value=st.session_state.get(f"{day}_{period}_eventcont", ""),
                            key=f"{day}_{period}_eventcont",
                            height=45,
                            label_visibility="collapsed"
                        )

                    main_subject = "（空欄）"
                    main_content = ""
                    if remain_minutes > 0:
                        current_main_subject = st.session_state.get(f"{day}_{period}_mainsubj", "（空欄）")
                        if current_main_subject not in subject_options:
                            current_main_subject = "（空欄）"
                            st.session_state[f"{day}_{period}_mainsubj"] = current_main_subject

                        st.markdown('<div class="tt-section tt-main">🟦 残り教科等</div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="tt-mini">残り：{int(round(remain_minutes))}分</div>', unsafe_allow_html=True)

                        main_subject = st.selectbox(
                            "残り枠の教科等",
                            subject_options,
                            index=subject_options.index(current_main_subject),
                            key=f"{day}_{period}_mainsubj",
                            label_visibility="collapsed"
                        )
                        main_content = st.text_area(
                            "残り枠の内容",
                            value=st.session_state.get(f"{day}_{period}_maincont", ""),
                            key=f"{day}_{period}_maincont",
                            height=55,
                            label_visibility="collapsed"
                        )

                    timetable[day][period] = {
                        "class": klass,
                        "event": {"fraction": event_frac, "content": event_content},
                        "main": {"subject": main_subject, "content": main_content}
                    }

                    st.markdown("</div>", unsafe_allow_html=True)

    # 画面入力内容を常に restore_plan に反映
    st.session_state["restore_plan"] = {"timetable": timetable}

    if teacher_key:
        try:
            upsert_autosave(current_school_year, teacher_key, base_grade, class_name, teacher_type, week_str, {"timetable": timetable})
            st.session_state["restore_plan"] = {"timetable": timetable}
            cur.execute(
                f"SELECT saved_at FROM auto_save_sessions WHERE school_year=? AND {teacher_where_clause()} AND week=? ORDER BY id DESC LIMIT 1",
                (current_school_year, teacher_key, week_str)
            )
            row = cur.fetchone()
            if row:
                st.caption(f"自動保存済み: {row[0]}")
        except Exception as e:
            st.warning(f"自動保存で問題が発生しました: {e}")

    week_minutes_all = compute_week_subject_minutes(timetable, base_grade)
    subject_minutes_this_grade = week_minutes_all.get(base_grade, {})

    st.markdown("---")
    st.markdown(f"#### この週の教科別 合計分数（{base_grade}）")
    for s in get_subjects_for_grade(base_grade):
        st.write(f"- {s}: {int(round(subject_minutes_this_grade.get(s, 0)))} 分")

    st.markdown("---")
    st.subheader("⭐ 時数不足警告（年度全体）")
    warn_msgs = hours_warning_messages(current_school_year)
    if warn_msgs:
        st.warning("不足 / 超過が検出されています（年間累積は『承認』で反映されます）。")
        for m in warn_msgs[:20]:
            st.write(f"- {m}")
        if len(warn_msgs) > 20:
            st.caption(f"…他 {len(warn_msgs) - 20} 件")
    else:
        st.success("不足 / 超過の大きい科目は検出されませんでした。")

    st.markdown("---")
    st.subheader("💾 自分の週案を保存（CSV）")
    slot_rows = []
    for day in DAYS:
        for period in PERIODS:
            mins = PERIOD_MINUTES.get(day, {}).get(period, 0)
            if mins <= 0:
                continue
            cell = (timetable or {}).get(day, {}).get(period, {}) or {}
            segs = cell_to_segments(cell, mins)
            if not segs:
                slot_rows.append({
                    "年度": current_school_year, "教員": teacher_key, "基準学年": base_grade, "担任学級": class_name,
                    "勤務形態": teacher_type, "週": week_str, "曜日": day, "校時": period, "分": int(round(mins)),
                    "学級": cell.get("class", ""), "教科等": "", "内容": ""
                })
            else:
                for seg in segs:
                    slot_rows.append({
                        "年度": current_school_year, "教員": teacher_key, "基準学年": base_grade, "担任学級": class_name,
                        "勤務形態": teacher_type, "週": week_str, "曜日": day, "校時": period,
                        "分": int(round(seg.get("minutes", 0))), "学級": seg.get("class", ""),
                        "教科等": seg.get("subject", ""), "内容": seg.get("content", "")
                    })
    df_my = pd.DataFrame(slot_rows)
    my_csv = df_my.to_csv(index=False).encode("utf-8-sig")
    today_str = date.today().strftime("%Y%m%d")
    my_name = f"{teacher_key or 'teacher'}_{base_grade}_{week_str}_{today_str}_my_weekly_plan.csv".replace("/", "_")
    st.download_button("⬇️ この週案をCSVで保存", my_csv, my_name, "text/csv")

    st.markdown("---")
    st.subheader("⭐ 探究活動ログ（総合 / 学校裁量（探究）など）")
    with st.expander("➕ 探究ログを追加", expanded=False):
        theme = st.text_input("テーマ", value="", key="inq_theme")
        goals = st.text_area("ねらい（育てたい力）", value="", height=80, key="inq_goals")
        activities = st.text_area("活動（学習の流れ）", value="", height=100, key="inq_activities")
        evidence = st.text_area("証拠（成果物 / 写真 / 発表 / ルーブリック等）", value="", height=80, key="inq_evidence")
        reflection = st.text_area("振り返り（児童 / 教師）", value="", height=100, key="inq_reflection")
        if st.button("保存する", key="inq_save_btn"):
            if not teacher_key:
                st.error("教員名を入力してください。")
            else:
                add_inquiry_log(current_school_year, week_str, base_grade, class_name, teacher_key, theme, goals, activities, evidence, reflection)
                st.success("探究ログを保存しました。")

    with st.expander("📚 自分 / 学年の探究ログを確認", expanded=False):
        gsel = st.selectbox("学年", ["すべて"] + list(STANDARD_HOURS.keys()), index=0, key="inq_grade_filter")
        csel = st.text_input("学級（空欄で全学級）", value="", key="inq_class_filter")
        tsel = st.text_input("教員（空欄で全教員）", value=teacher_key, key="inq_teacher_filter")
        logs = fetch_inquiry_logs(current_school_year, grade=gsel, class_name=csel, teacher=tsel)
        if not logs:
            st.info("探究ログはまだありません。")
        else:
            df_logs = pd.DataFrame(logs, columns=["id", "school_year", "week", "grade", "class", "teacher", "theme", "goals", "activities", "evidence", "reflection", "created_at"])
            st.dataframe(df_logs.drop(columns=["school_year"]), use_container_width=True, height=320)

    st.markdown("---")
    st.subheader("📝 一時保存・提出")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("💾 一時保存（作業中断用）", key="draft_save_btn"):
            if not teacher_key:
                st.error("教員名を入力してください。")
            else:
                plan = {"timetable": timetable}
                upsert_draft(current_school_year, teacher_key, base_grade, class_name, teacher_type, week_str, plan)
                upsert_autosave(current_school_year, teacher_key, base_grade, class_name, teacher_type, week_str, plan)
                st.session_state["restore_plan"] = {"timetable": timetable}
                st.success("一時保存しました。下書き一覧 / 自動保存一覧から再開できます。")
    with col_b:
        if st.button("✅ この内容で管理職へ提出する", key="submit_btn"):
            if not teacher_key:
                st.error("教員名を入力してください。")
            else:
                errors = validate_timetable_for_submit(timetable)
                if errors:
                    st.error("入力に不備があります。下記を修正してください：")
                    for e in errors:
                        st.write(f"- {e}")
                else:
                    submit_plan_from_current(current_school_year, teacher_key, base_grade, class_name, teacher_type, week_str, {"timetable": timetable})
                    st.success("週案を提出しました。管理職の承認をお待ちください。")

    st.markdown("---")
    st.subheader("📄 印刷・PDF保存用レイアウト（教員用）")
    if st.checkbox("この週案を印刷用に表示する（列幅が広い表示）", key="print_toggle"):
        df_print = build_print_df(timetable)
        if df_print.empty:
            st.info("有効なコマがありません。")
        else:
            st.write(f"**{current_school_year}／{base_grade}／{class_name}／{teacher_key}／{week_str} の週案（印刷用）**")
            st.dataframe(df_print, use_container_width=True, height=520)
            st.info("ブラウザの印刷機能（Ctrl+P）から PDF 保存・印刷を行ってください。")

# 管理職画面
if role == "管理職":
    require_manager_login()
    st.header("🧭 年度の管理（管理職）")

    years = {get_current_school_year(), DEFAULT_SCHOOL_YEAR}
    try:
        cur.execute("SELECT DISTINCT school_year FROM weekly_plans")
        for (sy,) in cur.fetchall():
            if sy:
                years.add(sy)
    except Exception:
        pass
    try:
        cur.execute("SELECT DISTINCT school_year FROM hours_total")
        for (sy,) in cur.fetchall():
            if sy:
                years.add(sy)
    except Exception:
        pass

    years_list = sorted(list(years))
    coly1, coly2, coly3 = st.columns([2, 2, 2])
    with coly1:
        view_year = st.selectbox("表示する年度", years_list, index=years_list.index(get_current_school_year()) if get_current_school_year() in years_list else 0, key="view_year_select")
    with coly2:
        st.write("現在の年度")
        st.write(f"**{get_current_school_year()}**")
    with coly3:
        if st.button("この表示年度を『現在の年度』にする", key="set_current_year_btn"):
            set_current_school_year(view_year)
            st.success(f"現在の年度を「{view_year}」に変更しました。")
            st.rerun()

    st.markdown("##### 新年度を追加")
    new_year = st.text_input("追加する年度名（例：令和9年度）", value="令和9年度", key="new_year_input")
    if st.button("➕ 新年度を追加して『現在の年度』にする", key="add_new_year_btn"):
        if new_year.strip():
            set_current_school_year(new_year.strip())
            st.success(f"新年度「{new_year.strip()}」を現在の年度にしました。")
            st.rerun()

    st.markdown("---")
    st.subheader("🧩 年度の初期化（0行の種まき）")
    if not is_year_initialized(view_year):
        st.warning(f"{view_year} は未初期化です。年間累積の行を0で作成します。")
        if st.button(f"✅ {view_year} を初期化する（0行作成）", key="init_year_btn"):
            init_year_hours_zero(view_year, initialized_by="管理職")
            st.success(f"{view_year} を初期化しました。")
            st.rerun()
    else:
        st.info(f"✅ {view_year} は初期化済みです。")

    cur.execute("SELECT id, school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by FROM weekly_plans WHERE school_year=? ORDER BY id DESC", (view_year,))
    all_rows = cur.fetchall()

    st.markdown("---")
    st.header("⭐ ダッシュボード（管理職）")
    if all_rows:
        df_plans = pd.DataFrame(all_rows, columns=["id", "school_year", "teacher", "grade", "class", "teacher_type", "week", "plan_json", "status", "submitted_at", "approved_at", "approved_by"])
        st.subheader("提出状況（件数）")
        counts = df_plans["status"].value_counts().to_dict()
        st.write({k: int(v) for k, v in counts.items()})

        cda1, cda2 = st.columns(2)
        with cda1:
            st.subheader("提出状況（教員別）")
            by_teacher = df_plans.groupby(["teacher", "status"]).size().reset_index(name="count")
            pivot = by_teacher.pivot_table(index="teacher", columns="status", values="count", fill_value=0)
            st.dataframe(pivot.reset_index(), use_container_width=True, height=240)
        with cda2:
            st.subheader("提出状況（学年別）")
            by_grade = df_plans.groupby(["grade", "status"]).size().reset_index(name="count")
            pivot_g = by_grade.pivot_table(index="grade", columns="status", values="count", fill_value=0)
            st.dataframe(pivot_g.reset_index(), use_container_width=True, height=240)

        st.subheader("学校行事 自動集計")
        df_ev = aggregate_events_from_plans(all_rows)
        if df_ev.empty:
            st.info("学校行事の入力がある週案がまだありません。")
        else:
            ev_sum = df_ev.groupby(["学年"])["学校行事(45分コマ)"].sum().reset_index()
            st.dataframe(ev_sum, use_container_width=True, height=220)
            with st.expander("明細（週×教員）", expanded=False):
                st.dataframe(df_ev, use_container_width=True, height=320)
    else:
        st.info("この年度の週案がまだありません。")

    st.subheader("⭐ 時数不足警告（年度全体）")
    warn = hours_warning_messages(view_year)
    if warn:
        for m in warn:
            st.warning(m)
    else:
        st.success("不足 / 超過の大きい科目は検出されませんでした。")

    st.subheader("⭐ 年間時数グラフ")
    df_hours_graph = build_hours_progress_df(view_year)
    if not df_hours_graph.empty:
        graph_grade = st.selectbox("グラフ表示学年", list(STANDARD_HOURS.keys()), key="graph_grade")
        gdf = df_hours_graph[df_hours_graph["学年"] == graph_grade].copy().set_index("教科等")[["標準(45分コマ)", "実施累積(45分コマ)"]]
        st.bar_chart(gdf)
    else:
        st.info("年間時数データがありません。")

    st.subheader("⭐ 年間時数 最適化提案（今後の必要 / 週）")
    df_opt = build_optimization_suggestions(view_year)
    st.caption(f"残り週数は概算（{DEFAULT_WEEKS_PER_YEAR}週）です。")
    if not df_opt.empty:
        st.dataframe(df_opt.sort_values(by="今後の必要/週(45分コマ)", ascending=False), use_container_width=True, height=360)

    st.markdown("---")
    st.header("📝 提出された週案一覧（管理職用）")
    counts = {"下書き": 0, "提出": 0, "承認": 0, "差戻": 0}
    for r in all_rows:
        stt = r[8]
        if stt in counts:
            counts[stt] += 1
    st.markdown("#### 状態別件数")
    st.write(f"- 下書き：{counts['下書き']} 件")
    st.write(f"- 提出：{counts['提出']} 件")
    st.write(f"- 承認：{counts['承認']} 件")
    st.write(f"- 差戻：{counts['差戻']} 件")

    grade_list = sorted({r[3] for r in all_rows if r[3]})
    teacher_list = sorted({r[2] for r in all_rows if r[2]})
    week_list = sorted({r[6] for r in all_rows if r[6]}, reverse=True)

    st.markdown("#### 表示フィルタ")
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filter_status = st.selectbox("状態", ["すべて", "下書き", "提出", "承認", "差戻"], key="filter_status")
    with col_f2:
        grade_filter = st.selectbox("学年", ["すべて"] + grade_list, key="filter_grade")
    with col_f3:
        teacher_filter = st.selectbox("教員", ["すべて"] + teacher_list, key="filter_teacher")
    col_f4, col_f5 = st.columns(2)
    with col_f4:
        week_filter = st.selectbox("週", ["すべて"] + week_list, key="filter_week")
    with col_f5:
        only_unapproved = st.checkbox("未承認（提出＋差戻）のみ表示する", value=False, key="only_unapproved")

    rows = all_rows
    if filter_status != "すべて":
        rows = [r for r in rows if r[8] == filter_status]
    if grade_filter != "すべて":
        rows = [r for r in rows if r[3] == grade_filter]
    if teacher_filter != "すべて":
        rows = [r for r in rows if r[2] == teacher_filter]
    if week_filter != "すべて":
        rows = [r for r in rows if r[6] == week_filter]
    if only_unapproved:
        rows = [r for r in rows if r[8] not in ("承認", "下書き")]

    if not rows:
        st.info("該当する週案はありません。")
    else:
        st.caption("※ 各行をクリックすると詳細が表示されます。")

    for (wid, school_year, teacher, grade, class_name, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by) in rows:
        try:
            plan = json.loads(plan_json) if plan_json else {}
        except Exception:
            plan = {}
        timetable = normalize_timetable(plan.get("timetable", {}))
        week_minutes_all = compute_week_subject_minutes(timetable, grade)
        title = f"ID:{wid} / {school_year} / {week} / {grade} / {class_name} / {teacher} / 状態：{status}"

        with st.expander(title):
            st.markdown(f"状態：{status_badge(status)}", unsafe_allow_html=True)
            st.write(f"- 勤務形態：{teacher_type if teacher_type else '（未記録）'}")
            st.write(f"- 提出者：{teacher}")
            st.write(f"- 基本学級：{grade} {class_name if class_name else ''}")
            st.write(f"- 提出日時：{submitted_at if submitted_at else '（記録なし）'}")
            if approved_at:
                st.write(f"- 承認日時：{approved_at}")
                st.write(f"- 承認者：{approved_by if approved_by else '管理職'}")
            else:
                st.write("- 承認：未承認")

            st.markdown("#### 一週間の時間割（学級＋教科等＋内容）")
            df_print = build_print_df(timetable)
            if df_print.empty:
                st.info("有効なコマがありません。")
            else:
                st.dataframe(df_print, use_container_width=True, height=520)

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"✅ 承認する（ID:{wid}）", key=f"approve_{wid}"):
                    if status != "承認":
                        for g in week_minutes_all:
                            for subj, mins in week_minutes_all[g].items():
                                add_hours(view_year, g, subj, mins)
                        cur.execute("UPDATE weekly_plans SET status='承認', approved_at=DATETIME('now'), approved_by=? WHERE id=?", ("管理職", wid))
                        conn.commit()
                        st.success("承認しました。年間累積時数に反映済みです。")
                        st.rerun()
                    else:
                        st.info("すでに承認済みです。")
            with col2:
                if st.button(f"↩ 差戻にする（ID:{wid}）", key=f"reject_{wid}"):
                    if status != "差戻":
                        cur.execute("UPDATE weekly_plans SET status='差戻' WHERE id=?", (wid,))
                        conn.commit()
                        st.warning("差戻にしました。")
                        st.rerun()
                    else:
                        st.info("すでに差戻済みです。")

    st.markdown("---")
    st.header(f"📊 年間累積時数の状況（{view_year}）")
    for g in STANDARD_HOURS.keys():
        st.subheader(f"{g}の時数状況")
        rows_table = []
        for subj in get_subjects_for_grade(g):
            std = float(STANDARD_HOURS[g][subj])
            cur.execute("SELECT consumed FROM hours_total WHERE school_year=? AND grade=? AND subject=?", (view_year, g, subj))
            row = cur.fetchone()
            used = float(row[0]) if row else 0.0
            rows_table.append({"教科等": subj, "標準（45分コマ）": round(std, 2), "実施累積（45分コマ）": round(used, 2), "残り（45分コマ）": round(std - used, 2)})
        st.table(rows_table)

    def get_last_backup_date(school_year: str):
        cur.execute("SELECT created_at FROM backup_log WHERE school_year=? ORDER BY id DESC LIMIT 1", (school_year,))
        row = cur.fetchone()
        return row[0] if row else None

    def log_backup(school_year: str, created_by: str, filename: str):
        cur.execute("INSERT INTO backup_log (school_year, created_at, created_by, filename) VALUES (?, DATETIME('now'), ?, ?)", (school_year, created_by, filename))
        conn.commit()

    def fetch_all_weekly_plans_for_year(school_year: str):
        cur.execute("SELECT id, school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by FROM weekly_plans WHERE school_year=? ORDER BY id DESC", (school_year,))
        return cur.fetchall()

    def flatten_plans_to_rows(plans):
        plan_rows, slot_rows = [], []
        for (wid, sy, teacher, grade, class_name, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by) in plans:
            plan_rows.append({"id": wid, "school_year": sy, "teacher": teacher, "grade": grade, "class": class_name, "teacher_type": teacher_type, "week": week, "status": status, "submitted_at": submitted_at, "approved_at": approved_at, "approved_by": approved_by})
            try:
                plan = json.loads(plan_json) if plan_json else {}
            except Exception:
                plan = {}
            timetable = normalize_timetable(plan.get("timetable", {}))
            for day in DAYS:
                for period in PERIODS:
                    slot_minutes = PERIOD_MINUTES.get(day, {}).get(period, 0)
                    if slot_minutes <= 0:
                        continue
                    cell = (timetable or {}).get(day, {}).get(period, {}) or {}
                    segs = cell_to_segments(cell, slot_minutes)
                    if not segs:
                        slot_rows.append({"plan_id": wid, "school_year": sy, "week": week, "teacher": teacher, "base_grade": grade, "base_class": class_name, "teacher_type": teacher_type, "day": day, "period": period, "minutes": int(round(slot_minutes)), "class": cell.get("class", ""), "subject": "", "content": "", "status": status})
                    else:
                        for seg in segs:
                            slot_rows.append({"plan_id": wid, "school_year": sy, "week": week, "teacher": teacher, "base_grade": grade, "base_class": class_name, "teacher_type": teacher_type, "day": day, "period": period, "minutes": int(round(seg.get("minutes", 0))), "class": seg.get("class", ""), "subject": seg.get("subject", ""), "content": seg.get("content", ""), "status": status})
        return pd.DataFrame(plan_rows), pd.DataFrame(slot_rows)

    def to_excel_bytes(dfs: dict):
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            for sheet, df in dfs.items():
                df.to_excel(writer, index=False, sheet_name=str(sheet)[:31])
        bio.seek(0)
        return bio.getvalue()

    st.markdown("---")
    st.header("🧰 バックアップ（Excel/CSV ダウンロード）")
    st.caption(f"対象年度：{view_year}（管理職のみ実行）")
    last_backup = get_last_backup_date(view_year)
    if last_backup:
        st.write(f"前回バックアップ：{last_backup}")
    else:
        st.warning("まだバックアップが作成されていません。初回は必ず作成してください。")

    st.session_state.setdefault("backup_excel_bytes", None)
    st.session_state.setdefault("backup_csv_pack", None)
    st.session_state.setdefault("backup_filename", None)

    if st.button("🟦 バックアップを作成（今日の日付で生成）", key="backup_make_btn"):
        plans = fetch_all_weekly_plans_for_year(view_year)
        df_plans, df_slots = flatten_plans_to_rows(plans)
        df_hours = build_hours_progress_df(view_year)
        today_str = date.today().strftime("%Y%m%d")
        filename = f"{safe_year_str(view_year)}_weekly_plan_backup_{today_str}.xlsx"
        excel_bytes = to_excel_bytes({"週案一覧": df_plans, "時間割（コマ明細）": df_slots, "年間累積（進捗）": df_hours})
        st.session_state["backup_excel_bytes"] = excel_bytes
        st.session_state["backup_csv_pack"] = {
            "weekly_plans": df_plans.to_csv(index=False).encode("utf-8-sig"),
            "weekly_slots": df_slots.to_csv(index=False).encode("utf-8-sig"),
            "hours_progress": df_hours.to_csv(index=False).encode("utf-8-sig")
        }
        st.session_state["backup_filename"] = filename
        log_backup(view_year, created_by="管理職", filename=filename)
        st.success("バックアップを作成しました。")

    if st.session_state["backup_excel_bytes"]:
        today_str = date.today().strftime("%Y%m%d")
        st.download_button(
            "⬇️ バックアップ一括（Excel）をダウンロード",
            st.session_state["backup_excel_bytes"],
            st.session_state["backup_filename"] or f"{safe_year_str(view_year)}_weekly_plan_backup_{today_str}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        csv_pack = st.session_state["backup_csv_pack"] or {}
        st.download_button("⬇️ 週案一覧（CSV）", csv_pack.get("weekly_plans", b""), f"{safe_year_str(view_year)}_weekly_plans_{today_str}.csv", "text/csv")
        st.download_button("⬇️ 時間割（コマ明細）（CSV）", csv_pack.get("weekly_slots", b""), f"{safe_year_str(view_year)}_weekly_slots_{today_str}.csv", "text/csv")
        st.download_button("⬇️ 年間累積（進捗）（CSV）", csv_pack.get("hours_progress", b""), f"{safe_year_str(view_year)}_hours_progress_{today_str}.csv", "text/csv")

    st.markdown("---")
    st.header("🏛 区教委提出用（年間時数 まとめCSV）")
    df_submit = build_hours_progress_df(view_year).rename(
        columns={
            "標準(45分コマ)": "標準（45分コマ）",
            "実施累積(45分コマ)": "実施累積（45分コマ）",
            "残り(45分コマ)": "残り（45分コマ）",
            "進捗(%)": "進捗（％）"
        }
    )[["年度", "学年", "教科等", "標準（45分コマ）", "実施累積（45分コマ）", "残り（45分コマ）", "進捗（％）"]]
    with st.expander("内容を表示（確認用）", expanded=False):
        st.dataframe(df_submit, use_container_width=True, height=420)

    today_str = date.today().strftime("%Y%m%d")
    submit_csv = df_submit.to_csv(index=False).encode("utf-8-sig")
    school_short = "東小松川小学校"
    reiwa_short = to_reiwa_short(view_year)
    submit_name = f"{reiwa_short}_年間指導時数集計_{school_short}_{today_str}.csv"
    st.download_button("⬇️ 区教委提出用CSVをダウンロード", submit_csv, submit_name, "text/csv")

    st.markdown("---")
    st.header("⭐ 探究活動ログ（管理職）")
    gsel2 = st.selectbox("学年フィルタ", ["すべて"] + list(STANDARD_HOURS.keys()), index=0, key="inq_m_grade")
    csel2 = st.text_input("学級フィルタ（空欄で全学級）", value="", key="inq_m_class")
    tsel2 = st.text_input("教員フィルタ（空欄で全教員）", value="", key="inq_m_teacher")
    logs2 = fetch_inquiry_logs(view_year, grade=gsel2, class_name=csel2, teacher=tsel2)
    if not logs2:
        st.info("探究ログはまだありません。")
    else:
        df_logs2 = pd.DataFrame(logs2, columns=["id", "school_year", "week", "grade", "class", "teacher", "theme", "goals", "activities", "evidence", "reflection", "created_at"])
        st.dataframe(df_logs2.drop(columns=["school_year"]), use_container_width=True, height=380)
