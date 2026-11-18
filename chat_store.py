"""
会话持久化：SQLite 保存对话历史，刷新页面 / 重启应用不丢。

设计：
  - 数据库文件 data/chat.db（已被 .gitignore 忽略，对话属于用户隐私）
  - 会话 ID 通过 URL 参数 ?sid=xxx 传递——浏览器刷新后 URL 不变，历史可恢复
  - 全部使用参数化查询，无 SQL 注入风险
"""
import os
import re
import sqlite3
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "chat.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    caption    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def new_session_id():
    """生成随机会话 ID"""
    return uuid.uuid4().hex[:12]


def sanitize_sid(raw):
    """清洗 URL 里传入的 sid，只保留安全字符，防止注入（参数化查询之外的双保险）"""
    if not raw:
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", str(raw))[:32]
    return cleaned or None


def load_messages(session_id, limit=100):
    """加载会话历史，返回 [{"role", "content", "caption"}, ...]（按时间升序）"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, caption FROM messages "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def append_message(session_id, role, content, caption=""):
    """追加一条消息"""
    if not content:
        return
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, caption, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, caption or "",
             datetime.now().isoformat(timespec="seconds")),
        )


def clear_session(session_id):
    """清空一个会话的全部消息"""
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))


def count_messages(session_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row["n"]
