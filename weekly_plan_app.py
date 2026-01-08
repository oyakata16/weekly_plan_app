# ===========================================
# weekly_plan_app.py
# 担任＋専科ハイブリッド版（A案）
# ・担任：学年ごとの教科リストで週案作成
# ・専科：主担当教科を設定しつつ、
#          各コマで「学級」「教科」「内容」を自由に選択
# ・学級名から学年を推定して、学年×教科の年間累積に自動反映
# ・40分／45分コマ混在に対応
# ・管理職ログイン＋承認／差戻＋年間累積一覧
# ・管理職画面に「学年／教員／週／未承認」フィルタを追加
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
# 画面全体の見栄え調整
# ------------------------------
st.markdown(
    """
    <style>
    html, body, [class*="css"]  {
        font-size: 16px;
    }

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

    textarea {
        font-size: 14px !important;
    }

    .status-label {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        color: white;
    }
    .status-teishutsu {
        background-color: #f39c12;
    }
    .status-shonin {
        background-color: #27ae60;
    }
    .status-sashimodoshi {
        background-color: #c0392b;
    }

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
COLUMN_WIDTHS = [0.7] + [1.6] * 6

# ------------------------------
# データベース
# ------------------------------
DB_PATH = "weekly_plans.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

# 週案テーブル
cur.execute(
    """
CREATE TABLE IF NOT EXISTS weekly_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
for col in ["class", "teacher_type", "submitted_at", "approved_at", "approved_by"]:
    try:
        cur.execute(f"ALTER TABLE weekly_plans ADD COLUMN {col} TEXT")
    except sqlite3.OperationalError:
        pass

# 年間累積時数テーブル
cur.execute(
    """
CREATE TABLE IF NOT EXISTS hours_total (
    grade TEXT,
    subject TEXT,
    consumed REAL,
    PRIMARY KEY(grade, subject)
)
"""
)
conn.commit()

# ------------------------------
# 学年ごとの標準時数（45分換算コマ数）
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
    return list(STANDARD_HOURS[grade].keys())


# 専科用：全学年の教科リスト（重複なし）
ALL_SUBJECTS = sorted(
    {subj for g in STANDARD_HOURS.values() for subj in g.keys()}
)

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
# 年間累積時数を加算
# ------------------------------
def add_hours(grade: str, subject: str, minutes: float):
    add_45 = convert_to_45(minutes)
    cur.execute(
        "SELECT consumed FROM hours_total WHERE grade=? AND subject=?",
        (grade, subject),
    )
    row = cur.fetchone()
    if row:
        new_value = row[0] + add_45
        cur.execute(
            "UPDATE hours_total SET consumed=? WHERE grade=? AND subject=?",
            (new_value, grade, subject),
        )
    else:
        cur.execute(
            "INSERT INTO hours_total (grade, subject, consumed) VALUES (?, ?, ?)",
            (grade, subject, add_45),
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
    学級が判別できる場合はそちらを優先し、
    判別できない場合は base_grade でカウント。
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
            # その学年でカウント対象の教科だけ集計
            if subject not in STANDARD_HOURS[grade_for_slot]:
                continue
            result.setdefault(grade_for_slot, {})
            result[grade_for_slot][subject] = (
                result[grade_for_slot].get(subject, 0) + minutes
            )
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
# 画面タイトル・利用者区分
# ------------------------------
st.title("小学校 週の指導計画（週案）管理システム（クラウド版）")

role = st.sidebar.selectbox("利用者区分", ["教員", "管理職"])

# ======================================================
# 教員画面
# ======================================================
if role == "教員":
    st.header("📘 週案の作成・提出（教員用）")

    teacher = st.text_input("教員名")
    teacher_type = st.radio("勤務形態", ["担任", "専科（音楽・家庭科など）"])

    grade = st.selectbox("基準学年", list(STANDARD_HOURS.keys()))
    base_grade = grade
    class_name = st.text_input("自分の担任学級（例：3-1）※担任でなければ空欄可")
    week = st.date_input("対象週（週の初日：月曜日など）", value=date.today())

    # 担任用・専科用の教科リスト
    if teacher_type == "担任":
        grade_subjects = get_subjects_for_grade(grade)
        subject_options = ["（空欄）"] + grade_subjects
        st.caption("※ 担任は、その学年で扱う教科のみが選択できます。")
        class_candidates = [class_name] if class_name else []
    else:
        grade_subjects = get_subjects_for_grade(grade)
        subject_options = ["（空欄）"] + ALL_SUBJECTS
        main_subject = st.selectbox("主担当教科（参考情報）", ALL_SUBJECTS)
        st.info(
            "この週に指導する学級をカンマ区切りで入力してください。"
            "（例：3-1,3-2,4-1）"
        )
        classes_input = st.text_input(
            "指導学級一覧",
            value=class_name,
            help="複数学級に入る場合は 3-1,3-2,4-1 のように入力してください。",
        )
        class_candidates = [c.strip() for c in classes_input.split(",") if c.strip()]
        if class_candidates:
            st.caption("この週に指導する学級：" + "、".join(class_candidates))
        else:
            st.caption("※ 学級が未入力の場合、学級欄は空欄のままとなります。")

    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    st.caption("行：校時／列：曜日。各マスで「学級（専科）」「教科等」「内容」を入力します。")

    timetable = {}

    # ヘッダー
    header_cols = st.columns(COLUMN_WIDTHS)
    header_cols[0].write("　")
    for i, day in enumerate(DAYS, start=1):
        header_cols[i].write(f"**{day}**")

    # 各行
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
                    # 専科：学級選択＋教科選択
                    if teacher_type.startswith("専科"):
                        if class_candidates:
                            klass = st.selectbox(
                                "学級",
                                ["（未選択）"] + class_candidates,
                                key=f"{day}_{period}_class",
                                label_visibility="collapsed",
                            )
                            if klass == "（未選択）":
                                klass = ""
                        else:
                            klass = ""
                    else:
                        # 担任
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

    # 学年×教科ごとの分数集計（基準学年分のみ表示）
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
            st.write(f"**{base_grade}／{class_name}／{teacher}／{week} の週案（印刷用）**")
            st.table(df_print)
            st.info("ブラウザの印刷機能から PDF 保存・印刷を行ってください。")

    if st.button("✅ この内容で管理職へ提出する"):
        plan = {"timetable": timetable}
        cur.execute(
            """
            INSERT INTO weekly_plans
              (teacher, grade, class, teacher_type, week, plan_json, status, submitted_at)
            VALUES
              (?, ?, ?, ?, ?, ?, '提出', DATETIME('now'))
        """,
            (teacher, base_grade, class_name, teacher_type, str(week), json.dumps(plan, ensure_ascii=False)),
        )
        conn.commit()
        st.success("週案を提出しました。管理職の承認をお待ちください。")

# ======================================================
# 管理職画面
# ======================================================
if role == "管理職":
    require_manager_login()

    st.header("📝 提出された週案一覧（管理職用）")

    cur.execute(
        """
        SELECT id, teacher, grade, class, teacher_type, week,
               plan_json, status, submitted_at, approved_at, approved_by
        FROM weekly_plans
        ORDER BY id DESC
    """
    )
    all_rows = cur.fetchall()

    # 状態別件数
    counts = {"提出": 0, "承認": 0, "差戻": 0}
    for r in all_rows:
        stt = r[7]
        if stt in counts:
            counts[stt] += 1

    st.markdown("#### 状態別件数")
    st.write(f"- 提出：{counts['提出']} 件")
    st.write(f"- 承認：{counts['承認']} 件")
    st.write(f"- 差戻：{counts['差戻']} 件")

    # フィルタ用の候補
    grade_list = sorted({r[2] for r in all_rows if r[2]})
    teacher_list = sorted({r[1] for r in all_rows if r[1]})
    week_list = sorted({r[5] for r in all_rows if r[5]}, reverse=True)

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

    # フィルタ適用
    rows = all_rows

    if filter_status != "すべて":
        rows = [r for r in rows if r[7] == filter_status]

    if grade_filter != "すべて":
        rows = [r for r in rows if r[2] == grade_filter]

    if teacher_filter != "すべて":
        rows = [r for r in rows if r[1] == teacher_filter]

    if week_filter != "すべて":
        rows = [r for r in rows if r[5] == week_filter]

    if only_unapproved:
        rows = [r for r in rows if r[7] != "承認"]

    if not rows:
        st.info("該当する週案はありません。")
    else:
        st.caption("※ 各行をクリックすると詳細が表示されます。")

    for (
        wid,
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
        plan = json.loads(plan_json)
        timetable = plan.get("timetable", {})
        week_minutes_all = compute_week_subject_minutes(timetable, grade)
        subject_minutes_this_grade = week_minutes_all.get(grade, {})

        badge_html = status_badge(status)
        title = f"ID:{wid} / {week} / {grade} / {class_name} / {teacher} / 状態：{status}"

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

            st.markdown(f"#### 教科別 合計分数（{grade}）")
            for s in get_subjects_for_grade(grade):
                mins = subject_minutes_this_grade.get(s, 0)
                st.write(f"- {s}: {mins} 分")

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
                                add_hours(g, subj, mins)
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
                    else:
                        st.info("すでに差戻済みです。")

    # 年間累積時数一覧
# 年間累積時数一覧
st.header("📊 年間累積時数の状況（学年×教科／45分コマ換算）")
for g in STANDARD_HOURS.keys():
    st.subheader(f"{g}の時数状況")
    rows_table = []
    for subj in get_subjects_for_grade(g):
        std = STANDARD_HOURS[g][subj]
        cur.execute(
            "SELECT consumed FROM hours_total WHERE grade=? AND subject=?",
            (g, subj),
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
    if rows_table:
        st.table(rows_table)
    else:
        st.info("まだ承認された週案がありません。")


# ======================================================
# 🧰 バックアップ（Excel/CSV ダウンロード）
# ======================================================

def fetch_all_weekly_plans():
    cur.execute("""
        SELECT id, teacher, grade, class, teacher_type, week, plan_json, status,
               submitted_at, approved_at, approved_by
        FROM weekly_plans
        ORDER BY id DESC
    """)
    return cur.fetchall()

def fetch_hours_total():
    cur.execute("""
        SELECT grade, subject, consumed
        FROM hours_total
        ORDER BY grade, subject
    """)
    return cur.fetchall()

def flatten_plans_to_rows(plans):
    plan_rows = []
    slot_rows = []

    for (wid, teacher, grade, class_name, teacher_type, week, plan_json, status,
         submitted_at, approved_at, approved_by) in plans:

        plan_rows.append({
            "id": wid,
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

def build_hours_progress_df(hours_total_rows):
    out = []
    consumed_map = {(gg, ss): cc for (gg, ss, cc) in hours_total_rows}

    for gg in STANDARD_HOURS.keys():
        for ss in get_subjects_for_grade(gg):
            std = STANDARD_HOURS[gg][ss]
            used = float(consumed_map.get((gg, ss), 0.0))
            remain = std - used
            out.append({
                "grade": gg,
                "subject": ss,
                "standard_45": std,
                "consumed_45": round(used, 2),
                "remain_45": round(remain, 2),
            })
    return pd.DataFrame(out)

def to_excel_bytes(dfs: dict):
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df.to_excel(writer, index=False, sheet_name=sheet[:31])
    bio.seek(0)
    return bio.getvalue()


# ======================================================
# 🧰 バックアップ（Excel/CSV）※管理職のみ
#   - 「作成」ボタンで日付付きバックアップを生成
#   - 生成後にダウンロードボタンを表示
#   - 前回バックアップから7日超なら注意表示
# ======================================================

def ensure_backup_log_table():
    cur.execute("""
    CREATE TABLE IF NOT EXISTS backup_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        created_by TEXT,
        filename TEXT
    )
    """)
    conn.commit()

def get_last_backup_date():
    ensure_backup_log_table()
    cur.execute("SELECT created_at FROM backup_log ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None

def log_backup(created_by: str, filename: str):
    ensure_backup_log_table()
    cur.execute(
        "INSERT INTO backup_log (created_at, created_by, filename) VALUES (DATETIME('now'), ?, ?)",
        (created_by, filename)
    )
    conn.commit()

def fetch_all_weekly_plans():
    cur.execute("""
        SELECT id, teacher, grade, class, teacher_type, week, plan_json, status,
               submitted_at, approved_at, approved_by
        FROM weekly_plans
        ORDER BY id DESC
    """)
    return cur.fetchall()

def fetch_hours_total():
    cur.execute("""
        SELECT grade, subject, consumed
        FROM hours_total
        ORDER BY grade, subject
    """)
    return cur.fetchall()

def flatten_plans_to_rows(plans):
    plan_rows = []
    slot_rows = []

    for (wid, teacher, grade, class_name, teacher_type, week, plan_json, status,
         submitted_at, approved_at, approved_by) in plans:

        plan_rows.append({
            "id": wid,
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

def build_hours_progress_df(hours_total_rows):
    out = []
    consumed_map = {(gg, ss): cc for (gg, ss, cc) in hours_total_rows}

    for gg in STANDARD_HOURS.keys():
        for ss in get_subjects_for_grade(gg):
            std = STANDARD_HOURS[gg][ss]
            used = float(consumed_map.get((gg, ss), 0.0))
            remain = std - used
            out.append({
                "grade": gg,
                "subject": ss,
                "standard_45": std,
                "consumed_45": round(used, 2),
                "remain_45": round(remain, 2),
            })
    return pd.DataFrame(out)

def to_excel_bytes(dfs: dict):
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df.to_excel(writer, index=False, sheet_name=sheet[:31])
    bio.seek(0)
    return bio.getvalue()


# ★ここから表示：管理職のみ
if role == "管理職":
    st.markdown("---")
    st.header("🧰 バックアップ（Excel/CSV ダウンロード）")

    last_backup = get_last_backup_date()
    if last_backup:
        st.write(f"前回バックアップ：{last_backup}")
    else:
        st.warning("まだバックアップが作成されていません。初回は必ず作成してください。")

    st.caption("操作：①『バックアップを作成』→ ②表示されたダウンロードボタンから保存（Excel/CSV）")

    # 7日以上バックアップが無い場合の注意（見落とし防止）
    cur.execute("""
        SELECT julianday('now') - julianday(created_at)
        FROM backup_log
        ORDER BY id DESC LIMIT 1
    """)
    row = cur.fetchone()
    if row and row[0] is not None and row[0] >= 7:
        st.warning("前回バックアップから7日以上経過しています。バックアップを作成してください。")

    # 生成データはセッションに保持（生成→ダウンロードの順を安定化）
    if "backup_excel_bytes" not in st.session_state:
        st.session_state["backup_excel_bytes"] = None
    if "backup_csv_pack" not in st.session_state:
        st.session_state["backup_csv_pack"] = None
    if "backup_filename" not in st.session_state:
        st.session_state["backup_filename"] = None

    created_by = "管理職"

    if st.button("🟦 バックアップを作成（今日の日付で生成）"):
        plans = fetch_all_weekly_plans()
        df_plans, df_slots = flatten_plans_to_rows(plans)

        hours_rows = fetch_hours_total()
        df_hours = build_hours_progress_df(hours_rows)

        today_str = date.today().strftime("%Y%m%d")
        filename = f"weekly_plan_backup_{today_str}.xlsx"

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

        log_backup(created_by=created_by, filename=filename)
        st.success("バックアップを作成しました。下のボタンからダウンロードしてください。")

    # 作成済みならダウンロードボタンを出す
    if st.session_state["backup_excel_bytes"]:
        today_str = date.today().strftime("%Y%m%d")
        st.download_button(
            label="⬇️ バックアップ一括（Excel）をダウンロード",
            data=st.session_state["backup_excel_bytes"],
            file_name=st.session_state["backup_filename"] or f"weekly_plan_backup_{today_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        csv_pack = st.session_state["backup_csv_pack"] or {}
        st.download_button(
            label="⬇️ 週案一覧（CSV）",
            data=csv_pack.get("weekly_plans", b""),
            file_name=f"weekly_plans_{today_str}.csv",
            mime="text/csv",
        )
        st.download_button(
            label="⬇️ 時間割（コマ明細）（CSV）",
            data=csv_pack.get("weekly_slots", b""),
            file_name=f"weekly_slots_{today_str}.csv",
            mime="text/csv",
        )
        st.download_button(
            label="⬇️ 年間累積（進捗）（CSV）",
            data=csv_pack.get("hours_progress", b""),
            file_name=f"hours_progress_{today_str}.csv",
            mime="text/csv",
        )
