"""
对话持久化模块
==============
用 SQLite 存储对话历史，重启应用不丢失数据

为什么用 SQLite 而不是 JSON 文件：
- JSON 每次要读全文再写全文，数据多了会慢
- SQLite 是数据库，增删改查都快，自带事务安全
- 不用额外装服务，一个 .db 文件就搞定
"""

import sqlite3
import json
from config import DB_PATH


class ChatMemory:
    """对话记忆管理器"""

    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        """建表（如果不存在的话）"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def save_message(self, agent_name, role, content):
        """保存一条消息"""
        self.conn.execute(
            "INSERT INTO messages (agent_name, role, content) VALUES (?, ?, ?)",
            (agent_name, role, content)
        )
        self.conn.commit()

    def load_history(self, agent_name, limit=20):
        """加载某个Agent的历史消息（最近的limit条）"""
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE agent_name = ? ORDER BY id DESC LIMIT ?",
            (agent_name, limit)
        ).fetchall()
        # 倒序变正序（最旧在前）
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def clear_history(self, agent_name):
        """清除某个Agent的对话历史"""
        self.conn.execute(
            "DELETE FROM messages WHERE agent_name = ?",
            (agent_name,)
        )
        self.conn.commit()

    def get_all_agents(self):
        """获取有对话记录的所有Agent名称"""
        rows = self.conn.execute(
            "SELECT DISTINCT agent_name FROM messages"
        ).fetchall()
        return [r[0] for r in rows]
