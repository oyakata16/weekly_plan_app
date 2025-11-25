# ===========================================
# weekly_plan_app.py
# 小学校 週の指導計画（週案）管理システム
# ・教員：週案を「一週間×1～6校時＋学校裁量枠」の表で作成し提出
# ・管理職：内容を確認して承認／差戻
# ・承認時に、教科ごとの時数を自動集計して年間累積に反映
# ・40分授業／45分授業 混在OK（コマごとの分数を自動計算）
# ・1・2年：生活科あり／理科・社会・総合なし
# ・3・4年：理科・社会・総合・外国語活動あり／生活科なし
# ・5・6年：理科・社会・総合・外国語あり／生活科なし
# ・全学年：読書科・学校裁量（学力向上）・学校裁量（探究）・学校行事あり
# ・5・6年：家庭科・クラブ・委員会あり（4年はクラブのみ）
# ・5校時と6校時の間に「学校裁量」45分枠（月・火・木・金のみ）
# ===========================================

import streamlit as st
import sqlite3
from datetime import date
import json

# ------------------------------
# 画面全体の見栄え調整（フォントや枠の大きさ）
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
        font-size: 13px !important;
        white-space: normal !important;
    }

    /* プルダウン内の文字サイズと折り返し */
    div[data-baseweb="select"] span {
        font-size: 13px !important;
        white-space: normal !important;
        line-height: 1.3 !important;
    }

    /* テキストエリアの文字サイズと高さ */
    textarea {
        font-size: 14px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 列幅（左端の「校時」列を細め、曜日列を広めに）
COLUMN_WIDTHS = [0.7] + [1.6] * 6  # 1 + 6列分

# ------------------------------
# データベースファイル（クラウドでもローカルでも同じフォルダに置く）
# ------------------------------
DB_PATH = "weekly_plans.db"

# ------------------------------
# 記録用ファイル（SQLite）の準備
# ------------------------------
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
    submitted_at TEXT
)
""")

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
#   学習指導要領の科目順になるように並べています
#   （数値は必要に応じて調整してください）
# ------------------------------
STANDARD_HOURS = {
    # 1・2年：生活科あり／理科・社会・総合なし
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
    # 3・4年：生活なし／理科・社会・総合・外国語活動あり
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
        "家庭科": 0,  # 必要なら時数を設定
        "学校行事": 0,
        "読書科": 70,
        "クラブ": 10,
        "学校裁量（学力向上）": 35,
        "学校裁量（探究）": 35,
    },
    # 5・6年：生活なし／理科・社会・総合・外国語・家庭科あり
    "5年": {
        "国語": 175,
        "社会": 105,
        "算数": 175,
        "理科": 105,
        "音楽": 45,
        "図工": 45,
        "家庭科": 70,  # 目安。必要なら変更
        "体育": 90,
        "道徳": 35,
        "特活": 35,
        "外国語": 70,
        "外国語活動": 0,  # 必要に応じて活動もここで扱うなら活用
        "総合的な学習の時間": 70,
        "学校行事": 0,
        "読書科": 70,
        "クラブ": 10,
        "委員会": 10,
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
        "外国語活動": 0,
        "総合的な学習の時間": 70,
        "学校行事": 0,
        "読書科": 70,
        "クラブ": 10,
        "委員会": 10,
        "学校裁量（学力向上）": 35,
        "学校裁量（探究）": 35,
    },
}

def get_subjects_for_grade(grade: str):
    """学年ごとに使える教科等の一覧を返す
    ※ dict の定義順（=学習指導要領順）をそのまま使う
    """
    return list(STANDARD_HOURS[grade].keys())

# ------------------------------
# 時間割の枠組み
#   行：1校時～6校時＋学校裁量枠
#   列：月～土
# ------------------------------
DAYS = ["月", "火", "水", "木", "金", "土"]
# 5校時と6校時の間に「学校裁量」枠を入れる
PERIODS = ["1校時", "2校時", "3校時", "4校時", "5校時", "学校裁量", "6校時"]

# 1コマあたりの分数
# ・1～5校時：40分
# ・学校裁量枠：45分（※月・火・木・金のみ。水・土は0分扱い）
# ・6校時：45分
PERIOD_MINUTES = {}
for day in DAYS:
    PERIOD_MINUTES[day] = {}
    for period in PERIODS:
        if period == "学校裁量":
            # 学校裁量枠は 月・火・木・金 のみ45分
            if day in ["月", "火", "木", "金"]:
                PERIOD_MINUTES[day][period] = 45
            else:
                PERIOD_MINUTES[day][period] = 0  # 水・土は枠なし
        else:
            # 「○校時」から数字を取って分を決める
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
# 年間の累積時数に加算
# grade: "1年" など
# subject: "国語" など
# minutes: その週に行った分数の合計
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
# 画面のタイトル＆利用者区分
# ------------------------------
st.title("小学校 週の指導計画（週案）管理システム")

role = st.sidebar.selectbox("利用者区分", ["教員", "管理職"])

# ======================================================
#  教員画面：週案の入力と提出（表形式）
# ======================================================
if role == "教員":
    st.header("📘 週案の作成・提出（表形式）")

    teacher = st.text_input("教員名（フルネームでも短縮でも可）")
    grade = st.selectbox("学年", list(STANDARD_HOURS.keys()))
    week = st.date_input("対象週（週の初日：月曜日など）", value=date.today())

    # 学年に応じた教科等
    grade_subjects = get_subjects_for_grade(grade)
    subject_options = ["（空欄）"] + grade_subjects

    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    st.caption("※ 行：校時／列：曜日。各マスで「教科等」と「授業内容」を入力します。")

    # 時間割データの入れ物
    timetable = {}

    # ヘッダー行（曜日）
    header_cols = st.columns(COLUMN_WIDTHS)
    header_cols[0].write("　")
    for i, day in enumerate(DAYS, start=1):
        header_cols[i].write(f"**{day}**")

    # 校時ごとに1行ずつ表示
    for period in PERIODS:
        # その行に、有効な（分数>0）のコマが1つもない場合は飛ばす（水・土の学校裁量だけの行など）
        has_any_slot = any(PERIOD_MINUTES[day][period] > 0 for day in DAYS)
        if not has_any_slot:
            continue

        row_cols = st.columns(COLUMN_WIDTHS)
        # 左端に「1校時（40分）」など
        row_cols[0].write(f"**{period}**")

        for j, day in enumerate(DAYS, start=1):
            if day not in timetable:
                timetable[day] = {}

            minutes = PERIOD_MINUTES[day][period]

            with row_cols[j]:
                if minutes == 0:
                    # コマが存在しない枠（水・土の学校裁量など）は表示だけ空欄にする
                    st.write("―")
                    subject = "（空欄）"
                    content = ""
                else:
                    st.caption(f"{minutes}分")
                    subject = st.selectbox(
                        "教科等",
                        subject_options,
                        key=f"{day}_{period}_subject",
                        label_visibility="collapsed"
                    )
                    content = st.text_area(
                        "内容",
                        key=f"{day}_{period}_content",
                        height=60,
                        label_visibility="collapsed"
                    )

            timetable[day][period] = {
                "subject": subject,
                "content": content
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

    if st.button("この内容で管理職へ提出する"):
        plan = {
            "timetable": timetable,
            "subject_minutes": subject_minutes
        }
        cur.execute("""
            INSERT INTO weekly_plans
              (teacher, grade, week, plan_json, status, submitted_at)
            VALUES
              (?, ?, ?, ?, '提出', DATE('now'))
        """, (teacher, grade, str(week), json.dumps(plan, ensure_ascii=False)))
        conn.commit()
        st.success("週案を提出しました。管理職の承認をお待ちください。")

# ======================================================
#  管理職画面：承認・差戻／年間累積時数の確認
# ======================================================
if role == "管理職":
    st.header("📝 提出された週案一覧")

    # 新しい順に表示
    cur.execute("""
        SELECT id, teacher, grade, week, plan_json, status
        FROM weekly_plans
        ORDER BY id DESC
    """)
    rows = cur.fetchall()

    for row in rows:
        wid, teacher, grade, week, plan_json, status = row
        plan = json.loads(plan_json)
        timetable = plan.get("timetable", {})
        subject_minutes = plan.get("subject_minutes", {})

        grade_subjects = get_subjects_for_grade(grade)

        with st.expander(f"ID:{wid} / {week} / {grade} / {teacher} / 状態：{status}"):
            st.markdown("#### 一週間の時間割（教科等＋内容：表形式表示）")

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
                        subject = cell.get("subject", "（空欄）")
                        content = cell.get("content", "")
                        st.caption(f"{minutes}分")
                        st.write(f"{subject}")
                        if content:
                            st.caption(content)

            st.markdown("#### 教科別 合計分数（この週）")
            for subject in grade_subjects:
                mins = subject_minutes.get(subject, 0)
                st.write(f"- {subject}: {mins} 分")

            # 承認ボタン
            if st.button(f"承認する（ID:{wid}）"):
                for subject, minutes in subject_minutes.items():
                    if minutes > 0:
                        add_hours(grade, subject, minutes)

                cur.execute(
                    "UPDATE weekly_plans SET status='承認' WHERE id=?",
                    (wid,)
                )
                conn.commit()
                st.success("承認しました。年間累積時数に反映済みです。")

            # 差戻ボタン
            if st.button(f"差戻にする（ID:{wid}）"):
                cur.execute(
                    "UPDATE weekly_plans SET status='差戻' WHERE id=?",
                    (wid,)
                )
                conn.commit()
                st.warning("差戻にしました。教員側で修正して再提出してもらってください。")

    # --------------------------------------
    # 年間累積時数の状況
    # --------------------------------------
    st.header("📊 年間累積時数の状況（45分換算）")

    for grade in STANDARD_HOURS.keys():
        st.subheader(f"{grade}の時数状況")

        grade_subjects = get_subjects_for_grade(grade)

        for subject in grade_subjects:
            std = STANDARD_HOURS[grade][subject]

            cur.execute(
                "SELECT consumed FROM hours_total WHERE grade=? AND subject=?",
                (grade, subject)
            )
            row = cur.fetchone()
            used = row[0] if row else 0
            remain = std - used

            st.write(f"● {subject}")
            st.write(f"- 標準：{std}（45分コマ換算）")
            st.write(f"- 実施累積：{round(used, 1)}（45分コマ換算）")
            st.write(f"- 残り：**{round(remain, 1)}**（45分コマ換算）")

            ratio = used / std if std > 0 else 0
            if ratio < 0:
                ratio = 0
            if ratio > 1:
                ratio = 1
            st.progress(ratio)
