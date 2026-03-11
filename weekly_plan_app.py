# weekly_plan_app.py （東小松川小学校 完全神アプリ V5）
# V5追加:
# ① 自動保存（autosave_plans）
# ② 前回の続きから再開
# ③ 下書き一覧復元
# ④ 前週コピー
# ⑤ 時数不足警告
# ⑥ 授業入替（安全UI）
# ⑦ 探究活動ログ
# ⑧ 管理職ダッシュボード（提出状況・学校行事集計・時数最適化提案）
# ⑨ 年間時数グラフ
# ⑩ 印刷用表示（ブラウザ印刷/PDF保存向け）
# ※ 外部APIなし / SQLiteのみ / Streamlit単体で動作

import streamlit as st
import sqlite3
from datetime import date
import json
import pandas as pd
import io
import re

DEFAULT_ADMIN_PASSWORD = "higakoma2025"
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
DEFAULT_SCHOOL_YEAR = "令和8年度"
DEFAULT_WEEKS_PER_YEAR = 35

st.set_page_config(page_title="東小松川小学校 完全神アプリ V5", layout="wide")

st.markdown(
    """
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
    .status-label {display: inline-block;padding: 2px 8px;border-radius: 999px;font-size: 12px;color: white;}
    .status-teishutsu { background-color: #f39c12; }
    .status-shonin    { background-color: #27ae60; }
    .status-sashimodoshi { background-color: #c0392b; }
    .status-shitagaki { background-color: #7f8c8d; }
    .tt-cell {border: 1px solid #999 !important;border-radius: 6px !important;padding: 6px 6px 2px 6px !important;margin: 2px 0 6px 0 !important;background: rgba(255,255,255,0.55);}
    .tt-rowlabel {border: 1px solid #999 !important;border-radius: 6px !important;padding: 8px 6px !important;margin: 2px 0 6px 0 !important;background: rgba(245,245,245,0.8);font-weight: 700;text-align: center;}
    .tt-headcell {border: 1px solid #999 !important;border-radius: 6px !important;padding: 8px 6px !important;margin: 2px 0 6px 0 !important;background: rgba(235,235,235,0.9);font-weight: 800;text-align: center;}
    .tt-section {font-size: 12px;font-weight: 800;padding: 2px 6px;border-radius: 999px;display: inline-block;margin: 2px 0 4px 0;border: 1px solid #777;}
    .tt-event { background: rgba(255,248,220,0.95); }
    .tt-main  { background: rgba(235,255,235,0.95); }
    .tt-mini  { font-size: 12px; opacity: 0.9; }
    .dataframe td, .dataframe th {white-space: pre-wrap !important;word-break: break-word !important;line-height: 1.35 !important;vertical-align: top !important;}
    div[data-testid="stVerticalBlockBorderWrapper"]{border: 1px solid #000 !important;border-radius: 0px !important;box-shadow: none !important;}
    @media print {
        header, footer, .stSidebar { display: none !important; }
        .main .block-container { padding-top: 0px !important; padding-bottom: 0px !important; }
        table {width: 100% !important;font-size: 11px !important;border-collapse: collapse !important;}
        th, td {border: 1px solid #000 !important;padding: 4px !important;white-space: pre-wrap !important;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

COLUMN_WIDTHS = [0.7] + [1.6] * 6
DB_PATH = "weekly_plans.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

def ensure_settings_table():
    cur.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()

def get_setting(key: str, default: str):
    ensure_settings_table()
    cur.execute("SELECT value FROM app_settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else default

def set_setting(key: str, value: str):
    ensure_settings_table()
    cur.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()

def get_current_school_year():
    return get_setting("current_school_year", DEFAULT_SCHOOL_YEAR)

def set_current_school_year(year_str: str):
    set_setting("current_school_year", year_str)

cur.execute("""
CREATE TABLE IF NOT EXISTS weekly_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_year TEXT,
    teacher TEXT,
    grade TEXT,
    class TEXT,
    teacher_type TEXT,
    week TEXT,
    plan_json TEXT,
    status TEXT,
    submitted_at TEXT,
    approved_at TEXT,
    approved_by TEXT
)
""")
for col in ["school_year", "class", "teacher_type", "submitted_at", "approved_at", "approved_by"]:
    try:
        cur.execute(f"ALTER TABLE weekly_plans ADD COLUMN {col} TEXT")
    except sqlite3.OperationalError:
        pass
try:
    cur.execute("UPDATE weekly_plans SET school_year=? WHERE school_year IS NULL OR school_year=''", (DEFAULT_SCHOOL_YEAR,))
    conn.commit()
except Exception:
    pass

cur.execute("""
CREATE TABLE IF NOT EXISTS hours_total (
    school_year TEXT,
    grade TEXT,
    subject TEXT,
    consumed REAL,
    PRIMARY KEY(school_year, grade, subject)
)
""")
try:
    cur.execute("ALTER TABLE hours_total ADD COLUMN school_year TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass
try:
    cur.execute("UPDATE hours_total SET school_year=? WHERE school_year IS NULL OR school_year=''", (DEFAULT_SCHOOL_YEAR,))
    conn.commit()
except Exception:
    pass

cur.execute("""
CREATE TABLE IF NOT EXISTS inquiry_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_year TEXT,
    week TEXT,
    grade TEXT,
    class TEXT,
    teacher TEXT,
    theme TEXT,
    goals TEXT,
    activities TEXT,
    evidence TEXT,
    reflection TEXT,
    created_at TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS autosave_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_year TEXT,
    teacher TEXT,
    week TEXT,
    grade TEXT,
    class TEXT,
    teacher_type TEXT,
    plan_json TEXT,
    saved_at TEXT
)
""")
conn.commit()

STANDARD_HOURS = {
    "1年": {"国語": 306, "算数": 140, "生活": 102, "音楽": 68, "図工": 68, "体育": 102, "道徳": 34, "特活": 34, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "2年": {"国語": 280, "算数": 140, "生活": 102, "音楽": 68, "図工": 68, "体育": 102, "道徳": 35, "特活": 35, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "3年": {"国語": 210, "社会": 70, "算数": 175, "理科": 70, "音楽": 50, "図工": 50, "体育": 105, "道徳": 35, "特活": 35, "外国語活動": 35, "総合的な学習の時間": 70, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "4年": {"国語": 175, "社会": 105, "算数": 175, "理科": 105, "音楽": 50, "図工": 50, "体育": 105, "道徳": 35, "特活": 35, "外国語活動": 35, "総合的な学習の時間": 70, "家庭科": 0, "クラブ": 10, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "5年": {"国語": 175, "社会": 105, "算数": 175, "理科": 105, "音楽": 45, "図工": 45, "家庭科": 70, "体育": 90, "道徳": 35, "特活": 35, "外国語": 70, "総合的な学習の時間": 70, "クラブ": 10, "委員会": 10, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
    "6年": {"国語": 175, "社会": 105, "算数": 140, "理科": 105, "音楽": 45, "図工": 45, "家庭科": 70, "体育": 90, "道徳": 35, "特活": 35, "外国語": 70, "総合的な学習の時間": 70, "クラブ": 10, "委員会": 10, "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35},
}

def get_subjects_for_grade(grade: str):
    return list(STANDARD_HOURS[grade].keys())

ALL_SUBJECTS = sorted({subj for g in STANDARD_HOURS.values() for subj in g.keys()})
DAYS = ["月", "火", "水", "木", "金", "土"]
PERIODS = ["1校時", "2校時", "3校時", "4校時", "5校時", "学校裁量", "6校時"]
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
    n = int(round(v * 8))
    return max(0, min(8, n))

def convert_to_45(mins: float) -> float:
    return float(mins) / 45.0

def detect_grade_from_class(klass: str):
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

def add_hours(school_year: str, grade: str, subject: str, minutes: float):
    add_45 = convert_to_45(minutes)
    cur.execute("SELECT consumed FROM hours_total WHERE school_year=? AND grade=? AND subject=?", (school_year, grade, subject))
    row = cur.fetchone()
    if row:
        new_value = float(row[0]) + add_45
        cur.execute("UPDATE hours_total SET consumed=? WHERE school_year=? AND grade=? AND subject=?", (new_value, school_year, grade, subject))
    else:
        cur.execute("INSERT INTO hours_total (school_year, grade, subject, consumed) VALUES (?, ?, ?, ?)", (school_year, grade, subject, add_45))
    conn.commit()

def cell_to_segments(cell: dict, slot_minutes: float):
    if not cell or slot_minutes <= 0:
        return []
    klass = cell.get("class", "")
    segs = []
    event = cell.get("event") or {}
    frac = float(event.get("fraction", 0.0) or 0.0)
    frac = max(0.0, min(1.0, frac))
    event_minutes = slot_minutes * frac
    remain_minutes = slot_minutes - event_minutes
    if event_minutes > 0:
        segs.append({"class": klass, "subject": "学校行事", "content": (event.get("content") or "").strip(), "minutes": event_minutes, "event_fraction": frac})
    main = cell.get("main") or {}
    main_subj = (main.get("subject") or "").strip()
    main_cont = (main.get("content") or "").strip()
    if remain_minutes > 0 and (main_subj and main_subj != "（空欄）"):
        segs.append({"class": klass, "subject": main_subj, "content": main_cont, "minutes": remain_minutes, "event_fraction": 0.0})
    if frac == 0.0 and not segs:
        subj = (cell.get("subject") or "").strip()
        cont = (cell.get("content") or "").strip()
        if subj and subj != "（空欄）":
            segs.append({"class": klass, "subject": subj, "content": cont, "minutes": slot_minutes, "event_fraction": 0.0})
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
    rows = []
    index = []
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
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, index=index, columns=DAYS)

def require_manager_login():
    if st.session_state.get("manager_authenticated"):
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
    if not st.session_state.get("manager_authenticated"):
        st.warning("管理職専用画面です。サイドバーからパスワードを入力してください。")
        st.stop()

def ensure_year_init_table():
    cur.execute("CREATE TABLE IF NOT EXISTS year_init (school_year TEXT PRIMARY KEY, initialized_at TEXT, initialized_by TEXT)")
    conn.commit()

def is_year_initialized(school_year: str) -> bool:
    ensure_year_init_table()
    cur.execute("SELECT 1 FROM year_init WHERE school_year=? LIMIT 1", (school_year,))
    return cur.fetchone() is not None

def init_year_hours_zero(school_year: str, initialized_by: str = "管理職"):
    ensure_year_init_table()
    for g in STANDARD_HOURS.keys():
        for s in get_subjects_for_grade(g):
            cur.execute("INSERT OR IGNORE INTO hours_total (school_year, grade, subject, consumed) VALUES (?, ?, ?, 0.0)", (school_year, g, s))
    cur.execute("INSERT OR REPLACE INTO year_init (school_year, initialized_at, initialized_by) VALUES (?, DATETIME('now'), ?)", (school_year, initialized_by))
    conn.commit()

def upsert_draft(school_year: str, teacher: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    cur.execute("SELECT id FROM weekly_plans WHERE school_year=? AND teacher=? AND week=? AND status='下書き' ORDER BY id DESC LIMIT 1", (school_year, teacher, week_str))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE weekly_plans SET grade=?, class=?, teacher_type=?, plan_json=?, submitted_at=DATETIME('now') WHERE id=?", (base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), row[0]))
    else:
        cur.execute("INSERT INTO weekly_plans (school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, '下書き', DATETIME('now'))", (school_year, teacher, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False)))
    conn.commit()

def autosave_plan(school_year: str, teacher: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    cur.execute("INSERT INTO autosave_plans (school_year, teacher, week, grade, class, teacher_type, plan_json, saved_at) VALUES (?, ?, ?, ?, ?, ?, ?, DATETIME('now'))", (school_year, teacher, week_str, base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False)))
    conn.commit()

def fetch_last_autosave(school_year: str, teacher: str):
    cur.execute("SELECT id, plan_json, week, grade, class, teacher_type, saved_at FROM autosave_plans WHERE school_year=? AND teacher=? ORDER BY id DESC LIMIT 1", (school_year, teacher))
    return cur.fetchone()

def list_my_drafts(school_year: str, teacher: str):
    cur.execute("SELECT id, week, grade, class, teacher_type, plan_json, submitted_at FROM weekly_plans WHERE school_year=? AND teacher=? AND status='下書き' ORDER BY week DESC, id DESC", (school_year, teacher))
    return cur.fetchall()

def load_plan_by_id(wid: int):
    cur.execute("SELECT id, school_year, teacher, grade, class, teacher_type, week, plan_json, status FROM weekly_plans WHERE id=?", (wid,))
    return cur.fetchone()

def fetch_latest_plan_before_week(school_year: str, teacher: str, week_str: str):
    cur.execute("SELECT plan_json, week, status FROM weekly_plans WHERE school_year=? AND teacher=? AND week < ? AND status IN ('提出','承認','差戻','下書き') ORDER BY week DESC, id DESC LIMIT 1", (school_year, teacher, week_str))
    return cur.fetchone()

def submit_plan_from_current(school_year: str, teacher: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    cur.execute("SELECT id FROM weekly_plans WHERE school_year=? AND teacher=? AND week=? AND status='下書き' ORDER BY id DESC LIMIT 1", (school_year, teacher, week_str))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE weekly_plans SET grade=?, class=?, teacher_type=?, plan_json=?, status='提出', submitted_at=DATETIME('now') WHERE id=?", (base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), row[0]))
    else:
        cur.execute("INSERT INTO weekly_plans (school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, '提出', DATETIME('now'))", (school_year, teacher, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False)))
    conn.commit()

def to_reiwa_short(year_str: str) -> str:
    m = re.search(r"令和\s*([0-9]+)\s*年度", str(year_str))
    return f"R{m.group(1)}" if m else str(year_str).replace("年度", "")

def safe_year_str(s: str):
    return str(s).replace(" ", "").replace("/", "_").replace("\\", "_")

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
        sub = df[df["学年"] == gg].copy()
        for _, r in sub.iterrows():
            remain = float(r["残り(45分コマ)"])
            need_per_week = remain / remaining_weeks
            rows.append({"年度": school_year, "学年": gg, "教科等": r["教科等"], "残り(45分コマ)": round(remain, 2), "残り週(概算)": remaining_weeks, "今後の必要/週(45分コマ)": round(need_per_week, 2)})
    return pd.DataFrame(rows)

def hours_warning_messages(school_year: str):
    df = build_hours_progress_df(school_year)
    msgs = []
    for _, r in df.iterrows():
        remain = float(r["残り(45分コマ)"])
        if remain > 20:
            msgs.append(f"{r['学年']} {r['教科等']}：不足 {round(remain,1)} コマ")
        if remain < -5:
            msgs.append(f"{r['学年']} {r['教科等']}：超過 {round(abs(remain),1)} コマ")
    return msgs

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
            if ev <= 0:
                continue
            out.append({"年度": sy, "週": week, "学年": gg, "教員": teacher, "状態": status, "学校行事(分)": int(round(ev)), "学校行事(45分コマ)": round(convert_to_45(ev), 2)})
    return pd.DataFrame(out)

def suggest_subject_sequence_for_grade(school_year: str, grade: str):
    df = build_optimization_suggestions(school_year)
    gdf = df[df["学年"] == grade].copy()
    if gdf.empty:
        return []
    gdf = gdf.sort_values(by="今後の必要/週(45分コマ)", ascending=False)
    gdf = gdf[gdf["教科等"] != "学校行事"]
    seq = list(gdf["教科等"].values)
    if not seq:
        seq = [s for s in get_subjects_for_grade(grade) if s != "学校行事"]
    return seq

def auto_fill_timetable_proposal(school_year: str, teacher_type: str, base_grade: str, class_name: str, class_candidates: list, timetable: dict):
    seq = suggest_subject_sequence_for_grade(school_year, base_grade)
    if not seq:
        return timetable
    idx = 0
    for period in PERIODS:
        for day in DAYS:
            mins = PERIOD_MINUTES.get(day, {}).get(period, 0)
            if mins <= 0:
                continue
            timetable.setdefault(day, {})
            cell = timetable[day].get(period, {}) or {}
            main = (cell.get("main") or {})
            if (main.get("subject") or "").strip() not in ("", "（空欄）"):
                continue
            event = cell.get("event") or {"fraction": 0.0, "content": ""}
            frac = float(event.get("fraction", 0.0) or 0.0)
            frac = max(0.0, min(1.0, frac))
            remain = mins - mins * frac
            if remain <= 0:
                timetable[day][period] = {"class": cell.get("class", class_name or ""), "event": {"fraction": frac, "content": (event.get("content") or "")}, "main": {"subject": "（空欄）", "content": ""}}
                continue
            subj = seq[idx % len(seq)]
            idx += 1
            klass = class_name or ""
            if teacher_type.startswith("専科"):
                if class_candidates:
                    klass = class_candidates[idx % len(class_candidates)]
                else:
                    klass = cell.get("class", "")
            timetable[day][period] = {"class": klass, "event": {"fraction": frac, "content": (event.get("content") or "")}, "main": {"subject": subj, "content": "（提案）単元名／ねらい／評価観点を入力"}}
    return timetable

def swap_cells_in_timetable(tt: dict, day_a: str, period_a: str, day_b: str, period_b: str):
    tt.setdefault(day_a, {})
    tt.setdefault(day_b, {})
    cell_a = tt[day_a].get(period_a)
    cell_b = tt[day_b].get(period_b)
    tt[day_a][period_a] = cell_b if cell_b is not None else {}
    tt[day_b][period_b] = cell_a if cell_a is not None else {}
    return tt

def add_inquiry_log(school_year: str, week: str, grade: str, class_name: str, teacher: str, theme: str, goals: str, activities: str, evidence: str, reflection: str):
    cur.execute("INSERT INTO inquiry_logs (school_year, week, grade, class, teacher, theme, goals, activities, evidence, reflection, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATETIME('now'))", (school_year, week, grade, class_name, teacher, theme, goals, activities, evidence, reflection))
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
        q += " AND teacher=?"
        args.append(teacher.strip())
    q += " ORDER BY created_at DESC, id DESC"
    cur.execute(q, tuple(args))
    return cur.fetchall()

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
    st.session_state.setdefault("restore_plan", None)
    st.session_state.setdefault("last_autosave_payload", "")
    st.session_state.setdefault("autosave_notice", False)

    teacher = st.text_input("教員名", value=st.session_state.get("teacher_name", ""), key="teacher_name_input")
    if teacher:
        st.session_state["teacher_name"] = teacher

    st.markdown("---")
    st.subheader("↺ 前回の続きから再開")
    if teacher.strip():
        last_auto = fetch_last_autosave(current_school_year, teacher.strip())
        if last_auto:
            _, _auto_pj, _auto_week, _auto_grade, _auto_class, _auto_type, _auto_saved_at = last_auto
            st.info(f"前回の自動保存があります：週 {_auto_week} / {_auto_grade} {_auto_class or ''} / {_auto_type} / 保存 {_auto_saved_at}")
            if st.button("↺ 前回の作業を復元する", key="restore_autosave_btn"):
                try:
                    auto_plan = json.loads(_auto_pj) if _auto_pj else {}
                except Exception:
                    auto_plan = {}
                st.session_state["restore_plan"] = auto_plan
                st.session_state["teacher_type"] = _auto_type if _auto_type in ["担任", "専科（音楽・家庭科など）"] else "担任"
                st.session_state["base_grade"] = _auto_grade if _auto_grade in STANDARD_HOURS else st.session_state["base_grade"]
                st.session_state["class_name"] = _auto_class or ""
                try:
                    st.session_state["week_date"] = date.fromisoformat(_auto_week)
                except Exception:
                    pass
                st.session_state["restore_notice"] = True
                st.success("前回の自動保存内容を復元しました。")
                st.rerun()
        else:
            st.caption("前回再開できる自動保存データはまだありません。")
    else:
        st.caption("※ 教員名を入力すると『前回の続きから再開』が使えます。")

    st.markdown("---")
    st.subheader("🗂 下書き一覧（復元）")
    if teacher.strip():
        drafts = list_my_drafts(current_school_year, teacher.strip())
        if drafts:
            options = []
            id_map = {}
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
                    st.session_state["restore_plan"] = plan
                    st.session_state["teacher_type"] = _tt if _tt in ["担任", "専科（音楽・家庭科など）"] else "担任"
                    st.session_state["base_grade"] = _g if _g in STANDARD_HOURS else st.session_state["base_grade"]
                    st.session_state["class_name"] = _c or ""
                    try:
                        st.session_state["week_date"] = date.fromisoformat(_wk)
                    except Exception:
                        pass
                    st.session_state["restore_notice"] = True
                    st.success("下書きを復元しました。")
                    st.rerun()
        else:
            st.caption("下書きはまだありません。")
    else:
        st.caption("※ 教員名を入力すると下書き一覧が表示されます。")

    if st.session_state.get("restore_notice"):
        st.info("復元が完了しました（勤務形態／基準学年／週／学級／表の中身を反映）。")
        st.session_state["restore_notice"] = False

    teacher_type = st.radio("勤務形態", ["担任", "専科（音楽・家庭科など）"], index=0 if st.session_state["teacher_type"] == "担任" else 1, key="teacher_type_radio")
    st.session_state["teacher_type"] = teacher_type
    grade_keys = list(STANDARD_HOURS.keys())
    base_grade = st.selectbox("基準学年", grade_keys, index=grade_keys.index(st.session_state["base_grade"]) if st.session_state["base_grade"] in grade_keys else 0, key="base_grade_select")
    st.session_state["base_grade"] = base_grade
    class_name = st.text_input("自分の担任学級（例：3-1）※担任でなければ空欄可", value=st.session_state.get("class_name", ""), key="class_name_input")
    st.session_state["class_name"] = class_name
    week = st.date_input("対象週（週の初日：月曜日など）", value=st.session_state.get("week_date", date.today()), key="week_date_input")
    st.session_state["week_date"] = week
    week_str = str(week)

    if teacher_type == "担任":
        subject_options = ["（空欄）"] + get_subjects_for_grade(base_grade)
        class_candidates = [class_name] if class_name else []
    else:
        subject_options = ["（空欄）"] + ALL_SUBJECTS
        classes_input = st.text_input("指導学級一覧", value=class_name, key="classes_input")
        class_candidates = [c.strip() for c in classes_input.split(",") if c.strip()]

    st.markdown("---")
    st.subheader("⭐ 前週コピー")
    if st.button("⬅ 前週の週案をコピーする", key="copy_prev_week"):
        if not teacher.strip():
            st.error("教員名を入力してください。")
        else:
            row = fetch_latest_plan_before_week(current_school_year, teacher.strip(), week_str)
            if not row:
                st.warning("前週データが見つかりませんでした。")
            else:
                plan_json, prev_week, _ = row
                try:
                    prev_plan = json.loads(plan_json) if plan_json else {}
                except Exception:
                    prev_plan = {}
                st.session_state["restore_plan"] = prev_plan
                st.success(f"前週（{prev_week}）をコピーしました。")
                st.rerun()

    st.subheader("⭐ 週案自動生成（提案）")
    if st.button("🤖 空欄コマに教科を提案して自動入力", key="auto_fill_btn"):
        restore_plan = st.session_state.get("restore_plan") or {}
        tt = (restore_plan.get("timetable") if isinstance(restore_plan, dict) else {}) or {}
        if not isinstance(tt, dict):
            tt = {}
        tt = auto_fill_timetable_proposal(current_school_year, teacher_type, base_grade, class_name, class_candidates, tt)
        st.session_state["restore_plan"] = {"timetable": tt}
        st.success("提案を反映しました（空欄のみ）。")
        st.rerun()

    st.markdown("---")
    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    timetable = {}
    restore_plan = st.session_state.get("restore_plan")
    if restore_plan and isinstance(restore_plan, dict):
        timetable = restore_plan.get("timetable") or {}
        if not isinstance(timetable, dict):
            timetable = {}

    st.markdown("---")
    st.subheader("⭐ 授業入替（安全版）")
    c1, c2, c3 = st.columns([2,2,2])
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
            st.success("入替しました。")
            st.rerun()

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
            timetable.setdefault(day, {})
            minutes = PERIOD_MINUTES[day][period]
            with row_cols[j]:
                with st.container(border=True):
                    st.markdown('<div class="tt-cell">', unsafe_allow_html=True)
                    if minutes <= 0:
                        st.write("―")
                        timetable[day][period] = {"class": "", "event": {"fraction": 0.0, "content": ""}, "main": {"subject": "（空欄）", "content": ""}}
                        st.markdown('</div>', unsafe_allow_html=True)
                        continue
                    st.caption(f"{minutes}分")
                    old_cell = timetable.get(day, {}).get(period, {}) or {}
                    old_class = (old_cell.get("class") or "").strip()
                    old_event = old_cell.get("event") or {}
                    old_main = old_cell.get("main") or {}
                    old_event_frac = float(old_event.get("fraction", 0.0) or 0.0)
                    event_label_default = fraction_value_to_label(old_event_frac)
                    old_event_content = (old_event.get("content") or "").strip()
                    old_main_subject = (old_main.get("subject") or old_cell.get("subject") or "（空欄）").strip()
                    old_main_content = (old_main.get("content") or old_cell.get("content") or "").strip()
                    if teacher_type.startswith("専科"):
                        if class_candidates:
                            opts = ["（未選択）"] + class_candidates
                            idx = opts.index(old_class) if old_class in opts else 0
                            klass = st.selectbox("学級", opts, index=idx, key=f"{day}_{period}_class", label_visibility="collapsed")
                            klass = "" if klass == "（未選択）" else klass
                        else:
                            klass = old_class
                    else:
                        klass = class_name
                    event_opts = [x[0] for x in EVENT_FRACTIONS]
                    st.markdown('<div class="tt-section tt-event">🟨 学校行事（配分）</div>', unsafe_allow_html=True)
                    event_label = st.selectbox("学校行事（配分）", event_opts, index=event_opts.index(event_label_default) if event_label_default in event_opts else 0, key=f"{day}_{period}_eventfrac", label_visibility="collapsed")
                    st.markdown('<div class="tt-mini">※ 3/8・6/8 は、その分だけ学校行事扱いになります。</div>', unsafe_allow_html=True)
                    event_frac = fraction_label_to_value(event_label)
                    event_minutes = minutes * event_frac
                    remain_minutes = minutes - event_minutes
                    event_content = ""
                    if event_frac > 0:
                        st.markdown('<div class="tt-section tt-event">🟨 学校行事（内容）</div>', unsafe_allow_html=True)
                        event_content = st.text_area("学校行事 内容", value=old_event_content, key=f"{day}_{period}_eventcont", height=45, label_visibility="collapsed")
                    main_subject = "（空欄）"
                    main_content = ""
                    if remain_minutes > 0:
                        st.markdown('<div class="tt-section tt-main">🟩 残り教科等</div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="tt-mini">残り：{int(round(remain_minutes))}分（教科等）</div>', unsafe_allow_html=True)
                        main_subject = st.selectbox("残り枠の教科等", subject_options, index=subject_options.index(old_main_subject) if old_main_subject in subject_options else 0, key=f"{day}_{period}_mainsubj", label_visibility="collapsed")
                        main_content = st.text_area("残り枠の内容", value=old_main_content, key=f"{day}_{period}_maincont", height=55, label_visibility="collapsed")
                    timetable[day][period] = {"class": klass, "event": {"fraction": event_frac, "content": event_content}, "main": {"subject": main_subject, "content": main_content}}
                    st.markdown('</div>', unsafe_allow_html=True)

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
                frac = float(event.get("fraction", 0.0) or 0.0)
                frac = max(0.0, min(1.0, frac))
                if 0.0 < frac < 1.0:
                    main = cell.get("main") or {}
                    subj = (main.get("subject") or "").strip()
                    e8 = fraction_to_8th(frac)
                    r8 = 8 - e8
                    if not subj or subj == "（空欄）":
                        errors.append(f"{day} {period}: 学校行事が {e8}/8 のため、残り {r8}/8（{int(round(slot_minutes*(1-frac)))}分）の教科等が必要です。")
        return errors

    week_minutes_all = compute_week_subject_minutes(timetable, base_grade)
    subject_minutes_this_grade = week_minutes_all.get(base_grade, {})
    if teacher.strip():
        auto_plan = {"timetable": timetable}
        auto_payload = json.dumps(auto_plan, ensure_ascii=False, sort_keys=True)
        if auto_payload != st.session_state.get("last_autosave_payload", ""):
            autosave_plan(current_school_year, teacher.strip(), base_grade, class_name, teacher_type, week_str, auto_plan)
            st.session_state["last_autosave_payload"] = auto_payload
            st.session_state["autosave_notice"] = True
    if st.session_state.get("autosave_notice"):
        st.success("自動保存しました。次回は『前回の続きから再開』で復元できます。")
        st.session_state["autosave_notice"] = False

    st.markdown("---")
    st.markdown(f"#### この週の教科別 合計分数（{base_grade}）")
    for s in get_subjects_for_grade(base_grade):
        st.write(f"- {s}: {int(round(subject_minutes_this_grade.get(s, 0)))} 分")

    st.markdown("---")
    st.subheader("⭐ 時数不足警告（年度全体）")
    warn_msgs = hours_warning_messages(current_school_year)
    if warn_msgs:
        st.warning("不足/超過が検出されています（年間累積は『承認』で反映されます）。")
        for m in warn_msgs[:20]:
            st.write(f"- {m}")
    else:
        st.success("不足/超過の大きい科目は検出されませんでした。")

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
                slot_rows.append({"年度": current_school_year, "教員": teacher, "基準学年": base_grade, "担任学級": class_name, "勤務形態": teacher_type, "週": week_str, "曜日": day, "校時": period, "分": int(round(mins)), "学級": cell.get("class", ""), "教科等": "", "内容": ""})
            else:
                for seg in segs:
                    slot_rows.append({"年度": current_school_year, "教員": teacher, "基準学年": base_grade, "担任学級": class_name, "勤務形態": teacher_type, "週": week_str, "曜日": day, "校時": period, "分": int(round(seg.get("minutes", 0))), "学級": seg.get("class", ""), "教科等": seg.get("subject", ""), "内容": seg.get("content", "")})
    df_my = pd.DataFrame(slot_rows)
    my_csv = df_my.to_csv(index=False).encode("utf-8-sig")
    today_str = date.today().strftime("%Y%m%d")
    my_name = f"{teacher or 'teacher'}_{base_grade}_{week_str}_{today_str}_my_weekly_plan.csv".replace("/", "_")
    st.download_button("⬇️ この週案をCSVで保存", data=my_csv, file_name=my_name, mime="text/csv")

    st.markdown("---")
    st.subheader("⭐ 探究活動ログ（総合/学校裁量（探究）など）")
    with st.expander("➕ 探究ログを追加", expanded=False):
        theme = st.text_input("テーマ", value="", key="inq_theme")
        goals = st.text_area("ねらい（育てたい力）", value="", height=80, key="inq_goals")
        activities = st.text_area("活動（学習の流れ）", value="", height=100, key="inq_activities")
        evidence = st.text_area("証拠（成果物/写真/発表/ルーブリック等）", value="", height=80, key="inq_evidence")
        reflection = st.text_area("振り返り（児童/教師）", value="", height=100, key="inq_reflection")
        if st.button("保存する", key="inq_save_btn"):
            if not teacher.strip():
                st.error("教員名を入力してください。")
            else:
                add_inquiry_log(current_school_year, week_str, base_grade, class_name, teacher.strip(), theme, goals, activities, evidence, reflection)
                st.success("探究ログを保存しました。")

    st.markdown("---")
    st.subheader("📝 一時保存・提出")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("💾 一時保存（作業中断用）", key="draft_save_btn"):
            if not teacher.strip():
                st.error("教員名を入力してください（下書きの紐づけに必要です）。")
            else:
                plan = {"timetable": timetable}
                upsert_draft(current_school_year, teacher.strip(), base_grade, class_name, teacher_type, week_str, plan)
                st.success("一時保存しました。次回は『前回の続きから再開』または下書き一覧から復元できます。")
    with col_b:
        if st.button("✅ この内容で管理職へ提出する", key="submit_btn"):
            if not teacher.strip():
                st.error("教員名を入力してください。")
            else:
                errors = validate_timetable_for_submit(timetable)
                if errors:
                    st.error("入力に不備があります。下記を修正してください：")
                    for e in errors:
                        st.write(f"- {e}")
                else:
                    plan = {"timetable": timetable}
                    submit_plan_from_current(current_school_year, teacher.strip(), base_grade, class_name, teacher_type, week_str, plan)
                    st.success("週案を提出しました。管理職の承認をお待ちください。")

    st.markdown("---")
    st.subheader("📄 印刷・PDF保存用レイアウト（教員用）")
    if st.checkbox("この週案を印刷用に表示する（列幅が広い表示）", key="print_toggle"):
        df_print = build_print_df(timetable)
        if df_print.empty:
            st.info("有効なコマがありません。")
        else:
            st.write(f"**{current_school_year}／{base_grade}／{class_name}／{teacher}／{week_str} の週案（印刷用）**")
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
    new_year = st.text_input("追加する年度名（例：令和9年度）", value="令和9年度", key="new_year_input")
    if st.button("➕ 新年度を追加して『現在の年度』にする", key="add_new_year_btn"):
        if new_year.strip():
            set_current_school_year(new_year.strip())
            st.success(f"新年度「{new_year.strip()}」を現在の年度にしました。")
            st.rerun()
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
        df_plans = pd.DataFrame(all_rows, columns=["id","school_year","teacher","grade","class","teacher_type","week","plan_json","status","submitted_at","approved_at","approved_by"])
        st.subheader("提出状況（件数）")
        st.write({k: int(v) for k, v in df_plans["status"].value_counts().to_dict().items()})
        st.subheader("提出状況（教員別）")
        by_teacher = df_plans.groupby(["teacher","status"]).size().reset_index(name="count")
        pivot = by_teacher.pivot_table(index="teacher", columns="status", values="count", fill_value=0)
        st.dataframe(pivot.reset_index(), use_container_width=True, height=240)
        st.subheader("学校行事 自動集計（週案から抽出）")
        df_ev = aggregate_events_from_plans(all_rows)
        if df_ev.empty:
            st.info("学校行事の入力がある週案がまだありません。")
        else:
            ev_sum = df_ev.groupby(["学年"])["学校行事(45分コマ)"].sum().reset_index()
            st.dataframe(ev_sum, use_container_width=True, height=220)
    else:
        st.info("この年度の週案がまだありません。")
    st.subheader("⭐ 時数不足警告（年度全体）")
    warn = hours_warning_messages(view_year)
    if warn:
        for m in warn:
            st.warning(m)
    else:
        st.success("不足/超過の大きい科目は検出されませんでした。")
    st.subheader("⭐ 年間時数 最適化提案（今後の必要/週）")
    df_opt = build_optimization_suggestions(view_year)
    st.dataframe(df_opt.sort_values(by="今後の必要/週(45分コマ)", ascending=False), use_container_width=True, height=360)
    st.subheader("⭐ 年間時数グラフ")
    df_hours_graph = build_hours_progress_df(view_year)
    grade_for_chart = st.selectbox("グラフ表示学年", list(STANDARD_HOURS.keys()), key="hours_chart_grade")
    chart_df = df_hours_graph[df_hours_graph["学年"] == grade_for_chart][["教科等", "実施累積(45分コマ)", "標準(45分コマ)"]].copy()
    if not chart_df.empty:
        st.bar_chart(chart_df.set_index("教科等"))
