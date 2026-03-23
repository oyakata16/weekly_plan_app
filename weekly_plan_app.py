# weekly_plan_app.py
# 東小松川小学校 週案管理システム 安定版 V6.5（認証完全修正版）

import io
import json
import re
import sqlite3
import hashlib
from datetime import date
from typing import Optional, List
from pathlib import Path

import pandas as pd
import streamlit as st

# =========================
# DBパス修正（超重要）
# =========================
APP_DIR = Path(__file__).resolve().parent
DB_PATH = str(APP_DIR / "weekly_plans.db")

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

# =========================
# パスワードハッシュ
# =========================
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# =========================
# usersテーブル
# =========================
def ensure_users_table():
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            password_hash TEXT,
            role TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()

ensure_users_table()

# =========================
# ユーザー登録
# =========================
def register_user(user_id, display_name, password, role):
    try:
        cur.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, DATETIME('now'))",
            (user_id.strip(), display_name.strip(), hash_password(password), role)
        )
        conn.commit()
        return True
    except:
        return False

# =========================
# ユーザー数確認
# =========================
def count_users():
    cur.execute("SELECT COUNT(*) FROM users")
    return cur.fetchone()[0]

# =========================
# 認証（修正版）
# =========================
def authenticate_user(user_id: str, raw_password: str):
    uid = str(user_id).strip()
    pw = str(raw_password)

    cur.execute(
        "SELECT user_id, display_name, password_hash, role FROM users WHERE TRIM(user_id)=?",
        (uid,)
    )
    row = cur.fetchone()

    if not row:
        return None

    _uid, _display_name, _pw_hash, _role = row
    if hash_password(pw) == _pw_hash:
        return {
            "user_id": _uid,
            "display_name": _display_name or _uid,
            "role": _role
        }
    return None

# =========================
# パスワード変更
# =========================
def change_password(user_id, new_pw):
    cur.execute(
        "UPDATE users SET password_hash=? WHERE user_id=?",
        (hash_password(new_pw), user_id)
    )
    conn.commit()

# =========================
# セッション初期化
# =========================
if "login_user" not in st.session_state:
    st.session_state["login_user"] = None

# =========================
# ログイン画面
# =========================
def render_login():
    st.title("週案管理システム")
    st.subheader("ログイン / 新規登録")

    user_count = count_users()
    if user_count == 0:
        st.warning("ユーザー未登録です。先に新規登録してください")
    else:
        st.caption(f"登録済ユーザー: {user_count} 名")

    tab1, tab2 = st.tabs(["ログイン", "新規登録"])

    # ログイン
    with tab1:
        login_uid = st.text_input("ID", key="login_uid")
        login_pw = st.text_input("パスワード", type="password", key="login_pw")

        if st.button("ログイン", key="login_btn"):
            user = authenticate_user(login_uid, login_pw)
            if user:
                st.session_state["login_user"] = user
                st.success("ログイン成功")
                st.rerun()
            else:
                st.error("IDまたはパスワードが違います")

    # 新規登録
    with tab2:
        signup_uid = st.text_input("ID（英数字）", key="signup_uid")
        signup_name = st.text_input("氏名", key="signup_name")
        signup_pw = st.text_input("パスワード", type="password", key="signup_pw")
        signup_role = st.selectbox("権限", ["教員", "管理職"], key="signup_role")

        if st.button("登録", key="signup_btn"):
            if not signup_uid.strip():
                st.error("IDを入力してください")
            elif not signup_name.strip():
                st.error("氏名を入力してください")
            elif not signup_pw:
                st.error("パスワードを入力してください")
            else:
                if register_user(signup_uid, signup_name, signup_pw, signup_role):
                    st.success("登録成功")
                else:
                    st.error("登録失敗（ID重複の可能性）")
# =========================
# 未ログインなら停止
# =========================
if st.session_state["login_user"] is None:
    render_login()
    st.stop()

user = st.session_state["login_user"]

# =========================
# パスワード変更UI
# =========================
with st.sidebar:
    st.write(f"ログイン中：{user['display_name']}（{user['role']}）")

    with st.expander("🔑 パスワード変更"):
        new_pw = st.text_input("新しいパスワード", type="password")
        if st.button("変更"):
            change_password(user["user_id"], new_pw)
            st.success("変更しました")

    if st.button("ログアウト"):
        st.session_state["login_user"] = None
        st.rerun()

# =========================
# 以下既存機能（簡略版）
# =========================

st.title("週案作成")

teacher_name = user["display_name"]

week = st.date_input("週")

st.write("ここに時間割UIが入る")

# =========================
# 管理職画面（氏名優先表示）
# =========================
if user["role"] == "管理職":
    st.header("管理職ダッシュボード")

    cur.execute("SELECT user_id, display_name, role FROM users")
    rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["ID", "氏名", "権限"])

    # ←ここが修正ポイント
    df["表示名"] = df["氏名"].fillna("") + "（" + df["ID"] + "）"

    st.dataframe(df[["表示名", "権限"]])
