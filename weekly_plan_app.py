# ===========================================
# weekly_plan_app.py
# 担任＋専科ハイブリッド版（A案）＋年度切替（令和○年度）＋自動バックアップ（ボタン式）
#
# ・教員：週案を「一週間×1～6校時＋学校裁量枠」の表で作成し提出
# ・管理職：内容確認→承認／差戻
# ・承認時：学年×教科の年間累積（45分換算）に反映
# ・担任：学年の教科リストから選択
# ・専科：各コマで「学級」「教科」「内容」を自由に選択（複数学級対応）
# ・学級名から学年を推定して反映（例 3-1 → 3年）
# ・40分／45分コマ混在対応、学校裁量45分枠（月火木金）
# ・管理職ログイン＋管理画面フィルタ強化
# ・印刷（ブラウザ印刷）
# ・バックアップ（管理職のみ、ボタンで日付付き生成→DL）
# ・年度切替（令和8年度/令和9年度…）
# ===========================================

import streamlit as st
import sqlite3
from datetime import date
import json
import pandas as pd
import io

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
# アプリ設定（現在の年度をDBに保存：全端末で共通）
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
# ※ 追加できない場合は except で無視
for col in ["school_year", "class", "teacher_type", "submitted_at", "approved_at", "approved_by"]:
    try:
        cur.execute(f"ALTER TABLE weekly_plans ADD COLUMN {col} TEXT")
    except sqlite3.OperationalError:
        pass

# 既存データの school_year が空なら既定年度で埋める
try:
    cur.execute("UPDATE weekly_plans SET school_year=? WHERE school_year IS NULL OR school_year=''", (DEFAULT_SCHOOL_YEAR,))
    conn.commit()
except Exception:
    pass

# ------------------------------
# 年間累積時数テーブル（年度列あり）
# ------------------------------
# 新規作成時は年度込みの主キー
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

# 既存の古い hours_total（年度列なし）からの移行を想定して列追加を試みる
# ただし、すでに年度列ありなら何もしない
try:
    cur.execute("ALTER TABLE hours_total ADD COLUMN school_year TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

# school_year が空なら既定年度で埋める（古いDBの救済）
try:
    cur.execute("UPDATE hours_total SET school_year=? WHERE school_year IS NULL OR school_year=''", (DEFAULT_SCHOOL_YEAR,))
    conn.commit()
except Exception:
    pass

conn.commit()

# ------------------------------
# 学年ごとの標準時数（45分換算コマ数）※校内運用に合わせて調整可
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

# 専科用：全学年の教科リスト（重複なし）
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
# 分 → 45分コマ換算
# ------------------------------
def convert_to_45(mins: float) -> float:
    return mins / 45

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
        new_value = row[0] + add_45
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
# 1週間分のコマを学年×教科ごとに分数集計
# ------------------------------
def compute_week_subject_minutes(timetable: dict, base_grade: str):
    """
    戻り値: { "3年": { "国語": 分数, ... }, "4年": {...}, ... }
    学級が判別できる場合はそちらを優先し、判別できない場合は base_grade でカウント。
    """
    result = {}
    for day in DAYS:
        for period in PERIODS:
            cell = timetable.get(day, {}).get(period)
            if not cell:
                continue
            minutes = PERIOD_MINUTES[day][period]
            if minutes <= 0:
                continue
            subject = cell.get("subject", "")
            klass = cell.get("class", "")
            grade_for_slot = detect_grade_from_class(klass) or base_grade
            if grade_for_slot not in STANDARD_HOURS:
                continue
            if subject not in STANDARD_HOURS[grade_for_slot]:
                continue
            result.setdefault(grade_for_slot, {})
            result[grade_for_slot][subject] = result[grade_for_slot].get(subject, 0) + minutes
    return result

# ------------------------------
# 状態ラベル（HTML）
# ------------------------------
def status_badge(status: str) -> str:
    cls = "status-teishutsu"
    if status == "承認":
        cls = "status-shonin"
    elif status == "差戻":
        cls = "status-sashimodoshi"
    return f'<span class="status-label {cls}">{status}</span>'

# ------------------------------
# 印刷用 DataFrame を生成
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
            cell = timetable.get(day, {}).get(period, {})
            klass = cell.get("class", "")
            subj = cell.get("subject", "")
            cont = cell.get("content", "")

            text = ""
            if klass:
                text += f"{klass} "
            if subj and subj != "（空欄）":
                text += subj
            if cont:
                text = (text + "\n" + cont) if text else cont
            if text:
                text = f"[{mins}分] " + text
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

# 現在の年度（DBから取得：全端末で共通）
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

    if teacher_type == "担任":
        subject_options = ["（空欄）"] + get_subjects_for_grade(grade)
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

    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    st.caption("行：校時／列：曜日。各マスで「学級（専科）」「教科等」「内容」を入力します。")

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
            if day not in timetable:
                timetable[day] = {}

            minutes = PERIOD_MINUTES[day][period]

            with row_cols[j]:
                if minutes <= 0:
                    st.write("―")
                    cell = {"class": "", "subject": "（空欄）", "content": ""}
                else:
                    st.caption(f"{minutes}分")

                    if teacher_type.startswith("専科"):
                        if class_candidates:
                            klass = st.selectbox(
                                "学級",
                                ["（未選択）"] + class_candidates,
                                key=f"{day}_{period}_class",
                                label_visibility="collapsed",
                            )
                            klass = "" if klass == "（未選択）" else klass
                        else:
                            klass = ""
                    else:
                        klass = class_name

                    subject = st.selectbox(
                        "教科等",
                        subject_options,
                        key=f"{day}_{period}_subject",
                        label_visibility="collapsed",
                    )
                    content = st.text_area(
                        "内容",
                        key=f"{day}_{period}_content",
                        height=60,
                        label_visibility="collapsed",
                    )
                    cell = {"class": klass, "subject": subject, "content": content}

            timetable[day][period] = cell
    week_minutes_all = compute_week_subject_minutes(timetable, base_grade)
    subject_minutes_this_grade = week_minutes_all.get(base_grade, {})

    st.markdown(f"#### この週の教科別 合計分数（{base_grade}）")
    for s in get_subjects_for_grade(base_grade):
        mins = subject_minutes_this_grade.get(s, 0)
        st.write(f"- {s}: {mins} 分")

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
        cell = timetable.get(day, {}).get(period, {})
        slot_rows.append({
            "年度": current_school_year,
            "教員": teacher,
            "基準学年": base_grade,
            "担任学級": class_name,
            "勤務形態": teacher_type,
            "週": str(week),
            "曜日": day,
            "校時": period,
            "分": mins,
            "学級": cell.get("class", ""),
            "教科等": cell.get("subject", ""),
            "内容": cell.get("content", ""),
        })

df_my = pd.DataFrame(slot_rows)

my_csv = df_my.to_csv(index=False).encode("utf-8-sig")
today_str = date.today().strftime("%Y%m%d")
my_name = f"{teacher or 'teacher'}_{base_grade}_{str(week)}_{today_str}_my_weekly_plan.csv".replace("/", "_")

st.download_button(
    label="⬇️ この週案をCSVで保存",
    data=my_csv,
    file_name=my_name,
    mime="text/csv",
)

    week_minutes_all = compute_week_subject_minutes(timetable, base_grade)
    subject_minutes_this_grade = week_minutes_all.get(base_grade, {})

    st.markdown(f"#### この週の教科別 合計分数（{base_grade}）")
    for s in get_subjects_for_grade(base_grade):
        mins = subject_minutes_this_grade.get(s, 0)
        st.write(f"- {s}: {mins} 分")

    st.markdown("#### 📄 印刷・PDF保存用レイアウト（教員用）")
    if st.checkbox("この週案を印刷用に表示する"):
        df_print = build_print_df(timetable)
        if df_print.empty:
            st.info("有効なコマがありません。")
        else:
            st.write(f"**{current_school_year}／{base_grade}／{class_name}／{teacher}／{week} の週案（印刷用）**")
            st.table(df_print)
            st.info("ブラウザの印刷機能から PDF 保存・印刷を行ってください。")

    if st.button("✅ この内容で管理職へ提出する"):
        plan = {"timetable": timetable}
        cur.execute(
            """
            INSERT INTO weekly_plans
              (school_year, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, '提出', DATETIME('now'))
            """,
            (
                current_school_year,
                teacher,
                base_grade,
                class_name,
                teacher_type,
                str(week),
                json.dumps(plan, ensure_ascii=False),
            ),
        )
        conn.commit()
        st.success("週案を提出しました。管理職の承認をお待ちください。")

# ======================================================
# 管理職画面
# ======================================================
if role == "管理職":
    require_manager_login()

    st.header("🧭 年度の管理（管理職）")

    # 年度候補（DBから集める）
    years = set()
    years.add(get_current_school_year())
    years.add(DEFAULT_SCHOOL_YEAR)

    try:
        cur.execute("SELECT DISTINCT school_year FROM weekly_plans")
        for r in cur.fetchall():
            if r and r[0]:
                years.add(r[0])
    except Exception:
        pass

    try:
        cur.execute("SELECT DISTINCT school_year FROM hours_total")
        for r in cur.fetchall():
            if r and r[0]:
                years.add(r[0])
    except Exception:
        pass

    years_list = sorted(list(years))

    coly1, coly2, coly3 = st.columns([2, 2, 2])
    with coly1:
        view_year = st.selectbox("表示する年度", years_list, index=years_list.index(get_current_school_year()) if get_current_school_year() in years_list else 0)
        # ------------------------------
# 年度 初期化ガード（初回だけ0行を作る）
# ------------------------------
def ensure_year_init_table():
    cur.execute("""
    CREATE TABLE IF NOT EXISTS year_init (
        school_year TEXT PRIMARY KEY,
        initialized_at TEXT,
        initialized_by TEXT
    )
    """)
    conn.commit()

def is_year_initialized(school_year: str) -> bool:
    ensure_year_init_table()
    cur.execute("SELECT 1 FROM year_init WHERE school_year=? LIMIT 1", (school_year,))
    return cur.fetchone() is not None

def init_year_hours_zero(school_year: str, initialized_by: str = "管理職"):
    """
    新年度の hours_total を0で種まき（学年×教科）
    既に存在する行は上書きしない（INSERT OR IGNORE）
    """
    ensure_year_init_table()

    # hours_total 0行作成
    for g in STANDARD_HOURS.keys():
        for s in get_subjects_for_grade(g):
            cur.execute("""
                INSERT OR IGNORE INTO hours_total (school_year, grade, subject, consumed)
                VALUES (?, ?, ?, 0.0)
            """, (school_year, g, s))
    # 初期化ログ
    cur.execute("""
        INSERT OR REPLACE INTO year_init (school_year, initialized_at, initialized_by)
        VALUES (?, DATETIME('now'), ?)
    """, (school_year, initialized_by))
    conn.commit()

# 画面表示（初期化されていない年度は警告）
if not is_year_initialized(view_year):
    st.warning(
        f"⚠ {view_year} は未初期化です。"
        "新年度の場合は、まず『年度を初期化（0で開始）』を押してください。"
        "（年間累積を0行で作成し、区教委CSVも必ず出せる状態にします）"
    )
    if st.button("🟨 年度を初期化（0で開始）"):
        init_year_hours_zero(view_year, initialized_by="管理職")
        st.success(f"{view_year} を初期化しました。（累積0で開始）")
        st.rerun()
else:
    st.info(f"✅ {view_year} は初期化済みです。")

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
            st.success(f"新年度「{new_year.strip()}」を現在の年度にしました。")
            st.rerun()

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
        timetable = plan.get("timetable", {})
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
                        cell = timetable.get(day, {}).get(period, {})
                        klass = cell.get("class", "")
                        subj = cell.get("subject", "（空欄）")
                        cont = cell.get("content", "")
                        st.caption(f"{mins}分")
                        if klass:
                            st.write(klass)
                        st.write(subj)
                        if cont:
                            st.caption(cont)

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
                        # 承認時：年度view_yearで累積に反映
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
    st.header(f"📊 年間累積時数の状況（{view_year}）")
    for g in STANDARD_HOURS.keys():
        st.subheader(f"{g}の時数状況")
        rows_table = []
        for subj in get_subjects_for_grade(g):
            std = STANDARD_HOURS[g][subj]
            cur.execute(
                "SELECT consumed FROM hours_total WHERE school_year=? AND grade=? AND subject=?",
                (view_year, g, subj),
            )
            row = cur.fetchone()
            used = row[0] if row else 0.0
            remain = std - used
            rows_table.append(
                {
                    "教科等": subj,
                    "標準（45分コマ）": std,
                    "実施累積（45分コマ）": round(used, 1),
                    "残り（45分コマ）": round(remain, 1),
                }
            )
        st.table(rows_table)

    # ======================================================
    # 🧰 バックアップ（Excel/CSV）※管理職のみ（年度view_yearで出力）
    # ======================================================

    # バックアップ履歴テーブル（年度も保存）
    def ensure_backup_log_table():
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

    def get_last_backup_date(school_year: str):
        ensure_backup_log_table()
        cur.execute(
            "SELECT created_at FROM backup_log WHERE school_year=? ORDER BY id DESC LIMIT 1",
            (school_year,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def log_backup(school_year: str, created_by: str, filename: str):
        ensure_backup_log_table()
        cur.execute(
            "INSERT INTO backup_log (school_year, created_at, created_by, filename) "
            "VALUES (?, DATETIME('now'), ?, ?)",
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
            timetable = plan.get("timetable", {})

            for day in DAYS:
                for period in PERIODS:
                    cell = timetable.get(day, {}).get(period, {})
                    minutes = PERIOD_MINUTES.get(day, {}).get(period, 0)
                    slot_rows.append({
                        "plan_id": wid,
                        "school_year": sy,
                        "week": week,
                        "teacher": teacher,
                        "base_grade": grade,
                        "base_class": class_name,
                        "teacher_type": teacher_type,
                        "day": day,
                        "period": period,
                        "minutes": minutes,
                        "class": cell.get("class", ""),
                        "subject": cell.get("subject", ""),
                        "content": cell.get("content", ""),
                        "status": status,
                    })

        return pd.DataFrame(plan_rows), pd.DataFrame(slot_rows)

    def build_hours_progress_df(school_year: str, hours_total_rows):
        out = []
        # hours_total_rows: [(school_year, grade, subject, consumed), ...]
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

    # --- 画面表示 ---
    st.markdown("---")
    st.header("🧰 バックアップ（Excel/CSV ダウンロード）")
    st.caption(f"対象年度：{view_year}　（管理職のみ実行）")

    last_backup = get_last_backup_date(view_year)
    if last_backup:
        st.write(f"前回バックアップ：{last_backup}")
    else:
        st.warning("まだバックアップが作成されていません。初回は必ず作成してください。")

    # 7日以上空いたら注意
    ensure_backup_log_table()
    cur.execute("""
        SELECT julianday('now') - julianday(created_at)
        FROM backup_log
        WHERE school_year=?
        ORDER BY id DESC LIMIT 1
    """, (view_year,))
    row = cur.fetchone()
    if row and row[0] is not None and row[0] >= 7:
        st.warning("前回バックアップから7日以上経過しています。バックアップを作成してください。")

    # セッション初期化
    st.session_state.setdefault("backup_excel_bytes", None)
    st.session_state.setdefault("backup_csv_pack", None)
    st.session_state.setdefault("backup_filename", None)

    created_by = "管理職"

    if st.button("🟦 バックアップを作成（今日の日付で生成）"):
        plans = fetch_all_weekly_plans_for_year(view_year)
        df_plans, df_slots = flatten_plans_to_rows(plans)

        hours_rows = fetch_hours_total_for_year(view_year)
        df_hours = build_hours_progress_df(view_year, hours_rows)

        today_str = date.today().strftime("%Y%m%d")
        filename = f"{safe_year_str(view_year)}_weekly_plan_backup_{today_str}.xlsx"

        excel_bytes = to_excel_bytes({
            "週案一覧": df_plans,
            "時間割（コマ明細）": df_slots,
            "年間累積（進捗）": df_hours,
        })

        st.session_state["backup_excel_bytes"] = excel_bytes
        st.session_state["backup_csv_pack"] = {
            "weekly_plans": df_plans.to_csv(index=False).encode("utf-8-sig"),
            "weekly_slots": df_slots.to_csv(index=False).encode("utf-8-sig"),
            "hours_progress": df_hours.to_csv(index=False).encode("utf-8-sig"),
        }
        st.session_state["backup_filename"] = filename

        log_backup(view_year, created_by=created_by, filename=filename)
        st.success("バックアップを作成しました。下のボタンからダウンロードしてください。")

    # バックアップDL（作成後のみ表示）
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
def to_reiwa_short(year_str: str) -> str:
    # 例：令和8年度 -> R8
    import re
    m = re.search(r"令和\s*([0-9]+)\s*年度", year_str)
    return f"R{m.group(1)}" if m else year_str.replace("年度", "")

st.markdown("---")
st.header("🏛 区教委提出用（年間時数 まとめCSV）")
st.caption(f"対象年度：{view_year}（学年×教科の標準・累積・残りを1本に整形）")

# 年間累積を取得（初期化済みなら必ず揃う / 未初期化でも0で補完）
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

school_short = "東小松川小学校"
reiwa_short = to_reiwa_short(view_year)
submit_name = f"{reiwa_short}_年間指導時数集計_{school_short}_{today_str}.csv"

st.download_button(
    label="⬇️ 区教委提出用CSVをダウンロード",
    data=submit_csv,
    file_name=submit_name,
    mime="text/csv",
)

