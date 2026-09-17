"""
配置文件：API密钥、模型名、常量
==============================
所有可调参数集中在这里，改参数不用翻代码
"""

import os

# ---- 大模型 API 配置 ----
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = "https://api.deepseek.com"
MODEL_NAME = "deepseek-v4-pro"

# ---- Tavily 搜索 API ----
# 注册地址：https://tavily.com 免费额度1000次/月
# 密钥只从环境变量读取，不要把 key 写进代码/提交进 git
# Windows: set TAVILY_API_KEY=你的key   |   Mac/Linux: export TAVILY_API_KEY=你的key
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# ---- Agent 参数 ----
MAX_ROUNDS = 5          # Function Calling 最大循环轮数
MAX_HISTORY = 6         # 携带的历史消息条数

# ---- 数据库 ----
DB_PATH = "chat_history.db"  # SQLite 数据库文件路径
