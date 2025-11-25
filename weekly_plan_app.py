# ===========================================
# weekly_plan_app.py（改良版）
# 小学校 週の指導計画（週案）管理システム
# ・教員：週案を「一週間×1～6校時＋学校裁量枠」の表で作成し提出
# ・管理職：内容を確認して承認／差戻
# ・承認時に、教科ごとの時数を自動集計して年間累積に反映
# ・40分授業／45分授業 混在OK（コマごとの分数を自動計算）
# ・1・2年：生活科あり／理科・社会・総合なし
# ・3・4年：理科・社会・総合・外国語活動あり
# ・5・6年：理科・社会・総合・外国語・家庭科・クラブ・委員会あり
# ・全学年：読書科・学校裁量（学力向上）・学校裁量（探究）・学校行事あり
# ・5校時と6校時の間に「学校裁量」45分枠（月・火・木・金のみ）
#
# 【今回の改良点】
# 1) 教科プルダウンを見やすく（幅拡大＋折り返し＋文字サイズ）
# 2) 管理職画面の承認フローを整理
#    - 状態別の件数サマリ
#    - 状態で絞り込み（提出／承認／差戻／すべて）
#    - 状態を色付きラベルで表示
# 3) 年間累積時数を「表形式」で表示（標準・累積・残り）
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
    """学年ごとに使える教科等の一覧を返す"""
    return list(STANDARD_HOURS[grade].keys())

# ------------------------------
# 時間割の枠組み
# ------------------------------
DAYS = ["月", "火", "水", "木", "金", "土"]
# 5校時と6校時の間に「学校裁量」枠を入れる
PERIODS = ["1校時", "2校時", "3校時", "4校時", "5校時", "学校裁量", "6校時"]

# 1コマあたりの分数
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
    text = status
    if status == "承認":
        cls = "status-shonin"
    elif status == "差戻":
        cls = "status-sashimodoshi"
    return f'<span class="status-label {cls}">{text}</span>'

# ------------------------------
# 画面のタイトル＆利用者区分
# ------------------------------
st.title("小学校 週の指導計画（週案）管理システム（クラウド版）")

role = st.sidebar.selectbox("利用者区分", ["教員", "管理職"])

# ======================================================
#  教員画面：週案の入力と提出（表形式）
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
                        label_visibility="collapsed"  # ラベルは用意しつつ画面上は隠す
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

    if st.button("✅ この内容で管理職へ提出する"):
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
    st.header("📝 提出された週案一覧（管理職用）")

    # 新しい順に取得
    cur.execute("""
        SELECT id, teacher, grade, week, plan_json, status
        FROM weekly_plans
        ORDER BY id DESC
    """)
    all_rows = cur.fetchall()

    # 状態別件数を数える
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
        st.caption("※ 各行をクリックすると詳細（時間割＋内容）が表示されます。")

    # 承認・差戻ボタン押下後に画面を更新するためのフラグ
    rerun_needed = False

    for row in rows:
        wid, teacher, grade, week, plan_json, status = row
        plan = json.loads(plan_json)
        timetable = plan.get("timetable", {})
        subject_minutes = plan.get("subject_minutes", {})

        grade_subjects = get_subjects_for_grade(grade)

        # 状態バッジ
        badge_html = status_badge(status)
        exp_label = f"ID:{wid} / {week} / {grade} / {teacher} / 状態："
        expander_title = exp_label + status

        with st.expander(expander_title):
            st.markdown(
                f"状態：{badge_html}",
                unsafe_allow_html=True
            )

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

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"✅ 承認する（ID:{wid}）", key=f"approve_{wid}"):
                    # 承認済みの場合は二重反映を防ぐ
                    if status != "承認":
                        for subject, minutes in subject_minutes.items():
                            if minutes > 0:
                                add_hours(grade, subject, minutes)

                        cur.execute(
                            "UPDATE weekly_plans SET status='承認' WHERE id=?",
                            (wid,)
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
                            (wid,)
                        )
                        conn.commit()
                        st.warning("差戻にしました。教員側で修正して再提出してもらってください。")
                        rerun_needed = True
                    else:
                        st.info("すでに差戻済みです。")

    # ボタン操作後に一覧を更新
    if rerun_needed:
        st.experimental_rerun()

    # --------------------------------------
    # 年間累積時数の状況（表形式）
    # --------------------------------------
    st.header("📊 年間累積時数の状況（45分コマ換算・表形式）")

    for grade in STANDARD_HOURS.keys():
        st.subheader(f"{grade}の時数状況")

        grade_subjects = get_subjects_for_grade(grade)
        table_rows = []

        for subject in grade_subjects:
            std = STANDARD_HOURS[grade][subject]

            cur.execute(
                "SELECT consumed FROM hours_total WHERE grade=? AND subject=?",
                (grade, subject)
            )
            row = cur.fetchone()
            used = row[0] if row else 0.0
            remain = std - used

            table_rows.append({
                "教科等": subject,
                "標準（45分コマ）": std,
                "実施累積（45分コマ）": round(used, 1),
                "残り（45分コマ）": round(remain, 1),
            })

        # 表として表示
        if table_rows:
            st.table(table_rows)
        else:
            st.info("まだ承認された週案がありません。")
