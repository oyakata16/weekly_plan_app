# ===========================================
# weekly_plan_app.py（操作ログ＋教員別時数一覧つき）
# ===========================================
# ・教員：週案を「一週間×1～6校時＋学校裁量枠」の表で作成し提出
# ・管理職：内容を確認して承認／差戻
# ・承認時に、教科ごとの時数を自動集計して年間累積に反映
# ・操作ログ：提出日時／承認日時／承認者を記録・表示
# ・教員別・学年別の年間時数一覧を表示（承認済み週案ベース）
# ===========================================

import streamlit as st
import sqlite3
from datetime import date
import json
import pandas as pd

# ------------------------------
# 管理職用パスワード
# ------------------------------
# そのまま使う場合の初期パスワード → "higakoma2025"
# 変更したい場合は、下の "higakoma2025" をお好きな文字列に書き換えてください。
# （将来、Secrets側に ADMIN_PASSWORD を設定した場合はそちらが優先されます）
DEFAULT_ADMIN_PASSWORD = "higakoma2025"
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)

# ------------------------------
# 画面全体の見栄え調整（フォントや枠の大きさ・印刷用CSS）
# ------------------------------
st.markdown(
    """
    <style>
    /* 全体の文字サイズを少し大きく */
    html, body, [class*="css"]  {
        font-size: 16px;
    }

    /* セレクトボックス本体の幅と折り返し */
    div[data-baseweb="select"] {
        font-size: 14px !important;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
        width: 100% !important;
        min-width: 140px !important;
    }

    /* プルダウン内の文字サイズと折り返し */
    div[data-baseweb="select"] span {
        font-size: 14px !important;
        white-space: normal !important;
        line-height: 1.3 !important;
    }

    /* テキストエリアの文字サイズと高さ */
    textarea {
        font-size: 14px !important;
    }

    /* 状態ラベル用（提出／承認／差戻） */
    .status-label {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        color: white;
    }
    .status-teishutsu {
        background-color: #f39c12; /* オレンジ */
    }
    .status-shonin {
        background-color: #27ae60; /* 緑 */
    }
    .status-sashimodoshi {
        background-color: #c0392b; /* 赤 */
    }

    /* 印刷時にサイドバーなどを隠す */
    @media print {
        header, footer, .stSidebar {
            display: none !important;
        }
        .main .block-container {
            padding-top: 0px !important;
            padding-bottom: 0px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 列幅（左端の「校時」列を細め、曜日列を広めに）
COLUMN_WIDTHS = [0.7] + [1.6] * 6  # 1 + 6列分

# ------------------------------
# データベースファイル
# ------------------------------
DB_PATH = "weekly_plans.db"

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

# 週案の記録
cur.execute("""
CREATE TABLE IF NOT EXISTS weekly_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher TEXT,
    grade TEXT,
    week TEXT,
    plan_json TEXT,   -- 時間割（教科＋内容）と集計結果をJSONで保存
    status TEXT,
    submitted_at TEXT,
    approved_at TEXT,
    approved_by TEXT
)
""")

# 既存DBをアップグレード（列がなければ追加）
for col in ["submitted_at", "approved_at", "approved_by"]:
    try:
        cur.execute(f"ALTER TABLE weekly_plans ADD COLUMN {col} TEXT")
    except sqlite3.OperationalError:
        # すでに列がある場合などは無視
        pass

# 年間の累積時数（45分換算）
cur.execute("""
CREATE TABLE IF NOT EXISTS hours_total (
    grade TEXT,
    subject TEXT,
    consumed REAL,
    PRIMARY KEY(grade, subject)
)
""")

conn.commit()

# ------------------------------
# 学年ごとの標準時数（45分×回数）※例示値
# ------------------------------
STANDARD_HOURS = {
    "1年": {
        "国語": 306,
        "算数": 140,
        "生活": 102,
        "音楽": 68,
        "図工": 68,
        "体育": 102,
        "道徳": 34,
        "特活": 34,
        "学校行事": 0,
        "読書科": 70,
        "学校裁量（学力向上）": 35,
        "学校裁量（探究）": 35,
    },

    "2年": {
        "国語": 280,
        "算数": 140,
        "生活": 102,
        "音楽": 68,
        "図工": 68,
        "体育": 102,
        "道徳": 35,
        "特活": 35,
        "学校行事": 0,
        "読書科": 70,
        "学校裁量（学力向上）": 35,
        "学校裁量（探究）": 35,
    },

    "3年": {
        "国語": 210,
        "社会": 70,
        "算数": 175,
        "理科": 70,
        "音楽": 50,
        "図工": 50,
        "体育": 105,
        "道徳": 35,
        "特活": 35,
        "外国語活動": 35,
        "総合的な学習の時間": 70,
        "学校行事": 0,
        "読書科": 70,
        "学校裁量（学力向上）": 35,
        "学校裁量（探究）": 35,
    },

    "4年": {
        "国語": 175,
        "社会": 105,
        "算数": 175,
        "理科": 105,
        "音楽": 50,
        "図工": 50,
        "体育": 105,
        "道徳": 35,
        "特活": 35,
        "外国語活動": 35,
        "総合的な学習の時間": 70,
        "家庭科": 0,
        "クラブ": 10,
        "学校行事": 0,
        "読書科": 70,
        "学校裁量（学力向上）": 35,
        "学校裁量（探究）": 35,
    },

    "5年": {
        "国語": 175,
        "社会": 105,
        "算数": 175,
        "理科": 105,
        "音楽": 45,
        "図工": 45,
        "家庭科": 70,
        "体育": 90,
        "道徳": 35,
        "特活": 35,
        "外国語": 70,
        "総合的な学習の時間": 70,
        "クラブ": 10,
        "委員会": 10,
        "学校行事": 0,
        "読書科": 70,
        "学校裁量（学力向上）": 35,
        "学校裁量（探究）": 35,
    },

    "6年": {
        "国語": 175,
        "社会": 105,
        "算数": 140,
        "理科": 105,
        "音楽": 45,
        "図工": 45,
        "家庭科": 70,
        "体育": 90,
        "道徳": 35,
        "特活": 35,
        "外国語": 70,
        "総合的な学習の時間": 70,
        "クラブ": 10,
        "委員会": 10,
        "学校行事": 0,
        "読書科": 70,
        "学校裁量（学力向上）": 35,
        "学校裁量（探究）": 35,
    },
}

def get_subjects_for_grade(grade: str):
    """学年ごとに使える教科等の一覧を返す"""
    return list(STANDARD_HOURS[grade].keys())

# ------------------------------
# 時間割の枠組み
# ------------------------------
DAYS = ["月", "火", "水", "木", "金", "土"]
PERIODS = ["1校時", "2校時", "3校時", "4校時", "5校時", "学校裁量", "6校時"]

# 1コマあたりの分数
PERIOD_MINUTES = {}
for day in DAYS:
    PERIOD_MINUTES[day] = {}
    for period in PERIODS:
        if period == "学校裁量":
            if day in ["月", "火", "木", "金"]:
                PERIOD_MINUTES[day][period] = 45
            else:
                PERIOD_MINUTES[day][period] = 0
        else:
            num = int(period[0])  # "1校時" → 1
            if num <= 5:
                PERIOD_MINUTES[day][period] = 40
            else:
                PERIOD_MINUTES[day][period] = 45

# ------------------------------
# 分 → 45分換算
# ------------------------------
def convert_to_45(mins):
    return mins / 45

# ------------------------------
# 年間の累積時数に加算（学年×教科）
# ------------------------------
def add_hours(grade, subject, minutes):
    add_45 = convert_to_45(minutes)

    cur.execute(
        "SELECT consumed FROM hours_total WHERE grade=? AND subject=?",
        (grade, subject)
    )
    row = cur.fetchone()

    if row:
        new_value = row[0] + add_45
        cur.execute(
            "UPDATE hours_total SET consumed=? WHERE grade=? AND subject=?",
            (new_value, grade, subject)
        )
    else:
        cur.execute(
            "INSERT INTO hours_total (grade, subject, consumed) VALUES (?, ?, ?)",
            (grade, subject, add_45)
        )

    conn.commit()

# ------------------------------
# 状態ラベル（HTML）を作る
# ------------------------------
def status_badge(status: str) -> str:
    cls = "status-teishutsu"
    if status == "承認":
        cls = "status-shonin"
    elif status == "差戻":
        cls = "status-sashimodoshi"
    return f'<span class="status-label {cls}">{status}</span>'

# ------------------------------
# 印刷用の表（DataFrame）を作る
# ------------------------------
def build_print_df(timetable: dict) -> pd.DataFrame:
    rows = []
    index = []

    for period in PERIODS:
        has_any_slot = any(PERIOD_MINUTES[day][period] > 0 for day in DAYS)
        if not has_any_slot:
            continue

        row = []
        for day in DAYS:
            mins = PERIOD_MINUTES[day][period]
            if mins <= 0:
                row.append("")
                continue

            cell = timetable.get(day, {}).get(period, {})
            subj = cell.get("subject", "")
            cont = cell.get("content", "")

            text = ""
            if subj and subj != "（空欄）":
                text = subj
            if cont:
                if text:
                    text += "\n" + cont
                else:
                    text = cont

            if text:
                text = f"[{mins}分] " + text

            row.append(text)

        rows.append(row)
        index.append(period)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, index=index, columns=DAYS)

# ------------------------------
# 管理職ログイン状態（セッション管理）
# ------------------------------
if "manager_authenticated" not in st.session_state:
    st.session_state["manager_authenticated"] = False

def require_manager_login():
    """管理職画面に入る前に呼び出す。
    認証されていなければパスワード入力を促し、認証されるまで処理を止める。
    """
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

    # 認証されていない間は本文を表示しない
    if not st.session_state["manager_authenticated"]:
        st.warning("管理職専用画面です。サイドバーからパスワードを入力してください。")
        st.stop()

# ------------------------------
# 画面タイトル・利用者区分
# ------------------------------
st.title("小学校 週の指導計画（週案）管理システム（クラウド版）")

role = st.sidebar.selectbox("利用者区分", ["教員", "管理職"])

# ======================================================
#  教員画面：週案の入力と提出（表形式＋印刷）
# ======================================================
if role == "教員":
    st.header("📘 週案の作成・提出（教員用）")

    teacher = st.text_input("教員名（フルネームでも短縮でも可）")
    grade = st.selectbox("学年", list(STANDARD_HOURS.keys()))
    week = st.date_input("対象週（週の初日：月曜日など）", value=date.today())

    grade_subjects = get_subjects_for_grade(grade)
    subject_options = ["（空欄）"] + grade_subjects

    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    st.caption("※ 行：校時／列：曜日。各マスで「教科等」と「授業内容」を入力します。")

    timetable = {}

    # ヘッダー行（曜日）
    header_cols = st.columns(COLUMN_WIDTHS)
    header_cols[0].write("　")
    for i, day in enumerate(DAYS, start=1):
        header_cols[i].write(f"**{day}**")

    # 校時ごとに1行ずつ表示
    for period in PERIODS:
        has_any_slot = any(PERIOD_MINUTES[day][period] > 0 for day in DAYS)
        if not has_any_slot:
            continue

        row_cols = st.columns(COLUMN_WIDTHS)
        row_cols[0].write(f"**{period}**")

        for j, day in enumerate(DAYS, start=1):
            if day not in timetable:
                timetable[day] = {}

            minutes = PERIOD_MINUTES[day][period]

            with row_cols[j]:
                if minutes == 0:
                    st.write("―")
                    subject = "（空欄）"
                    content = ""
                else:
                    st.caption(f"{minutes}分")
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

            timetable[day][period] = {
                "subject": subject,
                "content": content,
            }

    # 自動で教科ごとの分数を集計
    subject_minutes = {s: 0 for s in grade_subjects}
    for day in DAYS:
        for period in PERIODS:
            if day not in timetable or period not in timetable[day]:
                continue
            minutes = PERIOD_MINUTES[day][period]
            if minutes <= 0:
                continue
            cell = timetable[day][period]
            subject = cell["subject"]
            if subject in subject_minutes:
                subject_minutes[subject] += minutes

    st.markdown("#### この週の教科別 合計分数（自動計算）")
    for subject in grade_subjects:
        st.write(f"- {subject}: {subject_minutes[subject]} 分")

    # 印刷レイアウト
    st.markdown("#### 📄 印刷・PDF保存用レイアウト（教員用）")
    if st.checkbox("この週案を印刷用に表示する"):
        df_print = build_print_df(timetable)
        if df_print.empty:
            st.info("有効なコマがありません。時間割を入力してください。")
        else:
            st.write(f"**{grade}／{teacher}／{week} の週案（印刷用）**")
            st.table(df_print)
            st.info(
                "ブラウザの印刷機能（Ctrl+P または スマホの共有→プリント）から "
                "PDF 保存・印刷を行ってください。"
            )

    if st.button("✅ この内容で管理職へ提出する"):
        plan = {
            "timetable": timetable,
            "subject_minutes": subject_minutes,
        }
        cur.execute(
            """
            INSERT INTO weekly_plans
              (teacher, grade, week, plan_json, status, submitted_at)
            VALUES
              (?, ?, ?, ?, '提出', DATETIME('now'))
        """,
            (teacher, grade, str(week), json.dumps(plan, ensure_ascii=False)),
        )
        conn.commit()
        st.success("週案を提出しました。管理職の承認をお待ちください。")

# ======================================================
#  管理職画面：承認・差戻／年間累積時数（表形式＋印刷＋操作ログ＋教員別）
# ======================================================
if role == "管理職":
    # まずログイン必須
    require_manager_login()

    st.header("📝 提出された週案一覧（管理職用）")
    st.caption("① 状態別件数 → ② 内容確認 → ③ 承認／差戻 → ④ 年間累積と教員別一覧を確認")

    # 新しい順に取得（操作ログ用に submitted_at, approved_at, approved_by も取得）
    cur.execute(
        """
        SELECT id, teacher, grade, week, plan_json, status, submitted_at, approved_at, approved_by
        FROM weekly_plans
        ORDER BY id DESC
    """
    )
    all_rows = cur.fetchall()

    # 状態別件数
    counts = {"提出": 0, "承認": 0, "差戻": 0}
    for row in all_rows:
        stt = row[5]
        if stt in counts:
            counts[stt] += 1

    st.markdown("#### 状態別件数")
    st.write(f"- 提出：{counts['提出']} 件")
    st.write(f"- 承認：{counts['承認']} 件")
    st.write(f"- 差戻：{counts['差戻']} 件")

    # 状態で絞り込み
    filter_status = st.selectbox("表示する状態", ["すべて", "提出", "承認", "差戻"])
    if filter_status == "すべて":
        rows = all_rows
    else:
        rows = [r for r in all_rows if r[5] == filter_status]

    if not rows:
        st.info("該当する週案はありません。")
    else:
        st.caption("※ 各行をクリックすると詳細（時間割＋内容＋印刷用レイアウト＋操作履歴）が表示されます。")

    rerun_needed = False

    for row in rows:
        (
            wid,
            teacher,
            grade,
            week,
            plan_json,
            status,
            submitted_at,
            approved_at,
            approved_by,
        ) = row
        plan = json.loads(plan_json)
        timetable = plan.get("timetable", {})
        subject_minutes = plan.get("subject_minutes", {})

        grade_subjects = get_subjects_for_grade(grade)

        badge_html = status_badge(status)
        expander_title = f"ID:{wid} / {week} / {grade} / {teacher} / 状態：{status}"

        with st.expander(expander_title):
            st.markdown(f"状態：{badge_html}", unsafe_allow_html=True)

            st.markdown("#### 操作履歴")
            st.write(f"- 提出者：{teacher}")
            st.write(f"- 提出日時：{submitted_at if submitted_at else '（記録なし）'}")
            if approved_at:
                st.write(f"- 承認日時：{approved_at}")
                st.write(f"- 承認者：{approved_by if approved_by else '管理職'}")
            else:
                st.write("- 承認：未承認")

            st.markdown("#### 一週間の時間割（教科等＋内容）")

            # ヘッダー行
            header_cols = st.columns(COLUMN_WIDTHS)
            header_cols[0].write("　")
            for i, day in enumerate(DAYS, start=1):
                header_cols[i].write(f"**{day}**")

            # 校時ごとに1行
            for period in PERIODS:
                has_any_slot = any(PERIOD_MINUTES[day][period] > 0 for day in DAYS)
                if not has_any_slot:
                    continue

                row_cols = st.columns(COLUMN_WIDTHS)
                row_cols[0].write(f"**{period}**")
                for j, day in enumerate(DAYS, start=1):
                    with row_cols[j]:
                        minutes = PERIOD_MINUTES[day][period]
                        if minutes <= 0:
                            st.write("―")
                            continue
                        cell = timetable.get(day, {}).get(period, {})
                        subj = cell.get("subject", "（空欄）")
                        cont = cell.get("content", "")
                        st.caption(f"{minutes}分")
                        st.write(f"{subj}")
                        if cont:
                            st.caption(cont)

            st.markdown("#### 教科別 合計分数（この週）")
            for subject in grade_subjects:
                mins = subject_minutes.get(subject, 0)
                st.write(f"- {subject}: {mins} 分")

            # 印刷用
            st.markdown("#### 📄 印刷・PDF保存用レイアウト（この週案）")
            df_print = build_print_df(timetable)
            if df_print.empty:
                st.info("有効なコマがありません。")
            else:
                st.table(df_print)
                st.caption("※必要に応じてブラウザの印刷機能からPDF保存・印刷してください。")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"✅ 承認する（ID:{wid}）", key=f"approve_{wid}"):
                    if status != "承認":
                        # 学年×教科の年間累積に加算
                        for subject, minutes in subject_minutes.items():
                            if minutes > 0:
                                add_hours(grade, subject, minutes)
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
                        rerun_needed = True
                    else:
                        st.info("すでに承認済みです。")

            with col2:
                if st.button(f"↩ 差戻にする（ID:{wid}）", key=f"reject_{wid}"):
                    if status != "差戻":
                        cur.execute(
                            "UPDATE weekly_plans SET status='差戻' WHERE id=?",
                            (wid,),
                        )
                        conn.commit()
                        st.warning("差戻にしました。教員側で修正して再提出してもらってください。")
                        rerun_needed = True
                    else:
                        st.info("すでに差戻済みです。")

    if rerun_needed:
        st.experimental_rerun()

    # --------------------------------------
    # 操作ログ一覧（全件）
    # --------------------------------------
    st.header("📚 操作ログ一覧")

    log_rows = []
    for row in all_rows:
        (
            wid,
            teacher,
            grade,
            week,
            plan_json,
            status,
            submitted_at,
            approved_at,
            approved_by,
        ) = row
        log_rows.append(
            {
                "ID": wid,
                "学年": grade,
                "教員": teacher,
                "週": week,
                "状態": status,
                "提出日時": submitted_at,
                "承認日時": approved_at,
                "承認者": approved_by,
            }
        )

    if log_rows:
        st.table(log_rows)
    else:
        st.info("まだ提出された週案がありません。")

    # --------------------------------------
    # 年間累積時数の状況（学年×教科）
    # --------------------------------------
    st.header("📊 年間累積時数の状況（45分コマ換算・学年×教科）")

    for grade in STANDARD_HOURS.keys():
        st.subheader(f"{grade}の時数状況")

        grade_subjects = get_subjects_for_grade(grade)
        table_rows = []

        for subject in grade_subjects:
            std = STANDARD_HOURS[grade][subject]

            cur.execute(
                "SELECT consumed FROM hours_total WHERE grade=? AND subject=?",
                (grade, subject),
            )
            row = cur.fetchone()
            used = row[0] if row else 0.0
            remain = std - used

            table_rows.append(
                {
                    "教科等": subject,
                    "標準（45分コマ）": std,
                    "実施累積（45分コマ）": round(used, 1),
                    "残り（45分コマ）": round(remain, 1),
                }
            )

        if table_rows:
            st.table(table_rows)
        else:
            st.info("まだ承認された週案がありません。")

    # --------------------------------------
    # 教員別・年間時数一覧（承認済み週案ベース）
    # --------------------------------------
    st.header("👩‍🏫 教員別・年間時数一覧（承認済み週案ベース）")

    # 教員別集計：weekly_plans（承認済み）の subject_minutes を使って計算
    cur.execute(
        """
        SELECT teacher, grade, plan_json, status
        FROM weekly_plans
    """
    )
    rows_for_teacher = cur.fetchall()

    teacher_totals = {}  # (grade, teacher, subject) -> 45分コマ

    for teacher, grade, plan_json, status in rows_for_teacher:
        if status != "承認":
            continue
        plan = json.loads(plan_json)
        subject_minutes = plan.get("subject_minutes", {})
        for subject, minutes in subject_minutes.items():
            if minutes <= 0:
                continue
            key = (grade, teacher, subject)
            teacher_totals[key] = teacher_totals.get(key, 0) + convert_to_45(minutes)

    for grade in STANDARD_HOURS.keys():
        st.subheader(f"{grade}の教員別時数状況")
        rows_table = []
        for (g, t, subject), total_45 in teacher_totals.items():
            if g != grade:
                continue
            rows_table.append(
                {
                    "教員": t,
                    "教科等": subject,
                    "実施累積（45分コマ）": round(total_45, 1),
                }
            )

        if rows_table:
            st.table(rows_table)
        else:
            st.info("まだ承認済み週案がありません。")
