# weekly_plan_app.py （印刷完成版・完全動作：学校行事UI復元＋二段入力 安定版）
# 担任＋専科ハイブリッド＋年度切替＋下書き(上書き保存/復元)
# 学校行事：3/8・6/8・8/8(=1)＋残り教科入力（合計8/8必須）
# 印刷：同一マス2段表示＋st.dataframe＋印刷CSS
# バックアップ（管理職のみ）＋区教委提出用 年間時数まとめCSV
#
# ★追加（今回）：
# ① 時間割入力の「枠線（表の罫線）」：各マスを st.container(border=True) で囲む＋CSSで黒枠強制
# ② 「学校行事（配分）」と「残り教科等」を色ラベルで明確に区別
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
# 既定の年度（既存データはこれとして引き継ぎ）
# ------------------------------
DEFAULT_SCHOOL_YEAR = "令和8年度"

# ------------------------------
# 画面全体の見栄え調整（印刷完成版）
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
    .status-shitagaki { background-color: #7f8c8d; }

    /* dataframe の折り返し強化（表示・印刷共通） */
    .dataframe td, .dataframe th {
        white-space: pre-wrap !important;
        word-break: break-word !important;
        line-height: 1.35 !important;
        vertical-align: top !important;
    }

    /* --- 既存：時間割入力セルの見出し用（色分け） --- */
    .tt-sec-event{
        background: #fff4cc;
        border: 1px solid #f2d27a;
        padding: 4px 6px;
        border-radius: 6px;
        font-size: 12px;
        margin: 6px 0 6px 0;
        font-weight: 700;
    }
    .tt-sec-main{
        background: #e7f0ff;
        border: 1px solid #b5cffc;
        padding: 4px 6px;
        border-radius: 6px;
        font-size: 12px;
        margin: 6px 0 6px 0;
        font-weight: 700;
    }
    .tt-mini{
        font-size: 12px !important;
        color: #555;
        margin-top: 2px;
        margin-bottom: 6px;
    }

    /* --- 時間割入力の枠線（st.container(border=True) を“表の枠”として強調） --- */
    div[data-testid="stVerticalBlockBorderWrapper"]{
        border: 1px solid #000 !important;
        border-radius: 0px !important;
        box-shadow: none !important;
    }

    @media print {
        header, footer, .stSidebar { display: none !important; }
        .main .block-container { padding-top: 0px !important; padding-bottom: 0px !important; }

        table {
            width: 100% !important;
            font-size: 11px !important;
            border-collapse: collapse !important;
        }
        th, td {
            border: 1px solid #000 !important;
            padding: 4px !important;
            white-space: pre-wrap !important;
        }
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
# アプリ設定（現在の年度をDBに保存：全端末で共通）
# ------------------------------
def ensure_settings_table():
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
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
        (key, value),
    )
    conn.commit()


def get_current_school_year():
    return get_setting("current_school_year", DEFAULT_SCHOOL_YEAR)


def set_current_school_year(year_str: str):
    set_setting("current_school_year", year_str)


# ------------------------------
# 週案テーブル（年度列あり）
# ------------------------------
cur.execute(
    """
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
    """
)

# 既存テーブルに不足列があれば追加（古いDBからの移行用）
for col in ["school_year", "class", "teacher_type", "submitted_at", "approved_at", "approved_by"]:
    try:
        cur.execute(f"ALTER TABLE weekly_plans ADD COLUMN {col} TEXT")
    except sqlite3.OperationalError:
        pass

# 既存データの school_year が空なら既定年度で埋める
try:
    cur.execute(
        "UPDATE weekly_plans SET school_year=? WHERE school_year IS NULL OR school_year=''",
        (DEFAULT_SCHOOL_YEAR,),
    )
    conn.commit()
except Exception:
    pass

# ------------------------------
# 年間累積時数テーブル（年度列あり）
# ------------------------------
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS hours_total (
        school_year TEXT,
        grade TEXT,
        subject TEXT,
        consumed REAL,
        PRIMARY KEY(school_year, grade, subject)
    )
    """
)

try:
    cur.execute("ALTER TABLE hours_total ADD COLUMN school_year TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    cur.execute(
        "UPDATE hours_total SET school_year=? WHERE school_year IS NULL OR school_year=''",
        (DEFAULT_SCHOOL_YEAR,),
    )
    conn.commit()
except Exception:
    pass

conn.commit()

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
# 学校行事（3/8・6/8・8/8）
# ------------------------------
EVENT_FRACTIONS = [
    ("なし", 0.0),
    ("3/8", 3.0 / 8.0),
    ("6/8", 6.0 / 8.0),
    ("8/8（＝1）", 1.0),
]


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


# ------------------------------
# 分 → 45分コマ換算
# ------------------------------
def convert_to_45(mins: float) -> float:
    return float(mins) / 45.0


# ------------------------------
# 学級名から学年を推定（例：3-1 → 3年）
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
# 状態ラベル（HTML）
# ------------------------------
def status_badge(status: str) -> str:
    cls = "status-teishutsu"
    if status == "承認":
        cls = "status-shonin"
    elif status == "差戻":
        cls = "status-sashimodoshi"
    elif status == "下書き":
        cls = "status-shitagaki"
    return f'<span class="status-label {cls}">{status}</span>'


# ------------------------------
# 年間累積時数を加算（年度込み）
# ------------------------------
def add_hours(school_year: str, grade: str, subject: str, minutes: float):
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
# timetable セルの正規化（学校行事＋残り教科 2段）
# ------------------------------
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

    # 学校行事
    if event_minutes > 0:
        segs.append(
            {
                "class": klass,
                "subject": "学校行事",
                "content": (event.get("content") or "").strip(),
                "minutes": event_minutes,
                "event_fraction": frac,
            }
        )

    # 残り教科
    main = cell.get("main") or {}
    main_subj = (main.get("subject") or "").strip()
    main_cont = (main.get("content") or "").strip()

    if remain_minutes > 0 and (main_subj and main_subj != "（空欄）"):
        segs.append(
            {
                "class": klass,
                "subject": main_subj,
                "content": main_cont,
                "minutes": remain_minutes,
                "event_fraction": 0.0,
            }
        )

    # 互換（古い形式が来た場合）
    if frac == 0.0 and not segs:
        subj = (cell.get("subject") or "").strip()
        cont = (cell.get("content") or "").strip()
        if subj and subj != "（空欄）":
            segs.append(
                {
                    "class": klass,
                    "subject": subj,
                    "content": cont,
                    "minutes": slot_minutes,
                    "event_fraction": 0.0,
                }
            )

    return segs


# ------------------------------
# 1週間分のコマを学年×教科ごとに分数集計
# ------------------------------
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


# ------------------------------
# 印刷用 DataFrame（同一マス2段表示）
# ------------------------------
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

            text = "\n\n".join(parts).strip()
            row.append(text)

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


# ------------------------------
# 年度 初期化（0行種まき）
# ------------------------------
def ensure_year_init_table():
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS year_init (
            school_year TEXT PRIMARY KEY,
            initialized_at TEXT,
            initialized_by TEXT
        )
        """
    )
    conn.commit()


def is_year_initialized(school_year: str) -> bool:
    ensure_year_init_table()
    cur.execute("SELECT 1 FROM year_init WHERE school_year=? LIMIT 1", (school_year,))
    return cur.fetchone() is not None


def init_year_hours_zero(school_year: str, initialized_by: str = "管理職"):
    ensure_year_init_table()
    for g in STANDARD_HOURS.keys():
        for s in get_subjects_for_grade(g):
            cur.execute(
                """
                INSERT OR IGNORE INTO hours_total (school_year, grade, subject, consumed)
                VALUES (?, ?, ?, 0.0)
                """,
                (school_year, g, s),
            )
    cur.execute(
        """
        INSERT OR REPLACE INTO year_init (school_year, initialized_at, initialized_by)
        VALUES (?, DATETIME('now'), ?)
        """,
        (school_year, initialized_by),
    )
    conn.commit()


# ------------------------------
# 下書き（同一教員×週×年度で1件）
# ------------------------------
def upsert_draft(
    school_year: str,
    teacher: str,
    base_grade: str,
    class_name: str,
    teacher_type: str,
    week_str: str,
    plan: dict,
):
    cur.execute(
        """
        SELECT id FROM weekly_plans
        WHERE school_year=? AND teacher=? AND week=? AND status='下書き'
        ORDER BY id DESC LIMIT 1
        """,
        (school_year, teacher, week_str),
    )
    row = cur.fetchone()

    if row:
        wid = row[0]
        cur.execute(
            """
            UPDATE weekly_plans
            SET grade=?, class=?, teacher_type=?, plan_json=?, submitted_at=DATETIME('now')
            WHERE id=?
            """,
            (base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), wid),
        )
    else:
        cur.execute(
            """
            INSERT INTO weekly_plans
              (school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, '下書き', DATETIME('now'))
            """,
            (school_year, teacher, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False)),
        )
    conn.commit()


def list_my_drafts(school_year: str, teacher: str):
    cur.execute(
        """
        SELECT id, week, grade, class, teacher_type, plan_json, submitted_at
        FROM weekly_plans
        WHERE school_year=? AND teacher=? AND status='下書き'
        ORDER BY week DESC, id DESC
        """,
        (school_year, teacher),
    )
    return cur.fetchall()


def load_plan_by_id(wid: int):
    cur.execute(
        """
        SELECT id, school_year, teacher, grade, class, teacher_type, week, plan_json, status
        FROM weekly_plans
        WHERE id=?
        """,
        (wid,),
    )
    return cur.fetchone()


# ------------------------------
# 前週コピー用：直近の週案取得
# ------------------------------
def fetch_latest_plan_before_week(school_year: str, teacher: str, week_str: str):
    cur.execute(
        """
        SELECT plan_json, week, status
        FROM weekly_plans
        WHERE school_year=? AND teacher=? AND week < ?
        ORDER BY week DESC, id DESC
        LIMIT 1
        """,
        (school_year, teacher, week_str),
    )
    return cur.fetchone()


def submit_plan_from_current(
    school_year: str,
    teacher: str,
    base_grade: str,
    class_name: str,
    teacher_type: str,
    week_str: str,
    plan: dict,
):
    cur.execute(
        """
        SELECT id FROM weekly_plans
        WHERE school_year=? AND teacher=? AND week=? AND status='下書き'
        ORDER BY id DESC LIMIT 1
        """,
        (school_year, teacher, week_str),
    )
    row = cur.fetchone()

    if row:
        wid = row[0]
        cur.execute(
            """
            UPDATE weekly_plans
            SET grade=?, class=?, teacher_type=?, plan_json=?, status='提出', submitted_at=DATETIME('now')
            WHERE id=?
            """,
            (base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), wid),
        )
    else:
        cur.execute(
            """
            INSERT INTO weekly_plans
              (school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, '提出', DATETIME('now'))
            """,
            (school_year, teacher, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False)),
        )
    conn.commit()


# ------------------------------
# Reiwa短縮
# ------------------------------
def to_reiwa_short(year_str: str) -> str:
    m = re.search(r"令和\s*([0-9]+)\s*年度", str(year_str))
    return f"R{m.group(1)}" if m else str(year_str).replace("年度", "")


def safe_year_str(s: str):
    return str(s).replace(" ", "").replace("/", "_").replace("\\", "_")


# ------------------------------
# タイトル・利用者区分
# ------------------------------
st.title("小学校 週の指導計画（週案）管理システム（クラウド版）")
role = st.sidebar.selectbox("利用者区分", ["教員", "管理職"], key="role_select")

current_school_year = get_current_school_year()
st.sidebar.markdown("---")
st.sidebar.write(f"📅 現在の年度：**{current_school_year}**")

# ======================================================
# 教員画面
# ======================================================
if role == "教員":
    st.header("📘 週案の作成・提出（教員用）")
    st.caption(f"提出先年度：{current_school_year}（管理職が設定）")

    # ---- 復元のための session_state 初期値 ----
    st.session_state.setdefault("teacher_name", "")
    st.session_state.setdefault("teacher_type", "担任")
    st.session_state.setdefault("base_grade", "3年")
    st.session_state.setdefault("class_name", "")
    st.session_state.setdefault("week_date", date.today())
    st.session_state.setdefault("restore_notice", False)

    teacher = st.text_input("教員名", value=st.session_state.get("teacher_name", ""), key="teacher_name_input")
    if teacher:
        st.session_state["teacher_name"] = teacher

    # 下書き一覧（復元）
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

                    st.success("復元データを読み込みました。ページが再描画されます。")
                    st.rerun()
        else:
            st.caption("下書きはまだありません。")
    else:
        st.caption("※ 教員名を入力すると下書き一覧が表示されます。")

    if st.session_state.get("restore_notice"):
        st.info("下書きを復元しました（勤務形態／基準学年／週／学級／表の中身を反映）。")
        st.session_state["restore_notice"] = False

    # ---- 教員の基本情報（key付きで復元可能に） ----
    teacher_type = st.radio(
        "勤務形態",
        ["担任", "専科（音楽・家庭科など）"],
        index=0 if st.session_state["teacher_type"] == "担任" else 1,
        key="teacher_type_radio",
    )
    st.session_state["teacher_type"] = teacher_type

    grade_keys = list(STANDARD_HOURS.keys())
    base_grade = st.selectbox(
        "基準学年",
        grade_keys,
        index=grade_keys.index(st.session_state["base_grade"]) if st.session_state["base_grade"] in grade_keys else 0,
        key="base_grade_select",
    )
    st.session_state["base_grade"] = base_grade

    class_name = st.text_input(
        "自分の担任学級（例：3-1）※担任でなければ空欄可",
        value=st.session_state.get("class_name", ""),
        key="class_name_input",
    )
    st.session_state["class_name"] = class_name

    week = st.date_input(
        "対象週（週の初日：月曜日など）",
    # ------------------------------
# 前週コピー機能
# ------------------------------
st.markdown("### ⏪ 前週コピー")

if st.button("⬅ 前週の週案をコピーする", key="copy_prev_week"):

    if not teacher.strip():
        st.error("教員名を入力してください。")
    else:
        row = fetch_latest_plan_before_week(
            current_school_year,
            teacher.strip(),
            week_str
        )

        if not row:
            st.warning("前週データが見つかりませんでした。")
        else:
            plan_json, prev_week, prev_status = row

            try:
                prev_plan = json.loads(plan_json) if plan_json else {}
            except:
                prev_plan = {}

            prev_tt = prev_plan.get("timetable", {})

            st.session_state["restore_plan"] = {"timetable": prev_tt}

            st.success(f"前週（{prev_week}）をコピーしました。")
            st.rerun()
        value=st.session_state.get("week_date", date.today()),
        key="week_date_input",
    )
    st.session_state["week_date"] = week
    week_str = str(week)

    # ------------------------------
    # 前週コピー機能
    # ------------------------------
    st.markdown("### ⏪ 前週コピー")
    if st.button("⬅ 前週の週案をコピーする", key="copy_prev_week"):
        if not teacher.strip():
            st.error("教員名を入力してください。")
        else:
            row = fetch_latest_plan_before_week(
                current_school_year,
                teacher.strip(),
                week_str
            )

            if not row:
                st.warning("前週データが見つかりませんでした。")
            else:
                plan_json, prev_week, prev_status = row

                try:
                    prev_plan = json.loads(plan_json) if plan_json else {}
                except Exception:
                    prev_plan = {}

                prev_tt = prev_plan.get("timetable", {})

                # 現在の週へコピー
                st.session_state["restore_plan"] = {"timetable": prev_tt}

                st.success(f"前週（{prev_week}）をコピーしました。")
                st.rerun()

    # 教科選択肢
    if teacher_type == "担任":
        subject_options = ["（空欄）"] + get_subjects_for_grade(base_grade)
        st.caption("※ 担任は、その学年で扱う教科のみ選択できます。")
        class_candidates = [class_name] if class_name else []
    else:
        subject_options = ["（空欄）"] + ALL_SUBJECTS
        st.caption("※ 専科は、各コマで学級・教科を自由に選べます。")
        st.info("この週に指導する学級をカンマ区切りで入力してください。（例：3-1,3-2,4-1）")
        classes_input = st.text_input("指導学級一覧", value=class_name, key="classes_input")
        class_candidates = [c.strip() for c in classes_input.split(",") if c.strip()]
        if class_candidates:
            st.caption("この週に指導する学級：" + "、".join(class_candidates))
        else:
            st.caption("※ 学級が未入力の場合、学級欄は空欄のままとなります。")

    st.markdown("---")
    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    st.caption("行：校時／列：曜日。各マスで「学校行事(3/8等)＋残り教科」「内容」を入力します。")

    timetable = {}
    restore_plan = st.session_state.get("restore_plan")
    if restore_plan and isinstance(restore_plan, dict):
        timetable = restore_plan.get("timetable") or {}
        if not isinstance(timetable, dict):
            timetable = {}

    # header
    header_cols = st.columns(COLUMN_WIDTHS)
    header_cols[0].write("　")
    for i, day in enumerate(DAYS, start=1):
        header_cols[i].write(f"**{day}**")

    # 入力テーブル
    for period in PERIODS:
        if not any(PERIOD_MINUTES[day][period] > 0 for day in DAYS):
            continue

        row_cols = st.columns(COLUMN_WIDTHS)
        row_cols[0].write(f"**{period}**")

        for j, day in enumerate(DAYS, start=1):
            timetable.setdefault(day, {})
            minutes = PERIOD_MINUTES[day][period]

            with row_cols[j]:
                with st.container(border=True):
                    if minutes <= 0:
                        st.write("―")
                        timetable[day][period] = {
                            "class": "",
                            "event": {"fraction": 0.0, "content": ""},
                            "main": {"subject": "（空欄）", "content": ""},
                        }
                        continue

                    st.markdown(f"<div class='tt-mini'>{minutes}分</div>", unsafe_allow_html=True)

                    old_cell = timetable.get(day, {}).get(period, {}) or {}
                    old_class = (old_cell.get("class") or "").strip()
                    old_event = old_cell.get("event") or {}
                    old_main = old_cell.get("main") or {}

                    old_event_frac = float(old_event.get("fraction", 0.0) or 0.0)
                    event_label_default = fraction_value_to_label(old_event_frac)

                    old_event_content = (old_event.get("content") or "").strip()
                    old_main_subject = (old_main.get("subject") or old_cell.get("subject") or "（空欄）").strip()
                    old_main_content = (old_main.get("content") or old_cell.get("content") or "").strip()

                    # 学級（専科のみ選択）
                    if teacher_type.startswith("専科"):
                        if class_candidates:
                            opts = ["（未選択）"] + class_candidates
                            idx = opts.index(old_class) if old_class in opts else 0
                            klass = st.selectbox(
                                "学級",
                                opts,
                                index=idx,
                                key=f"{day}_{period}_class",
                                label_visibility="collapsed",
                            )
                            klass = "" if klass == "（未選択）" else klass
                        else:
                            klass = ""
                    else:
                        klass = class_name

                    # 学校行事（配分）
                    event_opts = [x[0] for x in EVENT_FRACTIONS]
                    st.markdown('<div class="tt-sec-event">学校行事（配分）</div>', unsafe_allow_html=True)
                    event_label = st.selectbox(
                        "学校行事（配分）",
                        event_opts,
                        index=event_opts.index(event_label_default) if event_label_default in event_opts else 0,
                        key=f"{day}_{period}_eventfrac",
                        label_visibility="collapsed",
                    )
                    event_frac = fraction_label_to_value(event_label)

                    event_minutes = minutes * event_frac
                    remain_minutes = minutes - event_minutes

                    # 学校行事内容（配分がある時だけ）
                    event_content = ""
                    if event_frac > 0:
                        st.markdown('<div class="tt-sec-event">学校行事（内容）</div>', unsafe_allow_html=True)
                        event_content = st.text_area(
                            "学校行事 内容",
                            value=old_event_content,
                            key=f"{day}_{period}_eventcont",
                            height=45,
                            label_visibility="collapsed",
                        )

                    # 残り教科（残りがある場合だけ表示）
                    main_subject = "（空欄）"
                    main_content = ""
                    if remain_minutes > 0:
                        st.markdown(
                            f'<div class="tt-sec-main">残り：{int(round(remain_minutes))}分（教科等）</div>',
                            unsafe_allow_html=True,
                        )
                        main_subject = st.selectbox(
                            "残り枠の教科等",
                            subject_options,
                            index=subject_options.index(old_main_subject) if old_main_subject in subject_options else 0,
                            key=f"{day}_{period}_mainsubj",
                            label_visibility="collapsed",
                        )
                        main_content = st.text_area(
                            "残り枠の内容",
                            value=old_main_content,
                            key=f"{day}_{period}_maincont",
                            height=55,
                            label_visibility="collapsed",
                        )

                    timetable[day][period] = {
                        "class": klass,
                        "event": {"fraction": event_frac, "content": event_content},
                        "main": {"subject": main_subject, "content": main_content},
                    }

    # ------------------------------
    # 入力バリデーション（学校行事 3/8・6/8 の場合は残り教科必須）
    # ------------------------------
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
                        errors.append(
                            f"{day} {period}: 学校行事が {e8}/8 のため、残り {r8}/8（{int(round(slot_minutes*(1-frac)))}分）の教科等が必要です。"
                        )
        return errors

    # 週の教科別合計（基準学年）
    week_minutes_all = compute_week_subject_minutes(timetable, base_grade)
    subject_minutes_this_grade = week_minutes_all.get(base_grade, {})

    st.markdown("---")
    st.markdown(f"#### この週の教科別 合計分数（{base_grade}）")
    for s in get_subjects_for_grade(base_grade):
        st.write(f"- {s}: {int(round(subject_minutes_this_grade.get(s, 0)))} 分")

    # ------------------------------
    # 教員用：この週案をCSVで保存（非常時用）
    # ------------------------------
    st.markdown("---")
    st.subheader("💾 自分の週案を保存（CSV）")
    st.caption("※ 未提出でも保存できます（非常時用の控え）。")

    slot_rows = []
    for day in DAYS:
        for period in PERIODS:
            mins = PERIOD_MINUTES.get(day, {}).get(period, 0)
            if mins <= 0:
                continue
            cell = (timetable or {}).get(day, {}).get(period, {}) or {}
            segs = cell_to_segments(cell, mins)

            if not segs:
                slot_rows.append(
                    {
                        "年度": current_school_year,
                        "教員": teacher,
                        "基準学年": base_grade,
                        "担任学級": class_name,
                        "勤務形態": teacher_type,
                        "週": week_str,
                        "曜日": day,
                        "校時": period,
                        "分": int(round(mins)),
                        "学級": cell.get("class", ""),
                        "教科等": "",
                        "内容": "",
                    }
                )
            else:
                for seg in segs:
                    slot_rows.append(
                        {
                            "年度": current_school_year,
                            "教員": teacher,
                            "基準学年": base_grade,
                            "担任学級": class_name,
                            "勤務形態": teacher_type,
                            "週": week_str,
                            "曜日": day,
                            "校時": period,
                            "分": int(round(seg.get("minutes", 0))),
                            "学級": seg.get("class", ""),
                            "教科等": seg.get("subject", ""),
                            "内容": seg.get("content", ""),
                        }
                    )

    df_my = pd.DataFrame(slot_rows)
    my_csv = df_my.to_csv(index=False).encode("utf-8-sig")
    today_str = date.today().strftime("%Y%m%d")
    my_name = f"{teacher or 'teacher'}_{base_grade}_{week_str}_{today_str}_my_weekly_plan.csv".replace("/", "_")

    st.download_button(
        label="⬇️ この週案をCSVで保存",
        data=my_csv,
        file_name=my_name,
        mime="text/csv",
    )

    # ------------------------------
    # 下書き保存 / 提出
    # ------------------------------
    st.markdown("---")
    st.subheader("📝 下書き・提出")

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("💾 下書きを上書き保存（同一 教員×週×年度 は1件）", key="draft_save_btn"):
            if not teacher.strip():
                st.error("教員名を入力してください（下書きの紐づけに必要です）。")
            else:
                plan = {"timetable": timetable}
                upsert_draft(current_school_year, teacher.strip(), base_grade, class_name, teacher_type, week_str, plan)
                st.success("下書きを保存しました。")

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
                    submit_plan_from_current(
                        current_school_year,
                        teacher.strip(),
                        base_grade,
                        class_name,
                        teacher_type,
                        week_str,
                        plan,
                    )
                    st.success("週案を提出しました。管理職の承認をお待ちください。")

    # ------------------------------
    # 印刷（完成版）
    # ------------------------------
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

# ======================================================
# 管理職画面
# ======================================================
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
        view_year = st.selectbox(
            "表示する年度",
            years_list,
            index=years_list.index(get_current_school_year()) if get_current_school_year() in years_list else 0,
            key="view_year_select",
        )
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

    # 年度初期化（未初期化なら自動）
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

    st.markdown("---")
    st.header("📝 提出された週案一覧（管理職用）")
    st.caption("※ この画面の一覧・集計は「表示する年度」に基づきます。")

    cur.execute(
        """
        SELECT id, school_year, teacher, grade, class, teacher_type, week,
               plan_json, status, submitted_at, approved_at, approved_by
        FROM weekly_plans
        WHERE school_year=?
        ORDER BY id DESC
        """,
        (view_year,),
    )
    all_rows = cur.fetchall()

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

    for (
        wid,
        school_year,
        teacher,
        grade,
        class_name,
        teacher_type,
        week,
        plan_json,
        status,
        submitted_at,
        approved_at,
        approved_by,
    ) in rows:
        try:
            plan = json.loads(plan_json) if plan_json else {}
        except Exception:
            plan = {}
        timetable = plan.get("timetable", {}) if isinstance(plan, dict) else {}
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
            df_print = build_print_df(timetable)
            if df_print.empty:
                st.info("有効なコマがありません。")
            else:
                st.dataframe(df_print, use_container_width=True, height=520)

            st.caption("（印刷はブラウザの印刷機能から）")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"✅ 承認する（ID:{wid}）", key=f"approve_{wid}"):
                    if status != "承認":
                        for g in week_minutes_all:
                            for subj, mins in week_minutes_all[g].items():
                                add_hours(view_year, g, subj, mins)

                        cur.execute(
                            """
                            UPDATE weekly_plans
                            SET status='承認',
                                approved_at=DATETIME('now'),
                                approved_by=?
                            WHERE id=?
                            """,
                            ("管理職", wid),
                        )
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
    st.markdown("---")
    st.header(f"📊 年間累積時数の状況（{view_year}）")

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
            rows_table.append(
                {
                    "教科等": subj,
                    "標準（45分コマ）": round(std, 2),
                    "実施累積（45分コマ）": round(used, 2),
                    "残り（45分コマ）": round(remain, 2),
                }
            )
        st.table(rows_table)

    # ======================================================
    # 🧰 バックアップ（Excel/CSV）※管理職のみ（年度view_yearで出力）
    # ======================================================
    def ensure_backup_log_table():
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS backup_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_year TEXT,
                created_at TEXT,
                created_by TEXT,
                filename TEXT
            )
            """
        )
        conn.commit()

    def get_last_backup_date(school_year: str):
        ensure_backup_log_table()
        cur.execute(
            "SELECT created_at FROM backup_log WHERE school_year=? ORDER BY id DESC LIMIT 1",
            (school_year,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def log_backup(school_year: str, created_by: str, filename: str):
        ensure_backup_log_table()
        cur.execute(
            "INSERT INTO backup_log (school_year, created_at, created_by, filename) "
            "VALUES (?, DATETIME('now'), ?, ?)",
            (school_year, created_by, filename),
        )
        conn.commit()

    def fetch_all_weekly_plans_for_year(school_year: str):
        cur.execute(
            """
            SELECT id, school_year, teacher, grade, class, teacher_type, week, plan_json, status,
                   submitted_at, approved_at, approved_by
            FROM weekly_plans
            WHERE school_year=?
            ORDER BY id DESC
            """,
            (school_year,),
        )
        return cur.fetchall()

    def fetch_hours_total_for_year(school_year: str):
        cur.execute(
            """
            SELECT school_year, grade, subject, consumed
            FROM hours_total
            WHERE school_year=?
            ORDER BY grade, subject
            """,
            (school_year,),
        )
        return cur.fetchall()

    def flatten_plans_to_rows(plans):
        plan_rows = []
        slot_rows = []
        for (
            wid,
            sy,
            teacher,
            grade,
            class_name,
            teacher_type,
            week,
            plan_json,
            status,
            submitted_at,
            approved_at,
            approved_by,
        ) in plans:

            plan_rows.append(
                {
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
                }
            )

            try:
                plan = json.loads(plan_json) if plan_json else {}
            except Exception:
                plan = {}
            timetable = plan.get("timetable", {}) if isinstance(plan, dict) else {}

            for day in DAYS:
                for period in PERIODS:
                    slot_minutes = PERIOD_MINUTES.get(day, {}).get(period, 0)
                    if slot_minutes <= 0:
                        continue
                    cell = (timetable or {}).get(day, {}).get(period, {}) or {}
                    segs = cell_to_segments(cell, slot_minutes)

                    if not segs:
                        slot_rows.append(
                            {
                                "plan_id": wid,
                                "school_year": sy,
                                "week": week,
                                "teacher": teacher,
                                "base_grade": grade,
                                "base_class": class_name,
                                "teacher_type": teacher_type,
                                "day": day,
                                "period": period,
                                "minutes": int(round(slot_minutes)),
                                "class": cell.get("class", ""),
                                "subject": "",
                                "content": "",
                                "status": status,
                            }
                        )
                    else:
                        for seg in segs:
                            slot_rows.append(
                                {
                                    "plan_id": wid,
                                    "school_year": sy,
                                    "week": week,
                                    "teacher": teacher,
                                    "base_grade": grade,
                                    "base_class": class_name,
                                    "teacher_type": teacher_type,
                                    "day": day,
                                    "period": period,
                                    "minutes": int(round(seg.get("minutes", 0))),
                                    "class": seg.get("class", ""),
                                    "subject": seg.get("subject", ""),
                                    "content": seg.get("content", ""),
                                    "status": status,
                                }
                            )

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
                out.append(
                    {
                        "school_year": school_year,
                        "grade": gg,
                        "subject": ss,
                        "standard_45": round(std, 2),
                        "consumed_45": round(used, 2),
                        "remain_45": round(remain, 2),
                        "progress_pct": round(pct, 1),
                    }
                )
        return pd.DataFrame(out)

    def to_excel_bytes(dfs: dict):
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            for sheet, df in dfs.items():
                df.to_excel(writer, index=False, sheet_name=str(sheet)[:31])
        bio.seek(0)
        return bio.getvalue()

    st.markdown("---")
    st.header("🧰 バックアップ（Excel/CSV ダウンロード）")
    st.caption(f"対象年度：{view_year}　（管理職のみ実行）")

    last_backup = get_last_backup_date(view_year)
    if last_backup:
        st.write(f"前回バックアップ：{last_backup}")
    else:
        st.warning("まだバックアップが作成されていません。初回は必ず作成してください。")

    ensure_backup_log_table()
    cur.execute(
        """
        SELECT julianday('now') - julianday(created_at)
        FROM backup_log
        WHERE school_year=?
        ORDER BY id DESC LIMIT 1
        """,
        (view_year,),
    )
    row = cur.fetchone()
    if row and row[0] is not None and float(row[0]) >= 7:
        st.warning("前回バックアップから7日以上経過しています。バックアップを作成してください。")

    st.session_state.setdefault("backup_excel_bytes", None)
    st.session_state.setdefault("backup_csv_pack", None)
    st.session_state.setdefault("backup_filename", None)

    created_by = "管理職"

    if st.button("🟦 バックアップを作成（今日の日付で生成）", key="backup_make_btn"):
        plans = fetch_all_weekly_plans_for_year(view_year)
        df_plans, df_slots = flatten_plans_to_rows(plans)

        hours_rows = fetch_hours_total_for_year(view_year)
        df_hours = build_hours_progress_df(view_year, hours_rows)

        today_str = date.today().strftime("%Y%m%d")
        filename = f"{safe_year_str(view_year)}_weekly_plan_backup_{today_str}.xlsx"

        excel_bytes = to_excel_bytes(
            {
                "週案一覧": df_plans,
                "時間割（コマ明細）": df_slots,
                "年間累積（進捗）": df_hours,
            }
        )

        st.session_state["backup_excel_bytes"] = excel_bytes
        st.session_state["backup_csv_pack"] = {
            "weekly_plans": df_plans.to_csv(index=False).encode("utf-8-sig"),
            "weekly_slots": df_slots.to_csv(index=False).encode("utf-8-sig"),
            "hours_progress": df_hours.to_csv(index=False).encode("utf-8-sig"),
        }
        st.session_state["backup_filename"] = filename

        log_backup(view_year, created_by=created_by, filename=filename)
        st.success("バックアップを作成しました。下のボタンからダウンロードしてください。")

    if st.session_state["backup_excel_bytes"]:
        today_str = date.today().strftime("%Y%m%d")
        st.download_button(
            label="⬇️ バックアップ一括（Excel）をダウンロード",
            data=st.session_state["backup_excel_bytes"],
            file_name=st.session_state["backup_filename"]
            or f"{safe_year_str(view_year)}_weekly_plan_backup_{today_str}.xlsx",
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
            label="⬇️ 時間割（コマ明細）（CSV）",
            data=csv_pack.get("weekly_slots", b""),
            file_name=f"{safe_year_str(view_year)}_weekly_slots_{today_str}.csv",
            mime="text/csv",
        )
        st.download_button(
            label="⬇️ 年間累積（進捗）（CSV）",
            data=csv_pack.get("hours_progress", b""),
            file_name=f"{safe_year_str(view_year)}_hours_progress_{today_str}.csv",
            mime="text/csv",
        )

    # ======================================================
    # 🏛 区教委提出用（年間時数 まとめCSV）
    # ======================================================
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
            out_rows.append(
                {
                    "年度": view_year,
                    "学年": gg,
                    "教科等": ss,
                    "標準（45分コマ）": round(std, 2),
                    "実施累積（45分コマ）": round(used, 2),
                    "残り（45分コマ）": round(remain, 2),
                    "進捗（％）": round(pct, 1),
                }
            )

    df_submit = pd.DataFrame(out_rows)[
        ["年度", "学年", "教科等", "標準（45分コマ）", "実施累積（45分コマ）", "残り（45分コマ）", "進捗（％）"]
    ]

    with st.expander("内容を表示（確認用）", expanded=False):
        st.dataframe(df_submit, use_container_width=True, height=420)

    today_str = date.today().strftime("%Y%m%d")
    submit_csv = df_submit.to_csv(index=False).encode("utf-8-sig")

    school_short = "東小松川小学校"
    reiwa_short = to_reiwa_short(view_year)
    submit_name = f"{reiwa_short}_年間指導時数集計_{school_short}_{today_str}.csv"

    st.download_button(
        label="⬇️ 区教委提出用CSVをダウンロード",
        data=submit_csv,
        file_name=submit_name,
        mime="text/csv",
    )
