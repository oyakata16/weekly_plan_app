# weekly_plan_app.py
# 東小松川小学校 週案管理システム V7.1 完全版
# ------------------------------------------------
# 追加・修正
# - 教員 / 管理職のログイン
# - 新規登録（管理職は登録コード必須）
# - パスワード変更
# - 教員名はログイン名を自動使用
# - 下書き保存 / 自動保存 / 復元 / 前回の続き / 前週コピー
# - 週案提出 / 管理職承認 / 差戻
# - 年間時数集計 / 警告 / 最適化提案
# - 探究活動ログ
# - バックアップ / 区教委提出CSV
# - 管理職画面では氏名優先表示
# - DBパス固定化
# - DuplicateElementId 対策
# - session_state 書き換え順の整理
# ------------------------------------------------

import io
import json
import re
import hashlib
from datetime import date
from pathlib import Path
from typing import Optional, List

import pandas as pd
import streamlit as st

# =========================
# 基本設定
# =========================
APP_DIR = Path(__file__).resolve().parent
DB_PATH = "Supabase"

DEFAULT_MANAGER_SIGNUP_CODE = "school-admin-2026"
MANAGER_SIGNUP_CODE = st.secrets.get("MANAGER_SIGNUP_CODE", DEFAULT_MANAGER_SIGNUP_CODE)

DEFAULT_SCHOOL_YEAR = "令和8年度"
DEFAULT_WEEKS_PER_YEAR = 35

st.set_page_config(page_title="週案管理システム", layout="wide")

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
        border: 1px solid #999 !important;
        border-radius: 6px !important;
        padding: 8px 6px !important;
        margin: 2px 0 6px 0 !important;
        background: #e0e0e0 !important;
        font-weight: 700;
        text-align: center;
        color: #000000 !important;
    }
    .tt-headcell {
        border: 1px solid #999 !important;
        border-radius: 6px !important;
        padding: 8px 6px !important;
        margin: 2px 0 6px 0 !important;
        background: #d6d6d6 !important;
        font-weight: 800;
        text-align: center;
        color: #000000 !important;
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

    .status-card {
        padding: 12px 14px;
        border-radius: 10px;
        margin-bottom: 8px;
        font-weight: 700;
        border-left: 6px solid transparent;
    }
    .status-missing { background-color: #ffe5e5; border-left-color: #ff4d4d; }
    .status-draft { background-color: #fff7cc; border-left-color: #ffcc00; }
    .status-done { background-color: #e6ffe6; border-left-color: #33cc33; }
    .matrix-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
    }
    .matrix-table th, .matrix-table td {
        border: 1px solid #d0d7de;
        padding: 6px 8px;
        text-align: center;
        vertical-align: middle;
    }
    .matrix-table th:first-child, .matrix-table td:first-child {
        text-align: left;
        white-space: nowrap;
    }
    .matrix-cell {
        text-align: center;
        font-weight: 700;
        border-radius: 6px;
        padding: 4px 6px;
        display: inline-block;
        min-width: 28px;
    }
    .miss { background-color:#ffcccc; color:#8b0000; }
    .draft { background-color:#fff0b3; color:#8a6d00; }
    .done { background-color:#ccffcc; color:#006400; }
    .empty { background-color:#f4f4f4; color:#666666; }
    .tag-chip {
        display:inline-block; padding:4px 10px; margin:2px 4px 2px 0;
        border-radius:999px; background:#eef4ff; border:1px solid #b8cdf5;
        font-size:13px; font-weight:600;
    }
    @media print {
        /* ======= 印刷レイアウト（A4縦1枚フィット） ======= */
        @page {
            size: A4 portrait;
            margin: 8mm 8mm 8mm 8mm;
        }
        /* 不要なUI要素を非表示 */
        header, footer, .stSidebar,
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        button, .stButton,
        [data-testid="stSidebar"],
        section[data-testid="stSidebar"],
        .stCheckbox, .stSelectbox, .stDateInput,
        .stTextInput, .stTextArea, .stRadio,
        hr, .stMarkdown hr,
        [data-testid="stExpander"] summary,
        .stAlert, .stInfo, .stWarning, .stSuccess,
        .no-print { display: none !important; }

        /* メインコンテナ */
        .main .block-container {
            padding: 0 !important;
            margin: 0 !important;
            max-width: 100% !important;
        }
        html, body { font-size: 9px !important; }

        /* 印刷対象の週案テーブル */
        .print-timetable {
            display: block !important;
            page-break-inside: avoid;
        }
        table.print-weekly-table {
            width: 100% !important;
            font-size: 8px !important;
            border-collapse: collapse !important;
            table-layout: fixed !important;
            page-break-inside: avoid !important;
        }
        table.print-weekly-table th,
        table.print-weekly-table td {
            border: 1px solid #000 !important;
            padding: 2px 3px !important;
            vertical-align: top !important;
            word-break: break-word !important;
            line-height: 1.3 !important;
        }
        table.print-weekly-table th {
            background: #e0e0e0 !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            font-weight: bold !important;
            text-align: center !important;
        }
        .print-header { font-size: 10px !important; margin-bottom: 3mm !important; }
        .print-cell-subject { font-weight: bold; }
        .print-cell-content { font-size: 7.5px; color: #333; }
        .print-cell-event { background: #fff4cc !important; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }

        /* dataframe（streamlit標準テーブル）フォールバック */
        .stDataFrame table {
            width: 100% !important;
            font-size: 8px !important;
            border-collapse: collapse !important;
        }
        .stDataFrame th, .stDataFrame td {
            border: 1px solid #000 !important;
            padding: 2px 3px !important;
            white-space: pre-wrap !important;
            word-break: break-word !important;
        }
        /* 印刷ヘッダー情報だけ表示 */
        .print-only { display: block !important; }
        /* ページ全体を1枚に収める */
        * { overflow: visible !important; }
    }
    /* 通常表示時は印刷専用要素を隠す */
    .print-only { display: none; }
    .print-weekly-table { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

COLUMN_WIDTHS = [0.7] + [1.6] * 6
DAYS = ["月", "火", "水", "木", "金", "土"]
PERIODS = ["1校時", "2校時", "3校時", "4校時", "5校時", "学校裁量", "6校時"]


import requests
from urllib.parse import urljoin, quote

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", st.secrets.get("SUPABASE_KEY", ""))

class SupabaseCompatConnection:
    def commit(self):
        return None

class SupabaseCompatCursor:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/") + "/"
        self.key = key
        self._results = []
        self._single = None

    def _headers(self, prefer: str | None = None):
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def _table_url(self, table: str) -> str:
        return urljoin(self.url, f"rest/v1/{table}")

    def _request(self, method: str, path: str, *, params=None, json_body=None, headers=None):
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY を Streamlit secrets に設定してください。")
        h = self._headers()
        if headers:
            h.update(headers)
        resp = requests.request(method, urljoin(self.url, path), params=params, json=json_body, headers=h, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase error {resp.status_code}: {resp.text[:500]}")
        ct = resp.headers.get("content-type", "")
        if "application/json" in ct:
            return resp.json()
        return resp.text

    def _select(self, table: str, select: str = "*", filters=None, order=None, limit=None):
        params = {"select": select}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        return self._request("GET", f"rest/v1/{table}", params=params)

    def _insert(self, table: str, rows, returning="representation"):
        prefer = f"return={returning}"
        return self._request("POST", f"rest/v1/{table}", json_body=rows, headers={"Prefer": prefer})

    def _update(self, table: str, values: dict, filters=None, returning="representation"):
        prefer = f"return={returning}"
        return self._request("PATCH", f"rest/v1/{table}", params=filters or {}, json_body=values, headers={"Prefer": prefer})

    def execute(self, query: str, params=()):
        q = " ".join(query.strip().split())
        self._results = []
        self._single = None

        # No-op DDL / migration SQL
        if q.startswith("CREATE TABLE IF NOT EXISTS") or q.startswith("ALTER TABLE"):
            return self
        if q.startswith("UPDATE weekly_plans SET school_year=") or q.startswith("UPDATE hours_total SET school_year=") or q.startswith("UPDATE weekly_plans SET user_id=teacher") or q.startswith("UPDATE weekly_plans SET teacher_name=teacher") or q.startswith("UPDATE auto_save_sessions SET user_id=teacher") or q.startswith("UPDATE auto_save_sessions SET teacher_name=teacher"):
            return self

        # users
        if q == "SELECT user_id, display_name, password_hash, role, created_at FROM users WHERE TRIM(user_id)=?":
            uid = str(params[0]).strip()
            rows = self._select("users", select="user_id,display_name,password_hash,role,created_at", filters={"user_id": f"eq.{uid}"}, limit=1)
            self._single = tuple(rows[0].values()) if rows else None
            return self
        if q == "SELECT COUNT(*) FROM users":
            rows = self._request("GET", "rest/v1/users", params={"select": "user_id"})
            self._single = (len(rows),)
            return self
        if q.startswith("INSERT INTO users (user_id, display_name, password_hash, role, created_at) VALUES"):
            user_id, display_name, password_hash, role = params
            self._insert("users", [{"user_id": user_id, "display_name": display_name, "password_hash": password_hash, "role": role}], returning="minimal")
            return self
        if q == "UPDATE users SET password_hash=? WHERE user_id=?":
            password_hash, uid = params
            self._update("users", {"password_hash": password_hash}, {"user_id": f"eq.{uid}"}, returning="minimal")
            return self
        if q == "SELECT user_id, display_name FROM users WHERE role='教員' ORDER BY display_name":
            rows = self._select("users", select="user_id,display_name", filters={"role": "eq.教員"}, order="display_name.asc")
            self._results = [(r.get("user_id"), r.get("display_name")) for r in rows]
            return self

        # app_settings
        if q == "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)":
            return self
        if q == "SELECT value FROM app_settings WHERE key=?":
            key = params[0]
            rows = self._select("app_settings", select="value", filters={"key": f"eq.{key}"}, limit=1)
            self._single = (rows[0]["value"],) if rows else None
            return self
        if q.startswith("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value"):
            key, value = params
            existing = self._select("app_settings", select="key", filters={"key": f"eq.{key}"}, limit=1)
            if existing:
                self._update("app_settings", {"value": value}, {"key": f"eq.{key}"}, returning="minimal")
            else:
                self._insert("app_settings", [{"key": key, "value": value}], returning="minimal")
            return self

        # weekly_plans
        if q.startswith("SELECT id FROM weekly_plans WHERE school_year=? AND TRIM(COALESCE(user_id,'')) = ? AND week=? AND status='下書き'"):
            school_year, user_id, week = params
            rows = self._select("weekly_plans", select="id", filters={"school_year": f"eq.{school_year}", "user_id": f"eq.{user_id}", "week": f"eq.{week}", "status": "eq.下書き"}, order="id.desc", limit=1)
            self._single = (rows[0]["id"],) if rows else None
            return self
        if q.startswith("UPDATE weekly_plans SET user_id=?, teacher_name=?, teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, submitted_at=DATETIME('now') WHERE id=?"):
            user_id, teacher_name, teacher, grade, klass, teacher_type, plan_json, row_id = params
            self._update("weekly_plans", {"user_id": user_id, "teacher_name": teacher_name, "teacher": teacher, "grade": grade, "class": klass, "teacher_type": teacher_type, "plan_json": plan_json, "submitted_at": "now"}, {"id": f"eq.{row_id}"}, returning="minimal")
            return self
        if q.startswith("INSERT INTO weekly_plans (school_year, user_id, teacher_name, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at) VALUES"):
            school_year, user_id, teacher_name, teacher, grade, klass, teacher_type, week, plan_json = params
            status = "提出" if "'提出'" in q else "下書き"
            self._insert("weekly_plans", [{"school_year": school_year, "user_id": user_id, "teacher_name": teacher_name, "teacher": teacher, "grade": grade, "class": klass, "teacher_type": teacher_type, "week": week, "plan_json": plan_json, "status": status, "submitted_at": "now"}], returning="minimal")
            return self
        if q.startswith("SELECT id, week, grade, class, teacher_type, plan_json, submitted_at FROM weekly_plans WHERE school_year=? AND TRIM(COALESCE(user_id,'')) = ? AND status='下書き'"):
            school_year, user_id = params
            rows = self._select("weekly_plans", select="id,week,grade,class,teacher_type,plan_json,submitted_at", filters={"school_year": f"eq.{school_year}", "user_id": f"eq.{user_id}", "status": "eq.下書き"}, order="week.desc,id.desc")
            self._results = [(r.get("id"), r.get("week"), r.get("grade"), r.get("class"), r.get("teacher_type"), r.get("plan_json"), r.get("submitted_at")) for r in rows]
            return self
        if q == "SELECT id, school_year, user_id, teacher_name, grade, class, teacher_type, week, plan_json, status FROM weekly_plans WHERE id=?":
            row_id = params[0]
            rows = self._select("weekly_plans", select="id,school_year,user_id,teacher_name,grade,class,teacher_type,week,plan_json,status", filters={"id": f"eq.{row_id}"}, limit=1)
            self._single = tuple(rows[0].get(k) for k in ["id","school_year","user_id","teacher_name","grade","class","teacher_type","week","plan_json","status"]) if rows else None
            return self
        if q.startswith("SELECT plan_json, week, status FROM weekly_plans WHERE school_year=? AND TRIM(COALESCE(user_id,'')) = ? AND week < ?"):
            school_year, user_id, week = params
            rows = self._select("weekly_plans", select="plan_json,week,status", filters={"school_year": f"eq.{school_year}", "user_id": f"eq.{user_id}", "week": f"lt.{week}", "status": "in.(提出,承認,差戻,下書き)"}, order="week.desc,id.desc", limit=1)
            self._single = (rows[0].get("plan_json"), rows[0].get("week"), rows[0].get("status")) if rows else None
            return self
        if q.startswith("UPDATE weekly_plans SET user_id=?, teacher_name=?, teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, status='提出', submitted_at=DATETIME('now') WHERE id=?"):
            user_id, teacher_name, teacher, grade, klass, teacher_type, plan_json, row_id = params
            self._update("weekly_plans", {"user_id": user_id, "teacher_name": teacher_name, "teacher": teacher, "grade": grade, "class": klass, "teacher_type": teacher_type, "plan_json": plan_json, "status": "提出", "submitted_at": "now"}, {"id": f"eq.{row_id}"}, returning="minimal")
            return self
        if q == "SELECT COUNT(DISTINCT week) FROM weekly_plans WHERE school_year=? AND grade=? AND status='承認'":
            school_year, grade = params
            rows = self._select("weekly_plans", select="week", filters={"school_year": f"eq.{school_year}", "grade": f"eq.{grade}", "status": "eq.承認"})
            self._single = (len({r.get("week") for r in rows if r.get("week") is not None}),)
            return self
        if q == "SELECT DISTINCT school_year FROM weekly_plans":
            rows = self._select("weekly_plans", select="school_year")
            vals = []
            seen = set()
            for r in rows:
                v = r.get("school_year")
                if v not in seen:
                    vals.append((v,))
                    seen.add(v)
            self._results = vals
            return self
        if q == "SELECT id, school_year, user_id, teacher_name, grade, class, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by FROM weekly_plans WHERE school_year=? ORDER BY id DESC":
            school_year = params[0]
            rows = self._select("weekly_plans", select="id,school_year,user_id,teacher_name,grade,class,teacher_type,week,plan_json,status,submitted_at,approved_at,approved_by", filters={"school_year": f"eq.{school_year}"}, order="id.desc")
            cols = ["id","school_year","user_id","teacher_name","grade","class","teacher_type","week","plan_json","status","submitted_at","approved_at","approved_by"]
            self._results = [tuple(r.get(c) for c in cols) for r in rows]
            return self
        if q == "UPDATE weekly_plans SET status='承認', approved_at=DATETIME('now'), approved_by=? WHERE id=?":
            approved_by, row_id = params
            self._update("weekly_plans", {"status": "承認", "approved_at": "now", "approved_by": approved_by}, {"id": f"eq.{row_id}"}, returning="minimal")
            return self
        if q == "UPDATE weekly_plans SET status='差戻' WHERE id=?":
            row_id = params[0]
            self._update("weekly_plans", {"status": "差戻"}, {"id": f"eq.{row_id}"}, returning="minimal")
            return self

        # hours_total
        if q == "SELECT consumed FROM hours_total WHERE school_year=? AND grade=? AND subject=?":
            school_year, grade, subject = params
            rows = self._select("hours_total", select="consumed", filters={"school_year": f"eq.{school_year}", "grade": f"eq.{grade}", "subject": f"eq.{subject}"}, limit=1)
            self._single = (rows[0].get("consumed"),) if rows else None
            return self
        if q == "UPDATE hours_total SET consumed=? WHERE school_year=? AND grade=? AND subject=?":
            consumed, school_year, grade, subject = params
            self._update("hours_total", {"consumed": consumed}, {"school_year": f"eq.{school_year}", "grade": f"eq.{grade}", "subject": f"eq.{subject}"}, returning="minimal")
            return self
        if q == "INSERT INTO hours_total (school_year, grade, subject, consumed) VALUES (?, ?, ?, ?)":
            school_year, grade, subject, consumed = params
            self._insert("hours_total", [{"school_year": school_year, "grade": grade, "subject": subject, "consumed": consumed}], returning="minimal")
            return self
        if q == "SELECT 1 FROM year_init WHERE school_year=? LIMIT 1":
            school_year = params[0]
            rows = self._select("year_init", select="school_year", filters={"school_year": f"eq.{school_year}"}, limit=1)
            self._single = (1,) if rows else None
            return self
        if q == "INSERT OR IGNORE INTO hours_total (school_year, grade, subject, consumed) VALUES (?, ?, ?, 0.0)":
            school_year, grade, subject = params
            existing = self._select("hours_total", select="school_year", filters={"school_year": f"eq.{school_year}", "grade": f"eq.{grade}", "subject": f"eq.{subject}"}, limit=1)
            if not existing:
                self._insert("hours_total", [{"school_year": school_year, "grade": grade, "subject": subject, "consumed": 0.0}], returning="minimal")
            return self
        if q == "INSERT OR REPLACE INTO year_init (school_year, initialized_at, initialized_by) VALUES (?, DATETIME('now'), ?)":
            school_year, initialized_by = params
            existing = self._select("year_init", select="school_year", filters={"school_year": f"eq.{school_year}"}, limit=1)
            if existing:
                self._update("year_init", {"initialized_at": "now", "initialized_by": initialized_by}, {"school_year": f"eq.{school_year}"}, returning="minimal")
            else:
                self._insert("year_init", [{"school_year": school_year, "initialized_at": "now", "initialized_by": initialized_by}], returning="minimal")
            return self
        if q == "SELECT school_year, grade, subject, consumed FROM hours_total WHERE school_year=?":
            school_year = params[0]
            rows = self._select("hours_total", select="school_year,grade,subject,consumed", filters={"school_year": f"eq.{school_year}"})
            self._results = [(r.get("school_year"), r.get("grade"), r.get("subject"), r.get("consumed")) for r in rows]
            return self
        if q == "SELECT DISTINCT school_year FROM hours_total":
            rows = self._select("hours_total", select="school_year")
            vals=[]; seen=set()
            for r in rows:
                v = r.get("school_year")
                if v not in seen:
                    vals.append((v,)); seen.add(v)
            self._results = vals
            return self

        # auto_save_sessions
        if q.startswith("SELECT id FROM auto_save_sessions WHERE school_year=? AND TRIM(COALESCE(user_id,'')) = ? AND week=? ORDER BY id DESC LIMIT 1"):
            school_year, user_id, week = params
            rows = self._select("auto_save_sessions", select="id", filters={"school_year": f"eq.{school_year}", "user_id": f"eq.{user_id}", "week": f"eq.{week}"}, order="id.desc", limit=1)
            self._single = (rows[0].get("id"),) if rows else None
            return self
        if q.startswith("UPDATE auto_save_sessions SET user_id=?, teacher_name=?, teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, meta_json=?, saved_at=DATETIME('now') WHERE id=?"):
            user_id, teacher_name, teacher, grade, klass, teacher_type, plan_json, meta_json, row_id = params
            self._update("auto_save_sessions", {"user_id": user_id, "teacher_name": teacher_name, "teacher": teacher, "grade": grade, "class": klass, "teacher_type": teacher_type, "plan_json": plan_json, "meta_json": meta_json, "saved_at": "now"}, {"id": f"eq.{row_id}"}, returning="minimal")
            return self
        if q.startswith("INSERT INTO auto_save_sessions (school_year, user_id, teacher_name, teacher, grade, class, teacher_type, week, plan_json, meta_json, saved_at) VALUES"):
            school_year, user_id, teacher_name, teacher, grade, klass, teacher_type, week, plan_json, meta_json = params
            self._insert("auto_save_sessions", [{"school_year": school_year, "user_id": user_id, "teacher_name": teacher_name, "teacher": teacher, "grade": grade, "class": klass, "teacher_type": teacher_type, "week": week, "plan_json": plan_json, "meta_json": meta_json, "saved_at": "now"}], returning="minimal")
            return self
        if q.startswith("SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE school_year=? AND TRIM(COALESCE(user_id,'')) = ? ORDER BY saved_at DESC, id DESC"):
            school_year, user_id = params
            rows = self._select("auto_save_sessions", select="id,week,grade,class,teacher_type,saved_at,plan_json,meta_json", filters={"school_year": f"eq.{school_year}", "user_id": f"eq.{user_id}"}, order="saved_at.desc,id.desc")
            self._results = [(r.get("id"), r.get("week"), r.get("grade"), r.get("class"), r.get("teacher_type"), r.get("saved_at"), r.get("plan_json"), r.get("meta_json")) for r in rows]
            return self
        if q.startswith("SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE school_year=? AND TRIM(COALESCE(user_id,'')) = ? ORDER BY saved_at DESC, id DESC LIMIT 1"):
            school_year, user_id = params
            rows = self._select("auto_save_sessions", select="id,week,grade,class,teacher_type,saved_at,plan_json,meta_json", filters={"school_year": f"eq.{school_year}", "user_id": f"eq.{user_id}"}, order="saved_at.desc,id.desc", limit=1)
            self._single = (rows[0].get("id"), rows[0].get("week"), rows[0].get("grade"), rows[0].get("class"), rows[0].get("teacher_type"), rows[0].get("saved_at"), rows[0].get("plan_json"), rows[0].get("meta_json")) if rows else None
            return self
        if q == "SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE id=?":
            row_id = params[0]
            rows = self._select("auto_save_sessions", select="id,week,grade,class,teacher_type,saved_at,plan_json,meta_json", filters={"id": f"eq.{row_id}"}, limit=1)
            self._single = (rows[0].get("id"), rows[0].get("week"), rows[0].get("grade"), rows[0].get("class"), rows[0].get("teacher_type"), rows[0].get("saved_at"), rows[0].get("plan_json"), rows[0].get("meta_json")) if rows else None
            return self
        if q.startswith("SELECT saved_at FROM auto_save_sessions WHERE school_year=? AND TRIM(COALESCE(user_id,'')) = ? AND week=? ORDER BY id DESC LIMIT 1"):
            school_year, user_id, week = params
            rows = self._select("auto_save_sessions", select="saved_at", filters={"school_year": f"eq.{school_year}", "user_id": f"eq.{user_id}", "week": f"eq.{week}"}, order="id.desc", limit=1)
            self._single = (rows[0].get("saved_at"),) if rows else None
            return self

        # inquiry logs
        if q.startswith("INSERT INTO inquiry_logs (school_year, week, grade, class, teacher, teacher_name, theme, goals, activities, evidence, reflection, created_at) VALUES"):
            school_year, week, grade, klass, teacher, teacher_name, theme, goals, activities, evidence, reflection = params
            self._insert("inquiry_logs", [{"school_year": school_year, "week": week, "grade": grade, "class": klass, "teacher": teacher, "teacher_name": teacher_name, "theme": theme, "goals": goals, "activities": activities, "evidence": evidence, "reflection": reflection, "created_at": "now"}], returning="minimal")
            return self
        if q.startswith("SELECT id, school_year, week, grade, class, teacher, teacher_name, theme, goals, activities, evidence, reflection, created_at FROM inquiry_logs WHERE school_year=?"):
            school_year = params[0]
            filters = {"school_year": f"eq.{school_year}"}
            idx=1
            if " AND grade=?" in q:
                filters["grade"] = f"eq.{params[idx]}"; idx+=1
            if " AND class=?" in q:
                filters["class"] = f"eq.{params[idx]}"; idx+=1
            if " AND TRIM(COALESCE(teacher,''))=?" in q:
                filters["teacher"] = f"eq.{params[idx]}"; idx+=1
            rows = self._select("inquiry_logs", select="id,school_year,week,grade,class,teacher,teacher_name,theme,goals,activities,evidence,reflection,created_at", filters=filters, order="created_at.desc,id.desc")
            cols = ["id","school_year","week","grade","class","teacher","teacher_name","theme","goals","activities","evidence","reflection","created_at"]
            self._results = [tuple(r.get(c) for c in cols) for r in rows]
            return self

        # backup log
        if q == "SELECT created_at FROM backup_log WHERE school_year=? ORDER BY id DESC LIMIT 1":
            school_year = params[0]
            rows = self._select("backup_log", select="created_at", filters={"school_year": f"eq.{school_year}"}, order="id.desc", limit=1)
            self._single = (rows[0].get("created_at"),) if rows else None
            return self
        if q == "INSERT INTO backup_log (school_year, created_at, created_by, filename) VALUES (?, DATETIME('now'), ?, ?)":
            school_year, created_by, filename = params
            self._insert("backup_log", [{"school_year": school_year, "created_at": "now", "created_by": created_by, "filename": filename}], returning="minimal")
            return self

        raise NotImplementedError(f"Unsupported SQL in compatibility layer: {q}")

    def fetchone(self):
        return self._single

    def fetchall(self):
        return self._results

conn = SupabaseCompatConnection()
cur = SupabaseCompatCursor(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# =========================
# 認証
# =========================
def hash_password(raw_password: str) -> str:
    return hashlib.sha256(str(raw_password).encode("utf-8")).hexdigest()


def ensure_users_table():
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            password_hash TEXT,
            role TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()


def get_user(user_id: str):
    cur.execute(
        "SELECT user_id, display_name, password_hash, role, created_at FROM users WHERE TRIM(user_id)=?",
        (str(user_id).strip(),),
    )
    return cur.fetchone()


def count_users() -> int:
    cur.execute("SELECT COUNT(*) FROM users")
    row = cur.fetchone()
    return int(row[0] or 0)


def create_user(user_id: str, display_name: str, raw_password: str, role: str):
    cur.execute(
        "INSERT INTO users (user_id, display_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, DATETIME('now'))",
        (
            str(user_id).strip(),
            str(display_name).strip(),
            hash_password(raw_password),
            str(role).strip(),
        ),
    )
    conn.commit()


def authenticate_user(user_id: str, raw_password: str):
    uid = str(user_id).strip()
    pw = str(raw_password)
    row = get_user(uid)
    if not row:
        return None
    _uid, _display_name, _pw_hash, _role, _created_at = row
    if str(_pw_hash).strip() == hash_password(pw):
        return {"user_id": _uid, "display_name": _display_name or _uid, "role": _role}
    return None


def update_user_password(user_id: str, new_raw_password: str):
    cur.execute(
        "UPDATE users SET password_hash=? WHERE user_id=?",
        (hash_password(new_raw_password), str(user_id).strip()),
    )
    conn.commit()


def get_user_display_name_by_id(user_id: str) -> str:
    row = get_user(user_id)
    if row and row[1]:
        return str(row[1]).strip()
    return str(user_id).strip()


def teacher_label(user_id: str, teacher_name: str = "") -> str:
    teacher_name = str(teacher_name or "").strip()
    user_id = str(user_id or "").strip()
    if teacher_name and user_id:
        return f"{teacher_name}（{user_id}）"
    if teacher_name:
        return teacher_name
    if user_id:
        resolved = get_user_display_name_by_id(user_id)
        return f"{resolved}（{user_id}）" if resolved != user_id else user_id
    return "（不明）"


def init_auth_session():
    st.session_state.setdefault("logged_in", False)
    st.session_state.setdefault("auth_user_id", "")
    st.session_state.setdefault("auth_display_name", "")
    st.session_state.setdefault("auth_role", "")


def logout():
    keys_to_clear = [
        "logged_in", "auth_user_id", "auth_display_name", "auth_role",
        "restore_notice", "restore_plan", "teacher_type", "base_grade",
        "class_name", "week_date", "class_name_input", "week_date_input",
        "classes_input"
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()


def render_login_screen():
    st.title("小学校 週の指導計画（週案）管理システム")
    st.subheader("ログイン / 新規登録")

    try:
        user_count = count_users()
        if user_count == 0:
            st.warning("現在、このDBには登録済みユーザーがいません。初回は新規登録を行ってください。")
        else:
            st.caption(f"登録済みユーザー数: {user_count} 名")
            st.caption(f"使用DB: {DB_PATH}")
    except Exception as e:
        st.error(f"users テーブル確認でエラーが出ています: {e}")

    tab_login, tab_signup = st.tabs(["ログイン", "新規登録"])

    with tab_login:
        login_user_id = st.text_input("ログインID", key="login_user_id")
        login_pw = st.text_input("パスワード", type="password", key="login_pw")

        if st.button("ログインする", key="login_submit_btn"):
            auth = authenticate_user(login_user_id, login_pw)
            if auth:
                st.session_state["logged_in"] = True
                st.session_state["auth_user_id"] = auth["user_id"]
                st.session_state["auth_display_name"] = auth["display_name"]
                st.session_state["auth_role"] = auth["role"]
                st.success("ログインしました。")
                st.rerun()
            else:
                st.error("ログインIDまたはパスワードが正しくありません。")

    with tab_signup:
        signup_display_name = st.text_input("氏名", key="signup_display_name")
        signup_user_id = st.text_input("新規ログインID", key="signup_user_id")
        signup_pw = st.text_input("新規パスワード", type="password", key="signup_pw")
        signup_pw2 = st.text_input("新規パスワード（確認）", type="password", key="signup_pw2")
        signup_role = st.selectbox("利用区分", ["教員", "管理職"], key="signup_role")
        manager_code = ""
        if signup_role == "管理職":
            manager_code = st.text_input("管理職登録コード", type="password", key="manager_signup_code")

        if st.button("新規登録する", key="signup_submit_btn"):
            uid = str(signup_user_id).strip()
            dname = str(signup_display_name).strip()
            pw1 = str(signup_pw)
            pw2 = str(signup_pw2)

            if not uid:
                st.error("ログインIDを入力してください。")
            elif not dname:
                st.error("氏名を入力してください。")
            elif not pw1:
                st.error("パスワードを入力してください。")
            elif pw1 != pw2:
                st.error("パスワード確認が一致しません。")
            elif get_user(uid):
                st.error("そのログインIDはすでに使われています。")
            elif signup_role == "管理職" and manager_code != MANAGER_SIGNUP_CODE:
                st.error("管理職登録コードが違います。")
            else:
                try:
                    create_user(uid, dname, pw1, signup_role)
                    st.success("新規登録が完了しました。ログインしてください。")
                except Exception as e:
                    st.error(f"登録に失敗しました: {e}")


ensure_users_table()
init_auth_session()

if not st.session_state["logged_in"]:
    render_login_screen()
    st.stop()

# =========================
# 設定・DBテーブル
# =========================
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS weekly_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_year TEXT,
            user_id TEXT,
            teacher_name TEXT,
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
    for col in [
        "school_year", "user_id", "teacher_name", "teacher", "grade", "class",
        "teacher_type", "week", "plan_json", "status", "submitted_at",
        "approved_at", "approved_by"
    ]:
        try:
            cur.execute(f"ALTER TABLE weekly_plans ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def ensure_hours_total_table():
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
    for col in ["school_year", "grade", "subject", "consumed"]:
        try:
            ctype = "REAL" if col == "consumed" else "TEXT"
            cur.execute(f"ALTER TABLE hours_total ADD COLUMN {col} {ctype}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


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


def ensure_inquiry_logs_table():
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS inquiry_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_year TEXT,
            week TEXT,
            grade TEXT,
            class TEXT,
            teacher TEXT,
            teacher_name TEXT,
            theme TEXT,
            goals TEXT,
            activities TEXT,
            evidence TEXT,
            reflection TEXT,
            created_at TEXT
        )
        """
    )
    for col in [
        "school_year", "week", "grade", "class", "teacher", "teacher_name",
        "theme", "goals", "activities", "evidence", "reflection", "created_at"
    ]:
        try:
            cur.execute(f"ALTER TABLE inquiry_logs ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def ensure_autosave_table():
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_save_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_year TEXT,
            user_id TEXT,
            teacher_name TEXT,
            teacher TEXT,
            grade TEXT,
            class TEXT,
            teacher_type TEXT,
            week TEXT,
            plan_json TEXT,
            meta_json TEXT,
            saved_at TEXT
        )
        """
    )
    for col in [
        "school_year", "user_id", "teacher_name", "teacher", "grade", "class",
        "teacher_type", "week", "plan_json", "meta_json", "saved_at"
    ]:
        try:
            cur.execute(f"ALTER TABLE auto_save_sessions ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()


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


ensure_weekly_plans_table()
ensure_hours_total_table()
ensure_year_init_table()
ensure_inquiry_logs_table()
ensure_autosave_table()
ensure_backup_log_table()

try:
    cur.execute("UPDATE weekly_plans SET school_year=? WHERE school_year IS NULL OR school_year=''", (DEFAULT_SCHOOL_YEAR,))
    cur.execute("UPDATE hours_total SET school_year=? WHERE school_year IS NULL OR school_year=''", (DEFAULT_SCHOOL_YEAR,))
    cur.execute("UPDATE weekly_plans SET user_id=teacher WHERE (user_id IS NULL OR user_id='') AND teacher IS NOT NULL AND teacher<>''")
    cur.execute("UPDATE weekly_plans SET teacher_name=teacher WHERE (teacher_name IS NULL OR teacher_name='') AND teacher IS NOT NULL AND teacher<>''")
    cur.execute("UPDATE auto_save_sessions SET user_id=teacher WHERE (user_id IS NULL OR user_id='') AND teacher IS NOT NULL AND teacher<>''")
    cur.execute("UPDATE auto_save_sessions SET teacher_name=teacher WHERE (teacher_name IS NULL OR teacher_name='') AND teacher IS NOT NULL AND teacher<>''")
    conn.commit()
except Exception:
    pass

# =========================
# 教科・分数設定
# =========================
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

# =========================
# 共通関数
# =========================
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
    return {"class": "", "event": {"fraction": 0.0, "content": ""}, "main": {"subject": "（空欄）", "content": ""}}


def build_empty_timetable():
    out = {}
    for day in DAYS:
        out[day] = {}
        for period in PERIODS:
            out[day][period] = empty_cell()
    return out


def normalize_timetable(tt):
    out = build_empty_timetable()
    src = tt if isinstance(tt, dict) else {}
    for day in DAYS:
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
                "event": {"fraction": float(event.get("fraction", 0.0) or 0.0), "content": event.get("content", "") or ""},
                "main": {"subject": (main.get("subject", "") or legacy_subject or "（空欄）"), "content": (main.get("content", "") or legacy_content or "")},
            }
    return out


def apply_timetable_to_widget_state(timetable: dict, teacher_type: str):
    tt = normalize_timetable(timetable)
    for day in DAYS:
        for period in PERIODS:
            cell = tt.get(day, {}).get(period, empty_cell())
            event = cell.get("event") or {}
            main = cell.get("main") or {}

            st.session_state[f"{day}_{period}_eventfrac"] = fraction_value_to_label(float(event.get("fraction", 0.0) or 0.0))
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


def validate_timetable_for_submit(tt: dict, teacher_type: str = "担任"):
    errors = []
    tt = normalize_timetable(tt)
    filled_count = 0

    for day in DAYS:
        for period in PERIODS:
            slot_minutes = PERIOD_MINUTES.get(day, {}).get(period, 0)
            if slot_minutes <= 0:
                continue

            cell = (tt or {}).get(day, {}).get(period, empty_cell())
            event = cell.get("event") or {}
            main = cell.get("main") or {}
            frac = max(0.0, min(1.0, float(event.get("fraction", 0.0) or 0.0)))
            subj = (main.get("subject") or "").strip()
            klass = (cell.get("class") or "").strip()
            event_content = (event.get("content") or "").strip()
            main_content = (main.get("content") or "").strip()

            has_event = frac > 0.0
            has_main = bool(subj and subj != "（空欄）")

            if has_event or has_main or event_content or main_content or klass:
                filled_count += 1

            if teacher_type.startswith("専科"):
                if has_event or has_main or event_content or main_content:
                    if not klass:
                        errors.append(f"{day} {period}: 専科のため学級の選択が必要です。")

            if 0.0 < frac < 1.0:
                e8 = fraction_to_8th(frac)
                r8 = 8 - e8
                if not has_main:
                    errors.append(f"{day} {period}: 学校行事が {e8}/8 のため、残り {r8}/8（{int(round(slot_minutes*(1-frac)))}分）の教科等が必要です。")

            if frac == 0.0 and not has_main:
                if event_content:
                    errors.append(f"{day} {period}: 学校行事の内容だけ入力されています。配分を選択してください。")

            if frac == 1.0 and not event_content:
                errors.append(f"{day} {period}: 学校行事が 8/8 のため、内容を入力してください。")

            if has_main and not main_content:
                errors.append(f"{day} {period}: 教科等「{subj}」の内容を入力してください。")

    if filled_count == 0:
        errors.append("1週間の時間割が未入力です。少なくとも1コマ以上入力してください。")

    seen = set()
    unique_errors = []
    for e in errors:
        if e not in seen:
            unique_errors.append(e) 
            seen.add(e)
    return unique_errors

def has_meaningful_timetable_data(timetable: dict) -> bool:
    tt = normalize_timetable(timetable)

    for day in DAYS:
        for period in PERIODS:
            slot_minutes = PERIOD_MINUTES.get(day, {}).get(period, 0)
            if slot_minutes <= 0:
                continue

            cell = tt.get(day, {}).get(period, empty_cell())
            event = cell.get("event") or {}
            main = cell.get("main") or {}

            klass = (cell.get("class") or "").strip()
            event_frac = float(event.get("fraction", 0.0) or 0.0)
            event_content = (event.get("content") or "").strip()
            main_subject = (main.get("subject") or "").strip()
            main_content = (main.get("content") or "").strip()

            if klass:
                return True
            if event_frac > 0:
                return True
            if event_content:
                return True
            if main_subject and main_subject != "（空欄）":
                return True
            if main_content:
                return True

    return False
        
def swap_cells_in_timetable(tt: dict, day_a: str, period_a: str, day_b: str, period_b: str):
    tt = normalize_timetable(tt)
    tt[day_a][period_a], tt[day_b][period_b] = tt[day_b][period_b], tt[day_a][period_a]
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
            msgs.append(f"{r['学年']} {r['教科等']}：不足 {round(remain,1)} コマ")
        if remain < -5:
            msgs.append(f"{r['学年']} {r['教科等']}：超過 {round(abs(remain),1)} コマ")
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


def user_where_clause(column="user_id"):
    return f"TRIM(COALESCE({column},'')) = ?"

# =========================
# 週案 / 自動保存 / 下書き
# =========================
def upsert_draft(school_year: str, user_id: str, teacher_name: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    user_id = str(user_id).strip()
    teacher_name = normalize_teacher_name(teacher_name)
    cur.execute(
        f"SELECT id FROM weekly_plans WHERE school_year=? AND {user_where_clause('user_id')} AND week=? AND status='下書き' ORDER BY id DESC LIMIT 1",
        (school_year, user_id, week_str),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE weekly_plans SET user_id=?, teacher_name=?, teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, submitted_at=DATETIME('now') WHERE id=?",
            (user_id, teacher_name, teacher_name, base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO weekly_plans (school_year, user_id, teacher_name, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '下書き', DATETIME('now'))",
            (school_year, user_id, teacher_name, teacher_name, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False)),
        )
    conn.commit()


def list_my_drafts(school_year: str, user_id: str):
    user_id = str(user_id).strip()
    cur.execute(
        f"SELECT id, week, grade, class, teacher_type, plan_json, submitted_at FROM weekly_plans WHERE school_year=? AND {user_where_clause('user_id')} AND status='下書き' ORDER BY week DESC, id DESC",
        (school_year, user_id),
    )
    return cur.fetchall()


def load_plan_by_id(wid: int):
    cur.execute("SELECT id, school_year, user_id, teacher_name, grade, class, teacher_type, week, plan_json, status FROM weekly_plans WHERE id=?", (wid,))
    return cur.fetchone()


def fetch_latest_plan_before_week(school_year: str, user_id: str, week_str: str):
    user_id = str(user_id).strip()
    cur.execute(
        f"SELECT plan_json, week, status FROM weekly_plans WHERE school_year=? AND {user_where_clause('user_id')} AND week < ? AND status IN ('提出','承認','差戻','下書き') ORDER BY week DESC, id DESC LIMIT 1",
        (school_year, user_id, week_str),
    )
    return cur.fetchone()


def submit_plan_from_current(school_year: str, user_id: str, teacher_name: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    user_id = str(user_id).strip()
    teacher_name = normalize_teacher_name(teacher_name)
    cur.execute(
        f"SELECT id FROM weekly_plans WHERE school_year=? AND {user_where_clause('user_id')} AND week=? AND status='下書き' ORDER BY id DESC LIMIT 1",
        (school_year, user_id, week_str),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE weekly_plans SET user_id=?, teacher_name=?, teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, status='提出', submitted_at=DATETIME('now') WHERE id=?",
            (user_id, teacher_name, teacher_name, base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO weekly_plans (school_year, user_id, teacher_name, teacher, grade, class, teacher_type, week, plan_json, status, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '提出', DATETIME('now'))",
            (school_year, user_id, teacher_name, teacher_name, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False)),
        )
    conn.commit()


def upsert_autosave(school_year: str, user_id: str, teacher_name: str, base_grade: str, class_name: str, teacher_type: str, week_str: str, plan: dict):
    user_id = str(user_id).strip()
    teacher_name = normalize_teacher_name(teacher_name)
    cur.execute(
        f"SELECT id FROM auto_save_sessions WHERE school_year=? AND {user_where_clause('user_id')} AND week=? ORDER BY id DESC LIMIT 1",
        (school_year, user_id, week_str),
    )
    row = cur.fetchone()
    meta = {
        "school_year": school_year,
        "user_id": user_id,
        "teacher_name": teacher_name,
        "grade": base_grade,
        "class": class_name,
        "teacher_type": teacher_type,
        "week": week_str,
    }
    if row:
        cur.execute(
            "UPDATE auto_save_sessions SET user_id=?, teacher_name=?, teacher=?, grade=?, class=?, teacher_type=?, plan_json=?, meta_json=?, saved_at=DATETIME('now') WHERE id=?",
            (user_id, teacher_name, teacher_name, base_grade, class_name, teacher_type, json.dumps(plan, ensure_ascii=False), json.dumps(meta, ensure_ascii=False), row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO auto_save_sessions (school_year, user_id, teacher_name, teacher, grade, class, teacher_type, week, plan_json, meta_json, saved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATETIME('now'))",
            (school_year, user_id, teacher_name, teacher_name, base_grade, class_name, teacher_type, week_str, json.dumps(plan, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)),
        )
    conn.commit()


def list_autosaves(school_year: str, user_id: str):
    user_id = str(user_id).strip()
    cur.execute(
        f"SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE school_year=? AND {user_where_clause('user_id')} ORDER BY saved_at DESC, id DESC",
        (school_year, user_id),
    )
    return cur.fetchall()


def fetch_latest_autosave(school_year: str, user_id: str):
    user_id = str(user_id).strip()
    cur.execute(
        f"SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE school_year=? AND {user_where_clause('user_id')} ORDER BY saved_at DESC, id DESC LIMIT 1",
        (school_year, user_id),
    )
    return cur.fetchone()


def load_autosave_by_id(sid: int):
    cur.execute("SELECT id, week, grade, class, teacher_type, saved_at, plan_json, meta_json FROM auto_save_sessions WHERE id=?", (sid,))
    return cur.fetchone()


def add_inquiry_log(school_year: str, week: str, grade: str, class_name: str, teacher: str, teacher_name: str, theme: str, goals: str, activities: str, evidence: str, reflection: str):
    cur.execute(
        "INSERT INTO inquiry_logs (school_year, week, grade, class, teacher, teacher_name, theme, goals, activities, evidence, reflection, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATETIME('now'))",
        (school_year, week, grade, class_name, teacher, teacher_name, theme, goals, activities, evidence, reflection),
    )
    conn.commit()


def fetch_inquiry_logs(school_year: str, grade: str = None, class_name: str = None, teacher: str = None):
    q = "SELECT id, school_year, week, grade, class, teacher, teacher_name, theme, goals, activities, evidence, reflection, created_at FROM inquiry_logs WHERE school_year=?"
    args = [school_year]
    if grade and grade != "すべて":
        q += " AND grade=?"
        args.append(grade)
    if class_name and class_name.strip():
        q += " AND class=?"
        args.append(class_name.strip())
    if teacher and teacher.strip():
        q += " AND TRIM(COALESCE(teacher,''))=?"
        args.append(str(teacher).strip())
    q += " ORDER BY created_at DESC, id DESC"
    cur.execute(q, tuple(args))
    return cur.fetchall()


def aggregate_events_from_plans(plans_rows) -> pd.DataFrame:
    out = []
    for (wid, sy, user_id, teacher_name, grade, class_name, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by) in plans_rows:
        try:
            plan = json.loads(plan_json) if plan_json else {}
        except Exception:
            plan = {}
        timetable = plan.get("timetable", {}) if isinstance(plan, dict) else {}
        week_mins = compute_week_subject_minutes(timetable, grade)
        for gg, mp in week_mins.items():
            ev = float(mp.get("学校行事", 0.0))
            if ev > 0:
                out.append({"年度": sy, "週": week, "学年": gg, "教員": teacher_label(user_id, teacher_name), "状態": status, "学校行事(分)": int(round(ev)), "学校行事(45分コマ)": round(convert_to_45(ev), 2)})
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
                klass = class_candidates[(idx - 1) % len(class_candidates)]
            tt[day][period] = {
                "class": klass,
                "event": {"fraction": frac, "content": ((cell.get("event") or {}).get("content") or "")},
                "main": {"subject": subj, "content": "（提案）単元名／ねらい／評価観点を入力"},
            }
    return tt

# =========================
# ログイン後共通
# =========================
current_school_year = get_current_school_year()
auth_user_id = st.session_state["auth_user_id"]
auth_display_name = st.session_state["auth_display_name"]
role = st.session_state["auth_role"]

st.title("小学校 週の指導計画（週案）管理システム（クラウド版）")

st.sidebar.markdown("### ログイン情報")
st.sidebar.write(f"ID：**{auth_user_id}**")
st.sidebar.write(f"氏名：**{auth_display_name}**")
st.sidebar.write(f"権限：**{role}**")
st.sidebar.markdown("---")
st.sidebar.write(f"📅 現在の年度：**{current_school_year}**")
st.sidebar.caption(f"DB: {DB_PATH}")

with st.sidebar.expander("🔑 パスワード変更", expanded=False):
    current_pw = st.text_input("現在のパスワード", type="password", key="pw_change_current")
    new_pw1 = st.text_input("新しいパスワード", type="password", key="pw_change_new1")
    new_pw2 = st.text_input("新しいパスワード（確認）", type="password", key="pw_change_new2")

    if st.button("パスワードを変更する", key="pw_change_btn"):
        auth = authenticate_user(auth_user_id, current_pw)
        if not auth:
            st.error("現在のパスワードが正しくありません。")
        elif not new_pw1:
            st.error("新しいパスワードを入力してください。")
        elif new_pw1 != new_pw2:
            st.error("新しいパスワード確認が一致しません。")
        else:
            update_user_password(auth_user_id, new_pw1)
            st.success("パスワードを変更しました。")

st.sidebar.markdown("---")
if st.sidebar.button("ログアウト", key="logout_btn"):
    logout()

# =========================
# 教員画面
# =========================
if role == "教員":
    st.header("📘 週案の作成・提出（教員用）")
    st.caption(f"提出先年度：{current_school_year}（管理職が設定）")
    st.info(f"ログイン中の利用者：{auth_display_name}（ID: {auth_user_id}）")

    # 画面用 state の初期化（ウィジェット生成前）
    st.session_state.setdefault("teacher_type", "担任")
    st.session_state.setdefault("base_grade", "3年")
    st.session_state.setdefault("class_name", "")
    st.session_state.setdefault("week_date", date.today())
    st.session_state.setdefault("restore_notice", False)
    st.session_state.setdefault("restore_plan", {"timetable": normalize_timetable({})})
    st.session_state.setdefault("class_name_input", st.session_state.get("class_name", ""))
    st.session_state.setdefault("week_date_input", st.session_state.get("week_date", date.today()))
    st.session_state.setdefault("classes_input", st.session_state.get("class_name", ""))

    teacher_key = auth_user_id
    teacher_display = auth_display_name

    st.markdown("---")
    st.subheader("🗂 下書き一覧（復元）")
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
                _id, _sy, _uid, _tname, _g, _c, _tt, _wk, _pj, _stt = row
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
                st.session_state["class_name_input"] = restored_class
                try:
                    restored_date = date.fromisoformat(_wk)
                    st.session_state["week_date"] = restored_date
                    st.session_state["week_date_input"] = restored_date
                except Exception:
                    pass

                apply_timetable_to_widget_state(restored_tt, restored_teacher_type)
                st.session_state["restore_notice"] = True
                st.success("下書きを復元しました。")
                st.rerun()
    else:
        st.caption("下書きはまだありません。")

    st.markdown("---")
    st.subheader("🛟 前回の続きから再開 / 自動保存")
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
                st.session_state["class_name_input"] = restored_class
                try:
                    restored_date = date.fromisoformat(_wk)
                    st.session_state["week_date"] = restored_date
                    st.session_state["week_date_input"] = restored_date
                except Exception:
                    pass

                apply_timetable_to_widget_state(restored_tt, restored_teacher_type)
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
                st.session_state["class_name_input"] = restored_class
                try:
                    restored_date = date.fromisoformat(_wk)
                    st.session_state["week_date"] = restored_date
                    st.session_state["week_date_input"] = restored_date
                except Exception:
                    pass

                apply_timetable_to_widget_state(restored_tt, restored_teacher_type)
                st.session_state["restore_notice"] = True
                st.success("自動保存データを復元しました。")
                st.rerun()
    else:
        st.caption("自動保存データ一覧はまだありません。")

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
        key="class_name_input"
    )
    st.session_state["class_name"] = class_name

    week = st.date_input(
        "対象週（週の初日：月曜日など）",
        key="week_date_input"
    )
    st.session_state["week_date"] = week
    week_str = str(week)

    if teacher_type == "担任":
        subject_options = ["（空欄）"] + get_subjects_for_grade(base_grade)
        st.caption("※ 担任は、その学年で扱う教科のみ選択できます。")
        class_candidates = [class_name] if class_name else []
    else:
        subject_options = ["（空欄）"] + ALL_SUBJECTS
        st.caption("※ 専科は、各コマで学級・教科を自由に選択できます。")

        # ── 専科：指導学級 選択式タグUI ──────────────────────────────
        st.markdown("##### 📋 この週に指導する学級を選択してください")

        all_class_candidates = [f"{g}-{c}" for g in range(1, 7) for c in range(1, 5)]
        prev_classes_raw = st.session_state.get("classes_input", "")
        prev_selected = [c.strip() for c in prev_classes_raw.split(",") if c.strip()]

        quick_cols = st.columns(6)
        selected_classes_set = set(prev_selected)
        for g in range(1, 7):
            with quick_cols[g-1]:
                if st.button(f"{g}年を追加", key=f"add_grade_{g}"):
                    for c in range(1, 5):
                        selected_classes_set.add(f"{g}-{c}")
                    st.session_state["classes_input"] = ",".join(sorted(selected_classes_set))
                    st.rerun()
                if st.button(f"{g}年解除", key=f"remove_grade_{g}"):
                    for c in range(1, 5):
                        selected_classes_set.discard(f"{g}-{c}")
                    st.session_state["classes_input"] = ",".join(sorted(selected_classes_set))
                    st.rerun()

        selected_classes = st.multiselect(
            "指導学級（複数選択）",
            options=all_class_candidates,
            default=sorted(selected_classes_set, key=lambda x: (int(x.split("-")[0]), int(x.split("-")[1]))),
            key="special_class_multiselect",
            help="チェック式で複数の学級を選択できます。"
        )

        extra_input = st.text_input(
            "上記以外の学級を追加（カンマ区切り 例：たんぽぽ）",
            key="classes_extra_input",
            placeholder="例：たんぽぽ,つくし"
        )
        extra_classes = [c.strip() for c in extra_input.split(",") if c.strip()]

        class_candidates = list(selected_classes)
        for c in extra_classes:
            if c not in class_candidates:
                class_candidates.append(c)

        def class_sort_key(x):
            if "-" in x and x.split("-")[0].isdigit() and x.split("-")[1].isdigit():
                return (0, int(x.split("-")[0]), int(x.split("-")[1]), x)
            return (1, 999, 999, x)

        class_candidates = sorted(class_candidates, key=class_sort_key)
        st.session_state["classes_input"] = ",".join(class_candidates)

        if class_candidates:
            st.markdown("###### 選択中の学級")
            chips = "".join([f"<span class='tag-chip'>{c}</span>" for c in class_candidates])
            st.markdown(chips, unsafe_allow_html=True)
        else:
            st.caption("※ 学級が未選択の場合、学級欄は空欄のままとなります。")
        # ────────────────────────────────────────────────────────

    st.markdown("---")
    st.subheader("⭐ 前週コピー")
    if st.button("⬅ 前週の週案をコピーする", key="copy_prev_week"):
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
            apply_timetable_to_widget_state(restored_tt, teacher_type)
            st.success(f"前週（{prev_week}）をコピーしました。")
            st.rerun()

    st.subheader("⭐ 週案自動生成（提案）")
    st.caption("※外部AIは使いません。年間時数の残り状況から、空欄コマに教科を提案して埋めます（既存入力は保持）。")
    if st.button("🤖 空欄コマに教科を提案して自動入力", key="auto_fill_btn"):
        restore_plan = st.session_state.get("restore_plan") or {"timetable": normalize_timetable({})}
        tt = normalize_timetable(restore_plan.get("timetable", {}))
        tt = auto_fill_timetable_proposal(current_school_year, teacher_type, base_grade, class_name, class_candidates, tt)

        st.session_state["restore_plan"] = {"timetable": tt}
        apply_timetable_to_widget_state(tt, teacher_type)
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
            apply_timetable_to_widget_state(timetable, teacher_type)
            st.success("入替しました。")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 一週間の時間割を入力してください（表形式）")
    st.caption("行：校時／列：曜日。各マスで『学校行事(3/8等)＋残り教科』『内容』を入力します。")

    header_cols = st.columns(COLUMN_WIDTHS)
    header_cols[0].markdown('<div class="tt-headcell">　</div>', unsafe_allow_html=True)
    for i, day in enumerate(DAYS, start=1):
        header_cols[i].markdown(f'<div class="tt-headcell">{day}</div>', unsafe_allow_html=True)

    event_opts = [x[0] for x in EVENT_FRACTIONS]

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

                    if f"{day}_{period}_eventfrac" not in st.session_state:
                        st.session_state[f"{day}_{period}_eventfrac"] = fraction_value_to_label(float(default_event.get("fraction", 0.0) or 0.0))
                    if f"{day}_{period}_eventcont" not in st.session_state:
                        st.session_state[f"{day}_{period}_eventcont"] = (default_event.get("content") or "").strip()
                    if f"{day}_{period}_mainsubj" not in st.session_state:
                        st.session_state[f"{day}_{period}_mainsubj"] = (default_main.get("subject") or "（空欄）").strip()
                    if f"{day}_{period}_maincont" not in st.session_state:
                        st.session_state[f"{day}_{period}_maincont"] = (default_main.get("content") or "").strip()
                    if teacher_type.startswith("専科") and f"{day}_{period}_class" not in st.session_state:
                        st.session_state[f"{day}_{period}_class"] = default_class if default_class else "（未選択）"

                    if st.session_state.get(f"{day}_{period}_eventfrac", "なし") not in event_opts:
                        st.session_state[f"{day}_{period}_eventfrac"] = "なし"
                    if st.session_state.get(f"{day}_{period}_mainsubj", "（空欄）") not in subject_options:
                        st.session_state[f"{day}_{period}_mainsubj"] = "（空欄）"

                    if teacher_type.startswith("専科"):
                        if class_candidates:
                            opts = ["（未選択）"] + class_candidates
                            if st.session_state.get(f"{day}_{period}_class", "（未選択）") not in opts:
                                st.session_state[f"{day}_{period}_class"] = "（未選択）"
                            klass_selected = st.selectbox("学級", opts, key=f"{day}_{period}_class", label_visibility="collapsed")
                            klass = "" if klass_selected == "（未選択）" else klass_selected
                        else:
                            klass = ""
                    else:
                        klass = class_name

                    st.markdown('<div class="tt-section tt-event">🟨 学校行事（配分）</div>', unsafe_allow_html=True)
                    event_label = st.selectbox("学校行事（配分）", event_opts, key=f"{day}_{period}_eventfrac", label_visibility="collapsed")
                    st.markdown('<div class="tt-mini">※ 3/8・6/8・8/8 を選択できます。</div>', unsafe_allow_html=True)

                    event_frac = fraction_label_to_value(event_label)
                    event_minutes = minutes * event_frac
                    remain_minutes = minutes - event_minutes

                    event_content = ""
                    if event_frac > 0:
                        st.markdown('<div class="tt-section tt-event">🟨 学校行事（内容）</div>', unsafe_allow_html=True)
                        event_content = st.text_area("学校行事 内容", key=f"{day}_{period}_eventcont", height=45, label_visibility="collapsed")

                    main_subject = "（空欄）"
                    main_content = ""
                    if remain_minutes > 0:
                        st.markdown('<div class="tt-section tt-main">🟦 残り教科等</div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="tt-mini">残り：{int(round(remain_minutes))}分</div>', unsafe_allow_html=True)

                        main_subject = st.selectbox("残り枠の教科等", subject_options, key=f"{day}_{period}_mainsubj", label_visibility="collapsed")
                        main_content = st.text_area("残り枠の内容", key=f"{day}_{period}_maincont", height=55, label_visibility="collapsed")

                    timetable[day][period] = {"class": klass, "event": {"fraction": event_frac, "content": event_content}, "main": {"subject": main_subject, "content": main_content}}
                    st.markdown("</div>", unsafe_allow_html=True)

st.session_state["restore_plan"] = {"timetable": timetable}

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
st.caption(f"…他 {len(warn_msgs)-20} 件")
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
slot_rows.append({"年度": current_school_year, "教員ID": teacher_key, "教員名": teacher_display, "基準学年": base_grade, "担任学級": class_name, "勤務形態": teacher_type, "週": week_str, "曜日": day, "校時": period, "分": int(round(mins)), "学級": cell.get("class", ""), "教科等": "", "内容": ""})
else:
for seg in segs:
slot_rows.append({"年度": current_school_year, "教員ID": teacher_key, "教員名": teacher_display, "基準学年": base_grade, "担任学級": class_name, "勤務形態": teacher_type, "週": week_str, "曜日": day, "校時": period, "分": int(round(seg.get("minutes", 0))), "学級": seg.get("class", ""), "教科等": seg.get("subject", ""), "内容": seg.get("content", "")})
df_my = pd.DataFrame(slot_rows)
my_csv = df_my.to_csv(index=False).encode("utf-8-sig")
today_str = date.today().strftime("%Y%m%d")
my_name = f"{teacher_key}_{base_grade}_{week_str}_{today_str}_my_weekly_plan.csv".replace("/", "_")
st.download_button("⬇️ この週案をCSVで保存", my_csv, my_name, "text/csv")

st.markdown("---")
st.subheader("⭐ 探究活動ログ（総合 / 学校裁量（探究）など）")
with st.expander("➕ 探究ログを追加", expanded=False):
theme = st.text_input("テーマ", key="inq_theme")
goals = st.text_area("ねらい（育てたい力）", key="inq_goals", height=80)
activities = st.text_area("活動（学習の流れ）", key="inq_activities", height=100)
evidence = st.text_area("証拠（成果物 / 写真 / 発表 / ルーブリック等）", key="inq_evidence", height=80)
reflection = st.text_area("振り返り（児童 / 教師）", key="inq_reflection", height=100)
if st.button("保存する", key="inq_save_btn"):
add_inquiry_log(current_school_year, week_str, base_grade, class_name, teacher_key, teacher_display, theme, goals, activities, evidence, reflection)
st.success("探究ログを保存しました。")

with st.expander("📚 自分 / 学年の探究ログを確認", expanded=False):
gsel = st.selectbox("学年", ["すべて"] + list(STANDARD_HOURS.keys()), key="inq_grade_filter")
csel = st.text_input("学級（空欄で全学級）", key="inq_class_filter")
tsel = st.text_input("教員ID（空欄で全教員）", value=teacher_key, key="inq_teacher_filter")
logs = fetch_inquiry_logs(current_school_year, grade=gsel, class_name=csel, teacher=tsel)
if not logs:
st.info("探究ログはまだありません。")
else:
df_logs = pd.DataFrame(logs, columns=["id","school_year","week","grade","class","teacher","teacher_name","theme","goals","activities","evidence","reflection","created_at"])
st.dataframe(df_logs.drop(columns=["school_year"]), use_container_width=True, height=320)

st.markdown("---")
st.subheader("📝 一時保存・提出")
col_a, col_b = st.columns(2)
with col_a:
if st.button("💾 一時保存（作業中断用）", key="draft_save_btn"):
plan = {"timetable": timetable}
upsert_draft(current_school_year, teacher_key, teacher_display, base_grade, class_name, teacher_type, week_str, plan)
upsert_autosave(current_school_year, teacher_key, teacher_display, base_grade, class_name, teacher_type, week_str, plan)
st.session_state["restore_plan"] = {"timetable": timetable}
st.success("一時保存しました。下書き一覧 / 自動保存一覧から再開できます。")
with col_b:
if st.button("✅ この内容で管理職へ提出する", key="submit_btn"):
errors = validate_timetable_for_submit(timetable, teacher_type)
if errors:
st.error("入力に不備があります。下記を修正してください：")
for e in errors:
st.write(f"- {e}")
else:
submit_plan_from_current(current_school_year, teacher_key, teacher_display, base_grade, class_name, teacher_type, week_str, {"timetable": timetable})
st.success("週案を提出しました。管理職の承認をお待ちください。")

    st.markdown("---")
    st.subheader("📄 印刷・PDF保存用レイアウト（教員用）")
    if st.checkbox("この週案を印刷用に表示する（A4縦1枚フィット）", key="print_toggle"):
        df_print = build_print_df(timetable)
        if df_print.empty:
            st.info("有効なコマがありません。")
        else:
            header_html = (
                f"<div class='print-header print-only'>"
                f"<strong>東小松川小学校　週の指導計画</strong>　　"
                f"{current_school_year}　{base_grade}　{class_name}　"
                f"{teacher_display}（{teacher_key}）　対象週：{week_str}"
                f"</div>"
            )
            # Build HTML table for print
            col_w0 = "7%"
            col_wd = f"{93 // len(DAYS)}%"
            th_days = "".join(f"<th style='width:{col_wd}'>{d}</th>" for d in DAYS)
            table_rows = ""
            for period in df_print.index:
                row_cells = ""
                for day in DAYS:
                    val = df_print.at[period, day]
                    lines = str(val).split("\n") if val else []
                    cell_html = ""
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("[") and "]" in line:
                            cell_html += f"<div class='print-cell-subject'>{line}</div>"
                        else:
                            cell_html += f"<div class='print-cell-content'>{line}</div>"
                    row_cells += f"<td>{cell_html}</td>"
                table_rows += f"<tr><th>{period}</th>{row_cells}</tr>"
            table_html = (
                f"<table class='print-weekly-table' style='display:table'>"
                f"<thead><tr><th style='width:{col_w0}'></th>{th_days}</tr></thead>"
                f"<tbody>{table_rows}</tbody>"
                f"</table>"
            )
            st.markdown(header_html + table_html, unsafe_allow_html=True)
            # Screen view
            st.write(f"**{current_school_year}／{base_grade}／{class_name}／{teacher_display}（{teacher_key}）／{week_str}**")
            st.dataframe(df_print, use_container_width=True, height=480)
            st.info("💡 ブラウザの印刷（Ctrl+P / ⌘+P）→「用紙サイズ：A4」「余白：なし or 最小」で1枚に収まります。")

# =========================
# 管理職画面
# =========================
if role == "管理職":
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
            init_year_hours_zero(view_year, initialized_by=auth_user_id)
            st.success(f"{view_year} を初期化しました。")
            st.rerun()
    else:
        st.info(f"✅ {view_year} は初期化済みです。")

    cur.execute("SELECT id, school_year, user_id, teacher_name, grade, class, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by FROM weekly_plans WHERE school_year=? ORDER BY id DESC", (view_year,))
    all_rows = cur.fetchall()

    st.markdown("---")
    st.header("⭐ ダッシュボード（管理職）")
    if all_rows:
        df_plans = pd.DataFrame(all_rows, columns=["id","school_year","user_id","teacher_name","grade","class","teacher_type","week","plan_json","status","submitted_at","approved_at","approved_by"])
        st.subheader("提出状況（件数）")
        counts = df_plans["status"].value_counts().to_dict()

        draft_count = int(counts.get("下書き", 0))
        submitted_count = int(counts.get("提出", 0))
        approved_count = int(counts.get("承認", 0))
        rejected_count = int(counts.get("差戻", 0))

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("下書き", draft_count)
        with m2:
            st.metric("提出", submitted_count)
        with m3:
            st.metric("承認", approved_count)
        with m4:
            st.metric("差戻", rejected_count)

        st.caption("現在の年度に登録されている週案の状態別件数です。")

        cda1, cda2 = st.columns(2)
        with cda1:
            st.subheader("提出状況（教員別）")
            df_plans["教員表示"] = df_plans.apply(lambda r: teacher_label(r["user_id"], r["teacher_name"]), axis=1)
            by_teacher = df_plans.groupby(["教員表示", "status"]).size().reset_index(name="count")
            pivot = by_teacher.pivot_table(index="教員表示", columns="status", values="count", fill_value=0)
            st.dataframe(pivot.reset_index(), use_container_width=True, height=240)
        with cda2:
            st.subheader("提出状況（学年別）")
            by_grade = df_plans.groupby(["grade","status"]).size().reset_index(name="count")
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

    # ══════════════════════════════════════════════════════
    # 未提出一覧（色分け＋カード表示強化版）
    # ══════════════════════════════════════════════════════
    st.markdown("---")
    st.subheader("🔴 未提出一覧")
    st.caption("週案を一度も提出していない教員×週の組み合わせを、色分けカードとマトリクスで表示します。")

    all_weeks_in_db = sorted({r[7] for r in all_rows if r[7]}, reverse=True)
    cur.execute("SELECT user_id, display_name FROM users WHERE role='教員' ORDER BY display_name")
    all_teachers = cur.fetchall()

    if not all_teachers:
        st.info("教員ユーザーがまだ登録されていません。")
    elif not all_weeks_in_db:
        st.info("週案の提出が1件もないため、未提出一覧は作成できません。")
    else:
        filt1, filt2, filt3 = st.columns([2, 2, 2])
        with filt1:
            unsubmit_week_filter = st.selectbox(
                "対象週で絞り込む",
                ["すべての週"] + all_weeks_in_db,
                key="unsubmit_week_filter"
            )
        with filt2:
            unsubmit_show_draft = st.checkbox(
                "下書きのみも未提出に含める",
                value=True,
                key="unsubmit_show_draft"
            )
        with filt3:
            teacher_name_options = ["全教員"] + [dname or uid for uid, dname in all_teachers]
            unsubmit_teacher_filter = st.selectbox(
                "教員で絞り込む",
                teacher_name_options,
                key="unsubmit_teacher_filter"
            )

        submitted_set = set()
        draft_set = set()
        known_set = set()
        for r in all_rows:
            uid, week_r, status_r = r[2], r[7], r[9]
            known_set.add((uid, week_r))
            if status_r in ("提出", "承認", "差戻"):
                submitted_set.add((uid, week_r))
            elif status_r == "下書き":
                draft_set.add((uid, week_r))

        target_weeks = all_weeks_in_db if unsubmit_week_filter == "すべての週" else [unsubmit_week_filter]

        unsubmit_rows = []
        matrix_rows = []
        for uid, dname in all_teachers:
            display_name = dname or uid
            if unsubmit_teacher_filter != "全教員" and display_name != unsubmit_teacher_filter:
                continue
            for wk in target_weeks:
                if (uid, wk) in submitted_set:
                    matrix_rows.append({"表示": f"{display_name}（{uid}）", "週": wk, "状態": "提出済み", "記号": "済", "class": "done"})
                    continue
                if (uid, wk) in draft_set:
                    matrix_rows.append({"表示": f"{display_name}（{uid}）", "週": wk, "状態": "下書きのみ", "記号": "下", "class": "draft"})
                    if unsubmit_show_draft:
                        unsubmit_rows.append({"教員ID": uid, "氏名": display_name, "週": wk, "状況": "下書きのみ", "表示": f"{display_name}（{uid}）"})
                    continue
                matrix_rows.append({"表示": f"{display_name}（{uid}）", "週": wk, "状態": "未登録", "記号": "未", "class": "miss"})
                unsubmit_rows.append({"教員ID": uid, "氏名": display_name, "週": wk, "状況": "未登録", "表示": f"{display_name}（{uid}）"})

        if not unsubmit_rows:
            st.success("✅ 対象条件では未提出はありません。全教員提出済みです。")
        else:
            df_unsubmit = pd.DataFrame(unsubmit_rows)
            df_matrix = pd.DataFrame(matrix_rows)

            total_missing = len(df_unsubmit)
            teacher_missing = df_unsubmit["教員ID"].nunique()
            week_missing = df_unsubmit["週"].nunique()
            draft_only_count = int((df_unsubmit["状況"] == "下書きのみ").sum())

            s1, s2, s3, s4 = st.columns(4)
            with s1:
                st.metric("未提出件数", total_missing)
            with s2:
                st.metric("該当教員数", teacher_missing)
            with s3:
                st.metric("対象週数", week_missing)
            with s4:
                st.metric("下書きのみ", draft_only_count)

            left, right = st.columns([1.0, 2.0])

            with left:
                st.markdown("#### 教員カード表示")
                teacher_summary = (
                    df_unsubmit.groupby(["氏名", "教員ID", "状況"]).size().reset_index(name="件数")
                )
                teacher_totals = (
                    df_unsubmit.groupby(["氏名", "教員ID"]).size().reset_index(name="合計件数").sort_values(["合計件数", "氏名"], ascending=[False, True])
                )
                for _, row in teacher_totals.iterrows():
                    person_rows = teacher_summary[(teacher_summary["氏名"] == row["氏名"]) & (teacher_summary["教員ID"] == row["教員ID"])]
                    missing_cnt = int(person_rows.loc[person_rows["状況"] == "未登録", "件数"].sum())
                    draft_cnt = int(person_rows.loc[person_rows["状況"] == "下書きのみ", "件数"].sum())
                    css = "status-missing" if missing_cnt > 0 else "status-draft"
                    detail = []
                    if missing_cnt > 0:
                        detail.append(f"未登録 {missing_cnt}件")
                    if draft_cnt > 0:
                        detail.append(f"下書きのみ {draft_cnt}件")
                    st.markdown(
                        f"<div class='status-card {css}'>{row['氏名']}（{row['教員ID']}）<br><span style='font-weight:500'>{' / '.join(detail)}</span></div>",
                        unsafe_allow_html=True
                    )

            with right:
                st.markdown("#### 週 × 教員 マトリクス")
                matrix_people = list(dict.fromkeys(df_matrix["表示"].tolist()))
                matrix_weeks = target_weeks
                html = ["<table class='matrix-table'><thead><tr><th>教員</th>"]
                for wk in matrix_weeks:
                    html.append(f"<th>{wk}</th>")
                html.append("</tr></thead><tbody>")
                for person in matrix_people:
                    html.append(f"<tr><td>{person}</td>")
                    for wk in matrix_weeks:
                        hit = df_matrix[(df_matrix["表示"] == person) & (df_matrix["週"] == wk)]
                        if hit.empty:
                            html.append("<td><span class='matrix-cell empty'>-</span></td>")
                        else:
                            rec = hit.iloc[0]
                            html.append(f"<td><span class='matrix-cell {rec['class']}' title='{rec['状態']}'>{rec['記号']}</span></td>")
                    html.append("</tr>")
                html.append("</tbody></table>")
                st.markdown("".join(html), unsafe_allow_html=True)
                st.caption("凡例：未=未登録 / 下=下書きのみ / 済=提出済み")

            with st.expander("📋 未提出 明細一覧", expanded=False):
                detail_df = df_unsubmit[["週", "氏名", "教員ID", "状況"]].sort_values(["週", "氏名"])
                st.dataframe(detail_df, use_container_width=True, height=320)

            unsubmit_csv = df_unsubmit[["週", "氏名", "教員ID", "状況"]].sort_values(["週", "氏名"]).to_csv(index=False).encode("utf-8-sig")
            today_str = date.today().strftime("%Y%m%d")
            st.download_button(
                "⬇️ 未提出一覧をCSVでダウンロード",
                unsubmit_csv,
                f"{safe_year_str(view_year)}_未提出一覧_{today_str}.csv",
                "text/csv",
                key="unsubmit_csv_dl"
            )
    # ══════════════════════════════════════════════════════

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
        stt = r[9]
        if stt in counts:
            counts[stt] += 1
    st.markdown("#### 状態別件数")
    st.write(f"- 下書き：{counts['下書き']} 件")
    st.write(f"- 提出：{counts['提出']} 件")
    st.write(f"- 承認：{counts['承認']} 件")
    st.write(f"- 差戻：{counts['差戻']} 件")

    grade_list = sorted({r[4] for r in all_rows if r[4]})
    teacher_list = sorted({teacher_label(r[2], r[3]) for r in all_rows if r[2] or r[3]})
    week_list = sorted({r[7] for r in all_rows if r[7]}, reverse=True)

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
        rows = [r for r in rows if r[9] == filter_status]
    if grade_filter != "すべて":
        rows = [r for r in rows if r[4] == grade_filter]
    if teacher_filter != "すべて":
        rows = [r for r in rows if teacher_label(r[2], r[3]) == teacher_filter]
    if week_filter != "すべて":
        rows = [r for r in rows if r[7] == week_filter]
    if only_unapproved:
        rows = [r for r in rows if r[9] not in ("承認", "下書き")]

    if not rows:
        st.info("該当する週案はありません。")
    else:
        st.caption("※ 各行をクリックすると詳細が表示されます。")

    for (wid, school_year, user_id, teacher_name, grade, class_name, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by) in rows:
        try:
            plan = json.loads(plan_json) if plan_json else {}
        except Exception:
            plan = {}
        timetable = normalize_timetable(plan.get("timetable", {}))
        week_minutes_all = compute_week_subject_minutes(timetable, grade)
        title = f"ID:{wid} / {school_year} / {week} / {grade} / {class_name} / {teacher_label(user_id, teacher_name)} / 状態：{status}"

        with st.expander(title):
            st.markdown(f"状態：{status_badge(status)}", unsafe_allow_html=True)
            st.write(f"- 勤務形態：{teacher_type if teacher_type else '（未記録）'}")
            st.write(f"- 提出者：{teacher_label(user_id, teacher_name)}")
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
                        cur.execute("UPDATE weekly_plans SET status='承認', approved_at=DATETIME('now'), approved_by=? WHERE id=?", (auth_user_id, wid))
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
        cur.execute("SELECT id, school_year, user_id, teacher_name, grade, class, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by FROM weekly_plans WHERE school_year=? ORDER BY id DESC", (school_year,))
        return cur.fetchall()

    def flatten_plans_to_rows(plans):
        plan_rows, slot_rows = [], []
        for (wid, sy, user_id, teacher_name, grade, class_name, teacher_type, week, plan_json, status, submitted_at, approved_at, approved_by) in plans:
            plan_rows.append({"id": wid, "school_year": sy, "user_id": user_id, "teacher_name": teacher_name, "grade": grade, "class": class_name, "teacher_type": teacher_type, "week": week, "status": status, "submitted_at": submitted_at, "approved_at": approved_at, "approved_by": approved_by})
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
                        slot_rows.append({"plan_id": wid, "school_year": sy, "week": week, "user_id": user_id, "teacher_name": teacher_name, "base_grade": grade, "base_class": class_name, "teacher_type": teacher_type, "day": day, "period": period, "minutes": int(round(slot_minutes)), "class": cell.get("class", ""), "subject": "", "content": "", "status": status})
                    else:
                        for seg in segs:
                            slot_rows.append({"plan_id": wid, "school_year": sy, "week": week, "user_id": user_id, "teacher_name": teacher_name, "base_grade": grade, "base_class": class_name, "teacher_type": teacher_type, "day": day, "period": period, "minutes": int(round(seg.get("minutes", 0))), "class": seg.get("class", ""), "subject": seg.get("subject", ""), "content": seg.get("content", ""), "status": status})
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
            "hours_progress": df_hours.to_csv(index=False).encode("utf-8-sig"),
        }
        st.session_state["backup_filename"] = filename
        log_backup(view_year, created_by=auth_user_id, filename=filename)
        st.success("バックアップを作成しました。")

    if st.session_state["backup_excel_bytes"]:
        today_str = date.today().strftime("%Y%m%d")
        st.download_button("⬇️ バックアップ一括（Excel）をダウンロード", st.session_state["backup_excel_bytes"], st.session_state["backup_filename"] or f"{safe_year_str(view_year)}_weekly_plan_backup_{today_str}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        csv_pack = st.session_state["backup_csv_pack"] or {}
        st.download_button("⬇️ 週案一覧（CSV）", csv_pack.get("weekly_plans", b""), f"{safe_year_str(view_year)}_weekly_plans_{today_str}.csv", "text/csv")
        st.download_button("⬇️ 時間割（コマ明細）（CSV）", csv_pack.get("weekly_slots", b""), f"{safe_year_str(view_year)}_weekly_slots_{today_str}.csv", "text/csv")
        st.download_button("⬇️ 年間累積（進捗）（CSV）", csv_pack.get("hours_progress", b""), f"{safe_year_str(view_year)}_hours_progress_{today_str}.csv", "text/csv")

    st.markdown("---")
    st.header("🏛 区教委提出用（年間時数 まとめCSV）")
    df_submit = build_hours_progress_df(view_year).rename(columns={"標準(45分コマ)": "標準（45分コマ）", "実施累積(45分コマ)": "実施累積（45分コマ）", "残り(45分コマ)": "残り（45分コマ）", "進捗(%)": "進捗（％）"})[["年度","学年","教科等","標準（45分コマ）","実施累積（45分コマ）","残り（45分コマ）","進捗（％）"]]
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
    gsel2 = st.selectbox("学年フィルタ", ["すべて"] + list(STANDARD_HOURS.keys()), key="inq_m_grade")
    csel2 = st.text_input("学級フィルタ（空欄で全学級）", key="inq_m_class")
    tsel2 = st.text_input("教員IDフィルタ（空欄で全教員）", key="inq_m_teacher")
    logs2 = fetch_inquiry_logs(view_year, grade=gsel2, class_name=csel2, teacher=tsel2)
    if not logs2:
        st.info("探究ログはまだありません。")
    else:
        df_logs2 = pd.DataFrame(logs2, columns=["id","school_year","week","grade","class","teacher","teacher_name","theme","goals","activities","evidence","reflection","created_at"])
        df_logs2["教員表示"] = df_logs2.apply(lambda r: teacher_label(r["teacher"], r["teacher_name"]), axis=1)
        df_logs2 = df_logs2.drop(columns=["school_year"])
        df_logs2 = df_logs2.rename(columns={"teacher": "教員ID", "teacher_name": "教員名"})
        cols = ["id", "week", "grade", "class", "教員表示", "theme", "goals", "activities", "evidence", "reflection", "created_at"]
        st.dataframe(df_logs2[cols], use_container_width=True, height=380)
