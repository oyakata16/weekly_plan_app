# ===========================================
# weekly_plan_app.py（完全版）
# 担任＋専科ハイブリッド／年度切替／下書き（上書き保存＋一覧復元）
# 学校行事：3/8・6/8・8/8（=1）＋同一コマ内「残り教科」入力（合計1を担保）
# 管理職：承認／差戻／年間累積／バックアップ／区教委提出CSV／学校行事内訳CSV
# ===========================================

import streamlit as st
import sqlite3
from datetime import date
import json
import pandas as pd
import io
import re

# ------------------------------
# 管理職用パスワード
# ------------------------------
DEFAULT_ADMIN_PASSWORD = "higakoma2025"
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)

# ------------------------------
# 既定の年度
# ------------------------------
DEFAULT_SCHOOL_YEAR = "令和8年度"

# ------------------------------
# 画面全体の見栄え調整
# ------------------------------
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

    .status-label {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        color: white;
    }
    .status-teishutsu { background-color: #f39c12; }
    .status-shonin    { background-color: #27ae60; }
    .status-sashimodoshi { background-color: #c0392b; }
    .status-draft { background-color: #2980b9; }

    @media print {
        header, footer, .stSidebar { display: none !important; }
        .main .block-container { padding-top: 0px !important; padding-bottom: 0px !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 列幅（左端の「校時」列を細め、曜日列を広めに）
COLUMN_WIDTHS = [0.7] + [1.6] * 6

# ------------------------------
# データベース
# ------------------------------
DB_PATH = "weekly_plans.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

# ------------------------------
# 学年ごとの標準時数（45分換算コマ数）
# ------------------------------
STANDARD_HOURS = {
    "1年": {
        "国語": 306, "算数": 140, "生活": 102, "音楽": 68, "図工": 68, "体育": 102,
        "道徳": 34, "特活": 34, "学校行事": 0,
        "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35,
    },
    "2年": {
        "国語": 280, "算数": 140, "生活": 102, "音楽": 68, "図工": 68, "体育": 102,
        "道徳": 35, "特活": 35, "学校行事": 0,
        "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35,
    },
    "3年": {
        "国語": 210, "社会": 70, "算数": 175, "理科": 70, "音楽": 50, "図工": 50, "体育": 105,
        "道徳": 35, "特活": 35, "外国語活動": 35, "総合的な学習の時間": 70,
        "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35,
    },
    "4年": {
        "国語": 175, "社会": 105, "算数": 175, "理科": 105, "音楽": 50, "図工": 50, "体育": 105,
        "道徳": 35, "特活": 35, "外国語活動": 35, "総合的な学習の時間": 70,
        "家庭科": 0, "クラブ": 10, "学校行事": 0, "読書科": 70,
        "学校裁量（学力向上）": 35, "学校裁量（探究）": 35,
    },
    "5年": {
        "国語": 175, "社会": 105, "算数": 175, "理科": 105, "音楽": 45, "図工": 45,
        "家庭科": 70, "体育": 90, "道徳": 35, "特活": 35, "外国語": 70,
        "総合的な学習の時間": 70, "クラブ": 10, "委員会": 10,
        "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35,
    },
    "6年": {
        "国語": 175, "社会": 105, "算数": 140, "理科": 105, "音楽": 45, "図工": 45,
        "家庭科": 70, "体育": 90, "道徳": 35, "特活": 35, "外国語": 70,
        "総合的な学習の時間": 70, "クラブ": 10, "委員会": 10,
        "学校行事": 0, "読書科": 70, "学校裁量（学力向上）": 35, "学校裁量（探究）": 35,
    },
}

def get_subjects_for_grade(grade: str):
    return list(STANDARD_HOURS[grade].keys())

ALL_SUBJECTS = sorted({subj for g in STANDARD_HOURS.values() for subj in g.keys()})

# ------------------------------
# 時間割の枠組み
# ------------------------------
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

# ------------------------------
# app_settings：現在の年度をDB保存
# ------------------------------
def ensure_settings_table():
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()

def get_setting(key: str, default: str):
    ensure_settings_table()
    cur.execute("SELECT value FROM app_settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else default

def set_setting(key: str, value: str):
    ensure_settings_table()
    cur.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    conn.commit()

def get_current_school_year():
    return get_setting("current_school_year", DEFAULT_SCHOOL_YEAR)

def set_current_school_year(year_str: str):
    set_setting("current_school_year", year_str)

# ------------------------------
# DBテーブル
# ------------------------------
def ensure_tables():
    # 提出・承認用（履歴）
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

    # 下書き（上書き保存：同一 teacher×week×school_year は1件）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS weekly_drafts (
            school_year TEXT,
            teacher TEXT,
            week TEXT,
            grade TEXT,
            class TEXT,
            teacher_type TEXT,
            plan_json TEXT,
            saved_at TEXT,
            PRIMARY KEY (school_year, teacher, week)
        )
    """)

    # 年間累積
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hours_total (
            school_year TEXT,
            grade TEXT,
            subject TEXT,
            consumed REAL,
            PRIMARY KEY(school_year, grade, subject)
        )
    """)

    # バックアップログ
    cur.execute("""
        CREATE TABLE IF NOT EXISTS backup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_year TEXT,
            created_at TEXT,
            created_by TEXT,
            filename TEXT
        )
    """)

    conn.commit()

ensure_tables()

# ------------------------------
# 年度 初期化：hours_total を0で種まき
# ------------------------------
def ensure_hours_seed(school_year: str):
    for g in STANDARD_HOURS.keys():
        for s in get_subjects_for_grade(g):
            cur.execute(
                "INSERT OR IGNORE INTO hours_total (school_year, grade, subject, consumed) VALUES (?, ?, ?, 0.0)",
                (school_year, g, s)
            )
    conn.commit()

# ------------------------------
# 45分換算
# ------------------------------
def convert_to_45(mins: float) -> float:
    return mins / 45.0

# ------------------------------
# 学級名から学年推定（3-1→3年）
# ------------------------------
def detect_grade_from_class(klass: str):
    if not klass:
        return None
    for ch in klass:
        if ch.isdigit():
            g = f"{ch}年"
            return g if g in STANDARD_HOURS else None
    return None

# ------------------------------
# parts対応：週の教科別分数集計
# ------------------------------
def compute_week_subject_minutes(timetable: dict, base_grade: str):
    """
    戻り値: { "3年": { "国語": 分数, ... }, ... }
    cell.parts があれば parts を優先（fraction×分）で集計。
    """
    result = {}

    for day in DAYS:
        for period in PERIODS:
            cell = timetable.get(day, {}).get(period)
            if not cell:
                continue

            base_minutes = PERIOD_MINUTES[day][period]
            if base_minutes <= 0:
                continue

            klass0 = cell.get("class", "")
            parts = cell.get("parts")

            # 互換：parts無しは1本扱い
            if not parts:
                parts = [{
                    "class": klass0,
                    "subject": cell.get("subject", ""),
                    "content": cell.get("content", ""),
                    "fraction": 1.0
                }]

            for p in parts:
                subject = (p.get("subject") or "").strip()
                if subject in ["", "（空欄）"]:
                    continue

                klass = (p.get("class") or "").strip() or klass0
                grade_for_slot = detect_grade_from_class(klass) or base_grade
                if grade_for_slot not in STANDARD_HOURS:
                    continue
                if subject not in STANDARD_HOURS[grade_for_slot]:
                    continue

                frac = float(p.get("fraction", 1.0))
                minutes = float(base_minutes) * frac

                result.setdefault(grade_for_slot, {})
                result[grade_for_slot][subject] = result[grade_for_slot].get(subject, 0) + minutes

    return result

# ------------------------------
# parts対応：学校行事内訳（3/8,6/8,1）を集計
# ------------------------------
def compute_school_event_breakdown(timetable: dict, base_grade: str):
    out = {}
    for day in DAYS:
        for period in PERIODS:
            cell = timetable.get(day, {}).get(period)
            if not cell:
                continue
            base_minutes = PERIOD_MINUTES[day][period]
            if base_minutes <= 0:
                continue

            klass0 = cell.get("class", "")
            parts = cell.get("parts") or [{
                "class": klass0,
                "subject": cell.get("subject", ""),
                "content": cell.get("content", ""),
                "fraction": 1.0
            }]

            for p in parts:
                if (p.get("subject") or "") != "学校行事":
                    continue

                klass = (p.get("class") or "").strip() or klass0
                grade_for_slot = detect_grade_from_class(klass) or base_grade
                if grade_for_slot not in STANDARD_HOURS:
                    continue

                frac = float(p.get("fraction", 1.0))
                minutes = float(base_minutes) * frac

                out.setdefault(grade_for_slot, {"3/8": 0, "6/8": 0, "1": 0, "minutes": 0.0})

                if abs(frac - 3/8) < 1e-9:
                    out[grade_for_slot]["3/8"] += 1
                elif abs(frac - 6/8) < 1e-9:
                    out[grade_for_slot]["6/8"] += 1
                else:
                    out[grade_for_slot]["1"] += 1

                out[grade_for_slot]["minutes"] += minutes

    return out

# ------------------------------
# 年間累積に加算
# ------------------------------
def add_hours(school_year: str, grade: str, subject: str, minutes: float):
    ensure_hours_seed(school_year)
    add_45 = convert_to_45(minutes)
    cur.execute(
        "SELECT consumed FROM hours_total WHERE school_year=? AND grade=? AND subject=?",
        (school_year, grade, subject),
    )
    row = cur.fetchone()
    if row:
        new_value = float(row[0]) + add_45
        cur.execute(
            "UPDATE hours_total SET consumed=? WHERE school_year=? AND grade=? AND subject=?",
            (new_value, school_year, grade, subject),
        )
    else:
        cur.execute(
            "INSERT INTO hours_total (school_year, grade, subject, consumed) VALUES (?, ?, ?, ?)",
            (school_year, grade, subject, add_45),
        )
    conn.commit()

# ------------------------------
# 状態ラベル
# ------------------------------
def status_badge(status: str) -> str:
    cls = "status-teishutsu"
    if status == "承認":
        cls = "status-shonin"
    elif status == "差戻":
        cls = "status-sashimodoshi"
    elif status == "下書き":
        cls = "status-draft"
    return f'<span class="status-label {cls}">{status}</span>'

# ------------------------------
# 印刷用 DataFrame（parts対応：同一マスに複数行）
# ------------------------------
def build_print_df(timetable: dict) -> pd.DataFrame:
    rows = []
    index = []

    for period in PERIODS:
        if not any(PERIOD_MINUTES[day][period] > 0 for day in DAYS):
            continue

        row = []
        for day in DAYS:
            mins = PERIOD_MINUTES[day][period]
            if mins <= 0:
                row.append("")
                continue

            cell = timetable.get(day, {}).get(period, {}) or {}
            klass0 = cell.get("class", "")
            parts = cell.get("parts") or [{
                "class": klass0,
                "subject": cell.get("subject", ""),
                "content": cell.get("content", ""),
                "fraction": 1.0
            }]

            lines = []
            for p in parts:
                subj = (p.get("subject") or "").strip()
                if subj in ["", "（空欄）"]:
                    continue
                frac = float(p.get("fraction", 1.0))
                part_min = int(round(mins * frac))
                kk = (p.get("class") or "").strip() or klass0
                cc = (p.get("content") or "").strip()

                head = ""
                if kk:
                    head += f"{kk} "
                head += subj

                if cc:
                    lines.append(f"[{part_min}分] {head}\n{cc}")
                else:
                    lines.append(f"[{part_min}分] {head}")

            row.append("\n\n".join(lines) if lines else "")

        rows.append(row)
        index.append(period)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows, index=index, columns=DAYS)

# ------------------------------
# 管理職ログイン
# ------------------------------
if "manager_authenticated" not in st.session_state:
    st.session_state["manager_authenticated"] = False

def require_manager_login():
    if st.session_state["manager_authenticated"]:
        return
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔐 管理職ログイン")
    pw = st.sidebar.text_input("管理職用パスワード", type="password")
    if st.sidebar.button("ログイン"):
        if pw == ADMIN_PASSWORD:
            st.session_state["manager_authenticated"] = True
            st.sidebar.success("管理職としてログインしました。")
        else:
            st.sidebar.error("パスワードが違います")

    if not st.session_state["manager_authenticated"]:
        st.warning("管理職専用画面です。サイドバーからパスワードを入力してください。")
        st.stop()

# ------------------------------
# タイトル・利用者区分
# ------------------------------
st.title("小学校 週の指導計画（週案）管理システム（クラウド版）")
role = st.sidebar.selectbox("利用者区分", ["教員", "管理職"])

current_school_year = get_current_school_year()
st.sidebar.markdown("---")
st.sidebar.write(f"📅 現在の年度：**{current_school_year}**")

# ======================================================
# 教員画面
# ======================================================
if role == "教員":
    st.header("📘 週案の作成・提出（教員用）")
    st.caption(f"提出先年度：{current_school_year}（管理職が設定）")

    teacher = st.text_input("教員名")
    teacher_type = st.radio("勤務形態", ["担任", "専科（音楽・家庭科など）"])

    grade = st.selectbox("基準学年", list(STANDARD_HOURS.keys()))
    base_grade = grade
    class_name = st.text_input("自分の担任学級（例：3-1）※担任でなければ空欄可")
    week = st.date_input("対象週（週の初日：月曜日など）", value=date.today())

    # ---- 下書き一覧 → 復元
    st.markdown("---")
    st.subheader("🗂 下書きの復元（教員用）")
    st.caption("※ 同一『教員×週×年度』の下書きは1件（上書き保存）です。")

    def list_my_drafts(school_year: str, teacher_name: str):
        if not teacher_name.strip():
            return []
        cur.execute("""
            SELECT school_year, teacher, week, grade, class, teacher_type, saved_at
            FROM weekly_drafts
            WHERE school_year=? AND teacher=?
            ORDER BY saved_at DESC
        """, (school_year, teacher_name.strip()))
        return cur.fetchall()

    def load_draft(school_year: str, teacher_name: str, week_str: str):
        cur.execute("""
            SELECT plan_json, grade, class, teacher_type
            FROM weekly_drafts
            WHERE school_year=? AND teacher=? AND week=?
            LIMIT 1
        """, (school_year, teacher_name.strip(), week_str))
        row = cur.fetchone()
        if not row:
            return None
        plan_json, g, c, tt = row
        try:
            plan = json.loads(plan_json) if plan_json else {}
        except Exception:
            plan = {}
        return {"plan": plan, "grade": g, "class": c, "teacher_type": tt}

    drafts = list_my_drafts(current_school_year, teacher or "")
    if drafts:
        options = [f"{r[2]}（{r[3]} {r[4]} / {r[5]}） 保存:{r[6]}" for r in drafts]
        pick = st.selectbox("自分の下書き一覧", ["（選択してください）"] + options)
        if pick != "（選択してください）":
            idx = options.index(pick)
            week_str = drafts[idx][2]
            if st.button("🔄 選択した下書きを復元する"):
                loaded = load_draft(current_school_year, teacher or "", week_str)
                if loaded:
                    st.session_state["restore_draft_plan"] = loaded["plan"]
                    st.session_state["restore_draft_week"] = week_str
                    st.success("下書きを復元しました。下の時間割入力欄に反映します。")
                    st.rerun()
    else:
        st.info("（下書きはまだありません。教員名を入力すると一覧が出ます）")

    # ---- 担任／専科の選択肢
    if teacher_type == "担任":
        subject_options = ["（空欄）"] + get_subjects_for_grade(base_grade)
        st.caption("※ 担任は、その学年で扱う教科のみ選択できます。")
        class_candidates = [class_name] if class_name else []
    else:
        subject_options = ["（空欄）"] + ALL_SUBJECTS
        st.caption("※ 専科は、各コマで学級・教科を自由に選べます。")
        st.info("この週に指導する学級をカンマ区切りで入力してください。（例：3-1,3-2,4-1）")
        classes_input = st.text_input("指導学級一覧", value=class_name)
        class_candidates = [c.strip() for c in classes_input.split(",") if c.strip()]
        if class_candidates:
            st.caption("この週に指導する学級：" + "、".join(class_candidates))
        else:
            st.caption("※ 学級が未入力の場合、学級欄は空欄のままとなります。")

    # ---- 復元した下書きがあれば timetable の初期値に利用
    restored_plan = st.session_state.get("restore_draft_plan")
    restored_week = st.session_state.get("restore_draft_week")
    restore_timetable = {}
    if restored_plan and restored_week == str(week):
        restore_timetable = restored_plan.get("timetable", {}) or {}

    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    st.caption("行：校時／列：曜日。各マスで「学級（専科）」「教科等」「内容」を入力します。")
    st.caption("※ 学校行事を 3/8・6/8 で入力した場合、そのコマの『残り教科』を入力できます（合計1）。")

    timetable = {}

    header_cols = st.columns(COLUMN_WIDTHS)
    header_cols[0].write("　")
    for i, day in enumerate(DAYS, start=1):
        header_cols[i].write(f"**{day}**")

    for period in PERIODS:
        if not any(PERIOD_MINUTES[day][period] > 0 for day in DAYS):
            continue

        row_cols = st.columns(COLUMN_WIDTHS)
        row_cols[0].write(f"**{period}**")

        for j, day in enumerate(DAYS, start=1):
            timetable.setdefault(day, {})

            minutes = PERIOD_MINUTES[day][period]
            restore_cell = (restore_timetable.get(day, {}).get(period, {}) or {})

            with row_cols[j]:
                if minutes <= 0:
                    st.write("―")
                    cell = {"class": "", "subject": "（空欄）", "content": "", "parts": []}
                else:
                    st.caption(f"{minutes}分")

                    # class
                    if teacher_type.startswith("専科"):
                        if class_candidates:
                            klass = st.selectbox(
                                "学級",
                                ["（未選択）"] + class_candidates,
                                key=f"{day}_{period}_class",
                                index=(
                                    (["（未選択）"] + class_candidates).index(restore_cell.get("class"))
                                    if restore_cell.get("class") in (["（未選択）"] + class_candidates) else 0
                                ),
                                label_visibility="collapsed",
                            )
                            klass = "" if klass == "（未選択）" else klass
                        else:
                            klass = ""
                    else:
                        klass = class_name

                    # subject
                    restore_subject = restore_cell.get("subject", "（空欄）")
                    if restore_subject not in subject_options:
                        restore_subject = "（空欄）"

                    subject = st.selectbox(
                        "教科等",
                        subject_options,
                        key=f"{day}_{period}_subject",
                        index=subject_options.index(restore_subject),
                        label_visibility="collapsed",
                    )

                    # content
                    restore_content = restore_cell.get("content", "")
                    content = st.text_area(
                        "内容",
                        key=f"{day}_{period}_content",
                        value=restore_content,
                        height=60,
                        label_visibility="collapsed",
                    )

                    # parts（学校行事の分割対応）
                    parts = None
                    if subject == "学校行事":
                        # restore fraction
                        restore_parts = restore_cell.get("parts") or []
                        restore_frac = 1.0
                        if restore_parts:
                            for p in restore_parts:
                                if p.get("subject") == "学校行事":
                                    restore_frac = float(p.get("fraction", 1.0))

                        if abs(restore_frac - 3/8) < 1e-9:
                            restore_label = "3/8"
                        elif abs(restore_frac - 6/8) < 1e-9:
                            restore_label = "6/8"
                        else:
                            restore_label = "8/8（1）"

                        frac_label = st.selectbox(
                            "学校行事の計上",
                            ["8/8（1）", "3/8", "6/8"],
                            key=f"{day}_{period}_event_frac",
                            index=["8/8（1）", "3/8", "6/8"].index(restore_label),
                            label_visibility="collapsed",
                        )

                        if frac_label == "3/8":
                            frac_event = 3/8
                        elif frac_label == "6/8":
                            frac_event = 6/8
                        else:
                            frac_event = 1.0

                        if frac_event < 1.0:
                            remain_frac = 1.0 - frac_event
                            st.caption(f"このコマの残り：{int(round(remain_frac*8))}/8（自動）")

                            # restore remain
                            restore_rem_subj = "（空欄）"
                            restore_rem_cont = ""
                            for p in restore_parts:
                                if p.get("subject") != "学校行事":
                                    restore_rem_subj = p.get("subject", "（空欄）")
                                    restore_rem_cont = p.get("content", "")
                                    break

                            remain_opts = ["（空欄）"] + (get_subjects_for_grade(base_grade) if teacher_type == "担任" else ALL_SUBJECTS)
                            if restore_rem_subj not in remain_opts:
                                restore_rem_subj = "（空欄）"

                            remain_subject = st.selectbox(
                                "残りの教科等",
                                remain_opts,
                                key=f"{day}_{period}_remain_subject",
                                index=remain_opts.index(restore_rem_subj),
                                label_visibility="collapsed",
                            )
                            remain_content = st.text_area(
                                "残りの内容",
                                key=f"{day}_{period}_remain_content",
                                value=restore_rem_cont,
                                height=60,
                                label_visibility="collapsed",
                            )

                            parts = [
                                {"class": klass, "subject": "学校行事", "content": content, "fraction": frac_event},
                                {"class": klass, "subject": remain_subject, "content": remain_content, "fraction": remain_frac},
                            ]
                        else:
                            parts = [{"class": klass, "subject": "学校行事", "content": content, "fraction": 1.0}]
                    else:
                        parts = [{"class": klass, "subject": subject, "content": content, "fraction": 1.0}]

                    cell = {"class": klass, "subject": subject, "content": content, "parts": parts}

            timetable[day][period] = cell

    # ---- 集計表示（基準学年）
    week_minutes_all = compute_week_subject_minutes(timetable, base_grade)
    subject_minutes_this_grade = week_minutes_all.get(base_grade, {})

    st.markdown(f"#### この週の教科別 合計分数（{base_grade}）")
    for s in get_subjects_for_grade(base_grade):
        mins = int(round(subject_minutes_this_grade.get(s, 0)))
        st.write(f"- {s}: {mins} 分")

    # ---- 下書き：上書き保存
    st.markdown("---")
    st.subheader("📝 下書き（上書き保存）")
    st.caption("※ 同一『教員×週×年度』は1件です。保存すると自動的に上書きされます。")

    def save_draft(school_year: str, teacher_name: str, week_str: str, grade: str, class_name: str, teacher_type: str, plan: dict):
        cur.execute("""
            INSERT INTO weekly_drafts (school_year, teacher, week, grade, class, teacher_type, plan_json, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, DATETIME('now'))
            ON CONFLICT(school_year, teacher, week) DO UPDATE SET
                grade=excluded.grade,
                class=excluded.class,
                teacher_type=excluded.teacher_type,
                plan_json=excluded.plan_json,
                saved_at=DATETIME('now')
        """, (
            school_year, teacher_name.strip(), week_str, grade, class_name, teacher_type,
            json.dumps(plan, ensure_ascii=False)
        ))
        conn.commit()

    col_d1, col_d2 = st.columns([2, 3])
    with col_d1:
        if st.button("💾 下書きを上書き保存"):
            if not teacher.strip():
                st.error("教員名を入力してください（下書き保存に必要です）。")
            else:
                plan = {"timetable": timetable}
                save_draft(current_school_year, teacher, str(week), base_grade, class_name, teacher_type, plan)
                st.success("下書きを保存（上書き）しました。")

    with col_d2:
        st.info("下書きを復元したい場合は、画面上部の『下書き一覧』から選んで復元できます。")

    # ---- 印刷
    st.markdown("#### 📄 印刷・PDF保存用レイアウト（教員用）")
    if st.checkbox("この週案を印刷用に表示する"):
        df_print = build_print_df(timetable)
        if df_print.empty:
            st.info("有効なコマがありません。")
        else:
            st.write(f"**{current_school_year}／{base_grade}／{class_name}／{teacher}／{week} の週案（印刷用）**")
            st.table(df_print)
            st.info("ブラウザの印刷機能から PDF 保存・印刷を行ってください。")

    # ---- 提出
    if st.button("✅ この内容で管理職へ提出する"):
        if not teacher.strip():
            st.error("教員名を入力してください（提出に必要です）。")
        else:
            plan = {"timetable": timetable}
            cur.execute("""
                INSERT INTO weekly_plans
                  (school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at)
                VALUES
                  (?, ?, ?, ?, ?, ?, ?, '提出', DATETIME('now'))
            """, (
                current_school_year,
                teacher.strip(),
                base_grade,
                class_name,
                teacher_type,
                str(week),
                json.dumps(plan, ensure_ascii=False),
            ))
            conn.commit()
            st.success("週案を提出しました。管理職の承認をお待ちください。")

# ======================================================
# 管理職画面
# ======================================================
if role == "管理職":
    require_manager_login()

    st.header("🧭 年度の管理（管理職）")

    # 年度候補（DBから集める）
    years = {get_current_school_year(), DEFAULT_SCHOOL_YEAR}
    try:
        cur.execute("SELECT DISTINCT school_year FROM weekly_plans")
        years |= {r[0] for r in cur.fetchall() if r and r[0]}
    except Exception:
        pass
    try:
        cur.execute("SELECT DISTINCT school_year FROM hours_total")
        years |= {r[0] for r in cur.fetchall() if r and r[0]}
    except Exception:
        pass

    years_list = sorted(list(years))

    coly1, coly2, coly3 = st.columns([2, 2, 2])
    with coly1:
        view_year = st.selectbox(
            "表示する年度",
            years_list,
            index=years_list.index(get_current_school_year()) if get_current_school_year() in years_list else 0
        )
    with coly2:
        st.write("現在の年度")
        st.write(f"**{get_current_school_year()}**")
    with coly3:
        if st.button("この表示年度を『現在の年度』にする"):
            set_current_school_year(view_year)
            st.success(f"現在の年度を「{view_year}」に変更しました。")
            st.rerun()

    st.markdown("##### 新年度を追加")
    new_year = st.text_input("追加する年度名（例：令和9年度）", value="令和9年度")
    if st.button("➕ 新年度を追加して『現在の年度』にする"):
        if new_year.strip():
            set_current_school_year(new_year.strip())
            ensure_hours_seed(new_year.strip())
            st.success(f"新年度「{new_year.strip()}」を現在の年度にしました。")
            st.rerun()

    # 年度の種まき
    ensure_hours_seed(view_year)

    st.markdown("---")
    st.header("📝 提出された週案一覧（管理職用）")
    st.caption("※ この画面の一覧・集計は「表示する年度」に基づきます。")

    cur.execute("""
        SELECT id, school_year, teacher, grade, class, teacher_type, week,
               plan_json, status, submitted_at, approved_at, approved_by
        FROM weekly_plans
        WHERE school_year=?
        ORDER BY id DESC
    """, (view_year,))
    all_rows = cur.fetchall()

    counts = {"提出": 0, "承認": 0, "差戻": 0}
    for r in all_rows:
        stt = r[8]
        if stt in counts:
            counts[stt] += 1

    st.markdown("#### 状態別件数")
    st.write(f"- 提出：{counts['提出']} 件")
    st.write(f"- 承認：{counts['承認']} 件")
    st.write(f"- 差戻：{counts['差戻']} 件")

    grade_list = sorted({r[3] for r in all_rows if r[3]})
    teacher_list = sorted({r[2] for r in all_rows if r[2]})
    week_list = sorted({r[6] for r in all_rows if r[6]}, reverse=True)

    st.markdown("#### 表示フィルタ")
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filter_status = st.selectbox("状態", ["すべて", "提出", "承認", "差戻"])
    with col_f2:
        grade_filter = st.selectbox("学年", ["すべて"] + grade_list)
    with col_f3:
        teacher_filter = st.selectbox("教員", ["すべて"] + teacher_list)

    col_f4, col_f5 = st.columns(2)
    with col_f4:
        week_filter = st.selectbox("週", ["すべて"] + week_list)
    with col_f5:
        only_unapproved = st.checkbox("未承認（提出＋差戻）のみ表示する", value=False)

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
        rows = [r for r in rows if r[8] != "承認"]

    if not rows:
        st.info("該当する週案はありません。")
    else:
        st.caption("※ 各行をクリックすると詳細が表示されます。")

    for (
        wid, school_year, teacher, grade, class_name, teacher_type, week,
        plan_json, status, submitted_at, approved_at, approved_by
    ) in rows:

        try:
            plan = json.loads(plan_json) if plan_json else {}
        except Exception:
            plan = {}

        timetable = plan.get("timetable", {}) or {}
        week_minutes_all = compute_week_subject_minutes(timetable, grade)

        badge_html = status_badge(status)
        title = f"ID:{wid} / {school_year} / {week} / {grade} / {class_name} / {teacher} / 状態：{status}"

        with st.expander(title):
            st.markdown(f"状態：{badge_html}", unsafe_allow_html=True)
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
            header_cols = st.columns(COLUMN_WIDTHS)
            header_cols[0].write("　")
            for i, day in enumerate(DAYS, start=1):
                header_cols[i].write(f"**{day}**")

            for period in PERIODS:
                if not any(PERIOD_MINUTES[day][period] > 0 for day in DAYS):
                    continue
                row_cols = st.columns(COLUMN_WIDTHS)
                row_cols[0].write(f"**{period}**")
                for j, day in enumerate(DAYS, start=1):
                    with row_cols[j]:
                        mins = PERIOD_MINUTES[day][period]
                        if mins <= 0:
                            st.write("―")
                            continue
                        cell = timetable.get(day, {}).get(period, {}) or {}
                        klass0 = cell.get("class", "")
                        parts = cell.get("parts") or [{
                            "class": klass0,
                            "subject": cell.get("subject", ""),
                            "content": cell.get("content", ""),
                            "fraction": 1.0
                        }]

                        st.caption(f"{mins}分")
                        lines = []
                        for p in parts:
                            subj = (p.get("subject") or "").strip()
                            if subj in ["", "（空欄）"]:
                                continue
                            frac = float(p.get("fraction", 1.0))
                            part_min = int(round(mins * frac))
                            kk = (p.get("class") or "").strip() or klass0
                            cont = (p.get("content") or "").strip()
                            head = f"{kk} " if kk else ""
                            head += subj
                            if cont:
                                lines.append(f"[{part_min}分] {head}\n{cont}")
                            else:
                                lines.append(f"[{part_min}分] {head}")
                        st.write("\n\n".join(lines) if lines else "")

            st.markdown("#### 📄 印刷・PDF保存用レイアウト（この週案）")
            df_print = build_print_df(timetable)
            if df_print.empty:
                st.info("有効なコマがありません。")
            else:
                st.table(df_print)
                st.caption("ブラウザの印刷機能から PDF 保存・印刷してください。")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"✅ 承認する（ID:{wid}）", key=f"approve_{wid}"):
                    if status != "承認":
                        for g in week_minutes_all:
                            for subj, mins in week_minutes_all[g].items():
                                add_hours(view_year, g, subj, mins)

                        cur.execute("""
                            UPDATE weekly_plans
                            SET status='承認',
                                approved_at=DATETIME('now'),
                                approved_by=?
                            WHERE id=?
                        """, ("管理職", wid))
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
                        st.warning("差戻にしました。教員側で修正して再提出してもらってください。")
                        st.rerun()
                    else:
                        st.info("すでに差戻済みです。")

    # 年間累積（年度view_year）
    st.header(f"📊 年間累積時数の状況（{view_year}）")
    ensure_hours_seed(view_year)

    for g in STANDARD_HOURS.keys():
        st.subheader(f"{g}の時数状況")
        rows_table = []
        for subj in get_subjects_for_grade(g):
            std = float(STANDARD_HOURS[g][subj])
            cur.execute(
                "SELECT consumed FROM hours_total WHERE school_year=? AND grade=? AND subject=?",
                (view_year, g, subj),
            )
            row = cur.fetchone()
            used = float(row[0]) if row else 0.0
            remain = std - used
            rows_table.append({
                "教科等": subj,
                "標準（45分コマ）": round(std, 1),
                "実施累積（45分コマ）": round(used, 1),
                "残り（45分コマ）": round(remain, 1),
            })
        st.table(rows_table)

    # ------------------------------------------------------
    # 学校行事 内訳（年累計：承認済み週案から集計）
    # ------------------------------------------------------
    st.markdown("---")
    st.header(f"🎪 学校行事の内訳（{view_year}・承認済みから集計）")
    st.caption("3/8・6/8・8/8（=1）の回数と、実分（分）を表示します。")

    cur.execute("""
        SELECT grade, plan_json
        FROM weekly_plans
        WHERE school_year=? AND status='承認'
    """, (view_year,))
    approved_plans = cur.fetchall()

    agg = {g: {"3/8": 0, "6/8": 0, "1": 0, "minutes": 0.0} for g in STANDARD_HOURS.keys()}
    for base_g, pjson in approved_plans:
        try:
            plan = json.loads(pjson) if pjson else {}
        except Exception:
            plan = {}
        tt = plan.get("timetable", {}) or {}
        bd = compute_school_event_breakdown(tt, base_g)
        for gg, d in bd.items():
            agg.setdefault(gg, {"3/8": 0, "6/8": 0, "1": 0, "minutes": 0.0})
            agg[gg]["3/8"] += d["3/8"]
            agg[gg]["6/8"] += d["6/8"]
            agg[gg]["1"] += d["1"]
            agg[gg]["minutes"] += d["minutes"]

    rows_event = []
    for gg in STANDARD_HOURS.keys():
        rows_event.append({
            "学年": gg,
            "学校行事 3/8 回数": agg.get(gg, {}).get("3/8", 0),
            "学校行事 6/8 回数": agg.get(gg, {}).get("6/8", 0),
            "学校行事 8/8(=1) 回数": agg.get(gg, {}).get("1", 0),
            "学校行事 合計（分）": int(round(agg.get(gg, {}).get("minutes", 0.0))),
        })
    df_event = pd.DataFrame(rows_event)
    st.table(df_event)

    event_csv = df_event.to_csv(index=False).encode("utf-8-sig")
    today_str = date.today().strftime("%Y%m%d")
    st.download_button(
        label="⬇️ 学校行事 内訳CSVをダウンロード",
        data=event_csv,
        file_name=f"{view_year.replace(' ', '')}_学校行事内訳_{today_str}.csv".replace("/", "_"),
        mime="text/csv",
    )

    # ------------------------------------------------------
    # 🧰 バックアップ（Excel/CSV）
    # ------------------------------------------------------
    st.markdown("---")
    st.header("🧰 バックアップ（Excel/CSV ダウンロード）")
    st.caption(f"対象年度：{view_year}　（管理職のみ実行）")

    def get_last_backup_date(school_year: str):
        cur.execute(
            "SELECT created_at FROM backup_log WHERE school_year=? ORDER BY id DESC LIMIT 1",
            (school_year,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def log_backup(school_year: str, created_by: str, filename: str):
        cur.execute(
            "INSERT INTO backup_log (school_year, created_at, created_by, filename) VALUES (?, DATETIME('now'), ?, ?)",
            (school_year, created_by, filename)
        )
        conn.commit()

    def fetch_all_weekly_plans_for_year(school_year: str):
        cur.execute("""
            SELECT id, school_year, teacher, grade, class, teacher_type, week, plan_json, status,
                   submitted_at, approved_at, approved_by
            FROM weekly_plans
            WHERE school_year=?
            ORDER BY id DESC
        """, (school_year,))
        return cur.fetchall()

    def fetch_hours_total_for_year(school_year: str):
        ensure_hours_seed(school_year)
        cur.execute("""
            SELECT school_year, grade, subject, consumed
            FROM hours_total
            WHERE school_year=?
            ORDER BY grade, subject
        """, (school_year,))
        return cur.fetchall()

    def flatten_plans_to_rows(plans):
        plan_rows = []
        slot_rows = []

        for (wid, sy, teacher, grade, class_name, teacher_type, week, plan_json, status,
             submitted_at, approved_at, approved_by) in plans:

            plan_rows.append({
                "id": wid,
                "school_year": sy,
                "teacher": teacher,
                "grade": grade,
                "class": class_name,
                "teacher_type": teacher_type,
                "week": week,
                "status": status,
                "submitted_at": submitted_at,
                "approved_at": approved_at,
                "approved_by": approved_by,
            })

            try:
                plan = json.loads(plan_json) if plan_json else {}
            except Exception:
                plan = {}
            timetable = plan.get("timetable", {}) or {}

            for day in DAYS:
                for period in PERIODS:
                    cell = timetable.get(day, {}).get(period, {}) or {}
                    base_minutes = PERIOD_MINUTES.get(day, {}).get(period, 0)
                    klass0 = cell.get("class", "")
                    parts = cell.get("parts") or [{
                        "class": klass0,
                        "subject": cell.get("subject", ""),
                        "content": cell.get("content", ""),
                        "fraction": 1.0
                    }]

                    # partsを1行ずつ出す（分割対応）
                    for idx, p in enumerate(parts, start=1):
                        frac = float(p.get("fraction", 1.0))
                        part_minutes = base_minutes * frac
                        slot_rows.append({
                            "plan_id": wid,
                            "school_year": sy,
                            "week": week,
                            "teacher": teacher,
                            "base_grade": grade,
                            "base_class": class_name,
                            "teacher_type": teacher_type,
                            "status": status,
                            "day": day,
                            "period": period,
                            "slot_minutes_base": base_minutes,
                            "part_no": idx,
                            "fraction": frac,
                            "minutes": round(part_minutes, 2),
                            "class": p.get("class", "") or klass0,
                            "subject": p.get("subject", ""),
                            "content": p.get("content", ""),
                        })

        return pd.DataFrame(plan_rows), pd.DataFrame(slot_rows)

    def build_hours_progress_df(school_year: str, hours_total_rows):
        out = []
        consumed_map = {(g, s): float(c) for (_sy, g, s, c) in hours_total_rows}
        for gg in STANDARD_HOURS.keys():
            for ss in get_subjects_for_grade(gg):
                std = float(STANDARD_HOURS[gg][ss])
                used = float(consumed_map.get((gg, ss), 0.0))
                remain = std - used
                pct = (used / std * 100.0) if std > 0 else 0.0
                out.append({
                    "school_year": school_year,
                    "grade": gg,
                    "subject": ss,
                    "standard_45": round(std, 2),
                    "consumed_45": round(used, 2),
                    "remain_45": round(remain, 2),
                    "progress_pct": round(pct, 1),
                })
        return pd.DataFrame(out)

    def to_excel_bytes(dfs: dict):
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            for sheet, df in dfs.items():
                df.to_excel(writer, index=False, sheet_name=str(sheet)[:31])
        bio.seek(0)
        return bio.getvalue()

    def safe_year_str(s: str):
        return str(s).replace(" ", "").replace("/", "_").replace("\\", "_")

    last_backup = get_last_backup_date(view_year)
    if last_backup:
        st.write(f"前回バックアップ：{last_backup}")
    else:
        st.warning("まだバックアップが作成されていません。初回は必ず作成してください。")

    st.session_state.setdefault("backup_excel_bytes", None)
    st.session_state.setdefault("backup_csv_pack", None)
    st.session_state.setdefault("backup_filename", None)

    if st.button("🟦 バックアップを作成（今日の日付で生成）"):
        plans = fetch_all_weekly_plans_for_year(view_year)
        df_plans, df_slots = flatten_plans_to_rows(plans)

        hours_rows = fetch_hours_total_for_year(view_year)
        df_hours = build_hours_progress_df(view_year, hours_rows)

        today_str = date.today().strftime("%Y%m%d")
        filename = f"{safe_year_str(view_year)}_weekly_plan_backup_{today_str}.xlsx"

        excel_bytes = to_excel_bytes({
            "週案一覧": df_plans,
            "時間割（コマ明細_parts）": df_slots,
            "年間累積（進捗）": df_hours,
            "学校行事内訳": df_event,
        })

        st.session_state["backup_excel_bytes"] = excel_bytes
        st.session_state["backup_csv_pack"] = {
            "weekly_plans": df_plans.to_csv(index=False).encode("utf-8-sig"),
            "weekly_slots_parts": df_slots.to_csv(index=False).encode("utf-8-sig"),
            "hours_progress": df_hours.to_csv(index=False).encode("utf-8-sig"),
            "event_breakdown": df_event.to_csv(index=False).encode("utf-8-sig"),
        }
        st.session_state["backup_filename"] = filename

        log_backup(view_year, created_by="管理職", filename=filename)
        st.success("バックアップを作成しました。下のボタンからダウンロードしてください。")

    if st.session_state["backup_excel_bytes"]:
        today_str = date.today().strftime("%Y%m%d")
        st.download_button(
            label="⬇️ バックアップ一括（Excel）をダウンロード",
            data=st.session_state["backup_excel_bytes"],
            file_name=st.session_state["backup_filename"] or f"{safe_year_str(view_year)}_weekly_plan_backup_{today_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        csv_pack = st.session_state["backup_csv_pack"] or {}
        st.download_button(
            label="⬇️ 週案一覧（CSV）",
            data=csv_pack.get("weekly_plans", b""),
            file_name=f"{safe_year_str(view_year)}_weekly_plans_{today_str}.csv",
            mime="text/csv",
        )
        st.download_button(
            label="⬇️ 時間割（コマ明細_parts）（CSV）",
            data=csv_pack.get("weekly_slots_parts", b""),
            file_name=f"{safe_year_str(view_year)}_weekly_slots_parts_{today_str}.csv",
            mime="text/csv",
        )
        st.download_button(
            label="⬇️ 年間累積（進捗）（CSV）",
            data=csv_pack.get("hours_progress", b""),
            file_name=f"{safe_year_str(view_year)}_hours_progress_{today_str}.csv",
            mime="text/csv",
        )
        st.download_button(
            label="⬇️ 学校行事内訳（CSV）",
            data=csv_pack.get("event_breakdown", b""),
            file_name=f"{safe_year_str(view_year)}_event_breakdown_{today_str}.csv",
            mime="text/csv",
        )

    # ------------------------------------------------------
    # 🏛 区教委提出用（年間時数 まとめCSV）
    # ------------------------------------------------------
    st.markdown("---")
    st.header("🏛 区教委提出用（年間時数 まとめCSV）")
    st.caption(f"対象年度：{view_year}（学年×教科の標準・累積・残りを1本に整形）")

    hours_rows = fetch_hours_total_for_year(view_year)
    consumed_map = {(g, s): float(c) for (_sy, g, s, c) in hours_rows}

    out_rows = []
    for gg in STANDARD_HOURS.keys():
        for ss in get_subjects_for_grade(gg):
            std = float(STANDARD_HOURS[gg][ss])
            used = float(consumed_map.get((gg, ss), 0.0))
            remain = std - used
            pct = (used / std * 100.0) if std > 0 else 0.0

            out_rows.append({
                "年度": view_year,
                "学年": gg,
                "教科等": ss,
                "標準（45分コマ）": round(std, 2),
                "実施累積（45分コマ）": round(used, 2),
                "残り（45分コマ）": round(remain, 2),
                "進捗（％）": round(pct, 1),
            })

    df_submit = pd.DataFrame(out_rows)[
        ["年度", "学年", "教科等", "標準（45分コマ）", "実施累積（45分コマ）", "残り（45分コマ）", "進捗（％）"]
    ]

    with st.expander("内容を表示（確認用）", expanded=False):
        st.dataframe(df_submit, use_container_width=True)

    today_str = date.today().strftime("%Y%m%d")
    submit_csv = df_submit.to_csv(index=False).encode("utf-8-sig")

    def to_reiwa_short(year_str: str) -> str:
        m = re.search(r"令和\s*([0-9]+)\s*年度", year_str)
        return f"R{m.group(1)}" if m else year_str.replace("年度", "")

    school_short = "東小松川小学校"
    reiwa_short = to_reiwa_short(view_year)
    submit_name = f"{reiwa_short}_年間指導時数集計_{school_short}_{today_str}.csv".replace("/", "_")

    st.download_button(
        label="⬇️ 区教委提出用CSVをダウンロード",
        data=submit_csv,
        file_name=submit_name,
        mime="text/csv",
    )
