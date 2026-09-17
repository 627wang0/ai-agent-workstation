"""
工具层（Tools）
==============
每个工具 = 函数实现 + JSON描述（给大模型看的）

升级内容：
1. 模拟搜索 → Tavily 真实搜索
2. 文本摘要 → 接入LLM做真正摘要（不再是截取前几句）
3. 新增文件读写工具
"""

import json
import datetime
import re
import os

from config import API_KEY, BASE_URL, MODEL_NAME, TAVILY_API_KEY


# ============================================================
# 工具1：计算器
# ============================================================
def calculate(expression: str) -> str:
    """
    执行数学计算
    参数：expression - 数学表达式，如 "123 * 456 + 789"
    返回：计算结果（字符串）
    """
    try:
        # 安全计算：只允许数字和运算符
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return "错误：表达式包含不允许的字符"
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"计算错误：{str(e)}"


CALCULATE_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "执行数学计算，支持加减乘除、幂运算、括号等。当用户提出计算相关的问题时使用此工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '123 * 456 + 789' 或 '2 ** 10' 或 '(100 + 200) / 3'"
                }
            },
            "required": ["expression"]
        }
    }
}


# ============================================================
# 工具2：获取当前时间
# ============================================================
def get_current_time() -> str:
    """
    获取当前日期和时间
    """
    now = datetime.datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[now.weekday()]
    return now.strftime(f"%Y-%m-%d %H:%M:%S {weekday}")


GET_TIME_TOOL = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "获取当前的日期和时间。当用户询问'现在几点'、'今天星期几'、'今天日期'等时间相关问题时使用。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


# ============================================================
# 工具3：文本摘要（升级版：用LLM做真正摘要）
# ============================================================
def summarize_text(text: str, max_length: int = 200) -> str:
    """
    用大模型对长文本进行摘要
    不再是截取前几句，而是LLM理解全文后生成摘要
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

        # 如果文本本身就不长，直接返回
        if len(text) <= max_length:
            return text

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是一个文本摘要助手，请用简洁的中文概括以下文本的核心要点。"},
                {"role": "user", "content": f"请用不超过{max_length}字概括以下内容：\n\n{text}"}
            ],
            max_tokens=max_length * 2,  # 中文大约1字≈1-2token
        )
        return response.choices[0].message.content
    except Exception as e:
        # 降级：如果LLM调用失败，用简单截取
        sentences = re.split(r'[。！？\n]', text)
        summary = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(summary) + len(sentence) + 1 <= max_length:
                summary += sentence + "。"
            else:
                break
        return summary if summary else text[:max_length] + "..."


SUMMARIZE_TOOL = {
    "type": "function",
    "function": {
        "name": "summarize_text",
        "description": "对长文本进行智能摘要，提取关键信息。当用户提供长文本并要求总结、概括、提取要点时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要摘要的文本内容"
                },
                "max_length": {
                    "type": "integer",
                    "description": "摘要最大字数，默认200"
                }
            },
            "required": ["text"]
        }
    }
}


# ============================================================
# 工具4：网页搜索（升级版：Tavily 真实搜索）
# ============================================================
def web_search(query: str) -> str:
    """
    搜索互联网获取实时信息（Tavily API）
    
    和模拟搜索的区别：
    - 模拟搜索：写死几条假数据，只能匹配关键词
    - Tavily搜索：真实搜索互联网，返回实时结果
    """
    if not TAVILY_API_KEY:
        return "⚠️ 未配置 Tavily API Key，请在 config.py 中设置 TAVILY_API_KEY"

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        results = client.search(query, max_results=3)

        formatted = []
        for r in results.get('results', []):
            formatted.append(
                f"标题：{r.get('title', '无标题')}\n"
                f"内容：{r.get('content', '无内容')}\n"
                f"来源：{r.get('url', '无来源')}"
            )
        
        if not formatted:
            return f"未找到关于「{query}」的相关信息"
        
        return "\n\n".join(formatted)
    except ImportError:
        return "⚠️ 未安装 tavily-python，请运行：pip install tavily-python"
    except Exception as e:
        return f"搜索出错：{str(e)}"


WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网获取最新信息。当用户询问实时信息、新闻、天气、最新动态等需要联网获取的内容时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如'今天天气'、'Python最新版本'、'AI最新新闻'"
                }
            },
            "required": ["query"]
        }
    }
}


# ============================================================
# 工具5：文件读写
# ============================================================
def read_file_tool(filepath: str) -> str:
    """读取本地文本文件内容"""
    try:
        # 安全检查：只允许读取当前目录下的文件
        abs_path = os.path.abspath(filepath)
        cwd = os.getcwd()
        if not abs_path.startswith(cwd):
            return "错误：只能读取当前工作目录下的文件"
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        # 限制返回长度
        if len(content) > 3000:
            return content[:3000] + f"\n\n... (文件共 {len(content)} 字符，已截取前3000字)"
        return content
    except FileNotFoundError:
        return f"错误：文件不存在 - {filepath}"
    except Exception as e:
        return f"读取错误：{str(e)}"


def write_file_tool(filepath: str, content: str) -> str:
    """写入内容到本地文件"""
    try:
        abs_path = os.path.abspath(filepath)
        cwd = os.getcwd()
        if not abs_path.startswith(cwd):
            return "错误：只能写入当前工作目录下的文件"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"✅ 已成功写入 {len(content)} 字符到 {filepath}"
    except Exception as e:
        return f"写入错误：{str(e)}"


READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file_tool",
        "description": "读取本地文本文件的内容。当用户让你查看某个文件的内容时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "要读取的文件路径，如 'notes.txt' 或 'data/report.md'"
                }
            },
            "required": ["filepath"]
        }
    }
}

WRITE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_file_tool",
        "description": "将内容写入本地文件。当用户让你保存内容到文件、创建新文件时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "要写入的文件路径，如 'output.txt' 或 'notes/draft.md'"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容"
                }
            },
            "required": ["filepath", "content"]
        }
    }
}


# ============================================================
# 工具注册表：统一管理所有工具
# ============================================================
TOOL_FUNCTIONS = {
    "calculate": calculate,
    "get_current_time": get_current_time,
    "summarize_text": summarize_text,
    "web_search": web_search,
    "read_file_tool": read_file_tool,
    "write_file_tool": write_file_tool,
}

ALL_TOOLS = [
    CALCULATE_TOOL,
    GET_TIME_TOOL,
    SUMMARIZE_TOOL,
    WEB_SEARCH_TOOL,
    READ_FILE_TOOL,
    WRITE_FILE_TOOL,
]
