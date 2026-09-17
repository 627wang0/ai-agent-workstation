"""
Agent 核心层（Agent Core）
=========================
实现 Function Calling 循环

升级内容：
1. 从 config 读取 API 配置（不再硬编码）
2. 支持指挥官模式（多Agent协作）
"""

import json
from openai import OpenAI
from tools import TOOL_FUNCTIONS, ALL_TOOLS
from agents_config import AGENTS_CONFIG
from config import API_KEY, BASE_URL, MODEL_NAME, MAX_ROUNDS, MAX_HISTORY


class Agent:
    """
    AI Agent 核心类

    每个 Agent 有自己的：
    - 系统提示词（决定它"是谁"、"怎么做事"）
    - 可用工具列表（决定它"能做什么"）

    核心方法 run() 实现了 Function Calling 循环。
    它是一个生成器（generator），每执行一步就 yield 一个事件，
    前端可以实时展示"思考 → 调用工具 → 获得结果 → 再思考 → 最终回答"的全过程。
    """

    def __init__(self, agent_name: str):
        """
        初始化 Agent

        参数：agent_name - Agent 的完整名称，如 "🧮 计算助手"
        """
        config = AGENTS_CONFIG.get(agent_name)
        if not config:
            raise ValueError(f"未知的 Agent: {agent_name}，可选: {list(AGENTS_CONFIG.keys())}")

        self.name = config["name"]
        self.avatar = config["avatar"]
        self.description = config["description"]
        self.system_prompt = config["system_prompt"]

        # 根据配置筛选可用工具
        allowed_tool_names = config["tools"]
        self.tools = [t for t in ALL_TOOLS if t["function"]["name"] in allowed_tool_names]

        # 初始化大模型客户端（从config读取）
        self.client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
        )

    def run(self, user_message: str, chat_history: list = None):
        """
        核心方法：Function Calling 循环

        参数：
            user_message - 用户本次输入的文字
            chat_history - 历史消息列表

        产出（yield）：
            {"type": "thinking"}
            {"type": "tool_call", "name": str, "args": dict}
            {"type": "tool_result", "name": str, "result": str}
            {"type": "answer", "content": str}
        """
        # 构建消息列表
        messages = [{"role": "system", "content": self.system_prompt}]

        if chat_history:
            for msg in chat_history[-MAX_HISTORY:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": user_message})

        # Function Calling 循环
        for round_num in range(MAX_ROUNDS):
            yield {"type": "thinking"}

            # 调用大模型
            if self.tools:
                response = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                )
            else:
                response = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                )

            assistant_message = response.choices[0].message

            if assistant_message.tool_calls:
                # 有工具调用
                assistant_msg_dict = {
                    "role": "assistant",
                    "content": assistant_message.content or "",
                }
                assistant_msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_message.tool_calls
                ]
                messages.append(assistant_msg_dict)

                for tool_call in assistant_message.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}

                    yield {"type": "tool_call", "name": func_name, "args": func_args}

                    if func_name in TOOL_FUNCTIONS:
                        func = TOOL_FUNCTIONS[func_name]
                        try:
                            result = func(**func_args)
                        except Exception as e:
                            result = f"工具执行出错：{str(e)}"
                    else:
                        result = f"错误：未知工具 {func_name}"

                    yield {"type": "tool_result", "name": func_name, "result": str(result)}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(result),
                    })

                continue

            else:
                # 最终回答
                answer = assistant_message.content or "（Agent 未返回内容）"
                yield {"type": "answer", "content": answer}
                return

        # 超过最大轮数
        yield {"type": "answer", "content": "（Agent 经过多轮工具调用后未能给出最终回答，请重试）"}


# ============================================================
# 多Agent协作：指挥官模式
# ============================================================

class CollaborativeAgent:
    """
    协作Agent：能调用其他Agent的指挥官

    工作流程：
    1. 用户提需求
    2. 指挥官拆解任务，输出执行计划
    3. 按计划依次调用子Agent
    4. 汇总结果返回给用户
    """

    def __init__(self):
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        self.commander_config = AGENTS_CONFIG["🎯 指挥官"].copy()
        # 动态注入当前日期，防止大模型编造日期
        import datetime
        today = datetime.datetime.now().strftime("%Y年%m月%d日")
        self.commander_config["system_prompt"] = self.commander_config["system_prompt"].format(current_date=today)
        self._sub_agents = {}  # 缓存子Agent实例

    def _get_sub_agent(self, agent_name: str) -> Agent:
        """获取子Agent实例（带缓存）"""
        if agent_name not in self._sub_agents:
            self._sub_agents[agent_name] = Agent(agent_name)
        return self._sub_agents[agent_name]

    def run(self, user_message: str):
        """
        协作执行流程

        yield 事件：
            {"type": "commander_plan", "plan": str}     - 指挥官的任务拆解计划
            {"type": "sub_agent_start", "agent": str}   - 子Agent开始执行
            {"type": "tool_call", "name": str, "args": dict}
            {"type": "tool_result", "name": str, "result": str}
            {"type": "sub_agent_done", "agent": str, "answer": str} - 子Agent完成
            {"type": "answer", "content": str}           - 最终汇总回答
        """
        # Step 1: 指挥官拆解任务
        messages = [
            {"role": "system", "content": self.commander_config["system_prompt"]},
            {"role": "user", "content": user_message}
        ]

        response = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
        )

        plan = response.choices[0].message.content
        yield {"type": "commander_plan", "plan": plan}

        # Step 2: 检查是否需要拆解（如果指挥官认为简单问题直接回答）
        has_steps = any(name in plan for name in ["🧮", "🌐", "📝", "✍️"])

        if not has_steps:
            # 简单问题，指挥官直接回答
            yield {"type": "answer", "content": plan}
            return

        # Step 3: 按计划调用子Agent
        agent_map = {
            "🧮": "🧮 计算助手",
            "🌐": "🌐 联网助手",
            "📝": "📝 摘要助手",
            "✍️": "✍️ 创作助手",
        }

        results = []
        lines = plan.split("\n")

        for line in lines:
            # 找包含Agent emoji的行，提取任务
            for emoji, agent_name in agent_map.items():
                if emoji in line:
                    # 提取任务描述（Agent名后面的部分）
                    task = line.split(emoji, 1)[-1]
                    # 去掉 "计算助手" 等名称和横线
                    for suffix in ["计算助手", "联网助手", "摘要助手", "创作助手", "-", "—"]:
                        task = task.replace(suffix, "", 1)
                    task = task.strip().strip("：:").strip()

                    if not task:
                        task = user_message  # fallback

                    yield {"type": "sub_agent_start", "agent": agent_name}

                    # 调用子Agent
                    sub_agent = self._get_sub_agent(agent_name)
                    sub_answer = ""
                    for step in sub_agent.run(task):
                        if step["type"] == "tool_call":
                            yield step
                        elif step["type"] == "tool_result":
                            yield step
                        elif step["type"] == "answer":
                            sub_answer = step["content"]

                    results.append(f"[{agent_name}] {sub_answer}")
                    yield {"type": "sub_agent_done", "agent": agent_name, "answer": sub_answer}
                    break

        # Step 4: 汇总结果
        summary_prompt = f"""用户原始需求：{user_message}

各Agent执行结果：
{chr(10).join(results)}

请综合以上结果，给用户一个完整、清晰的回答。"""

        summary_response = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": summary_prompt}],
        )
        final_answer = summary_response.choices[0].message.content
        yield {"type": "answer", "content": final_answer}


# ============================================================
# 快速测试
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🧪 测试1：计算助手 → 数学计算")
    print("=" * 60)

    agent = Agent("🧮 计算助手")
    for step in agent.run("帮我算一下 123 * 456 + 789 等于多少"):
        if step["type"] == "thinking":
            print("  🤔 思考中...")
        elif step["type"] == "tool_call":
            print(f"  🔧 调用工具: {step['name']}({step['args']})")
        elif step["type"] == "tool_result":
            print(f"  ✅ 工具结果: {step['name']} → {step['result']}")
        elif step["type"] == "answer":
            print(f"\n  💬 最终回答:\n  {step['content']}")

    print("\n")
    print("=" * 60)
    print("🧪 测试2：指挥官 → 多Agent协作")
    print("=" * 60)

    collab = CollaborativeAgent()
    for step in collab.run("帮我搜索一下今天的科技新闻，然后算一下 256*16"):
        if step["type"] == "commander_plan":
            print(f"  📋 任务计划:\n  {step['plan']}")
        elif step["type"] == "sub_agent_start":
            print(f"  ▶️ 启动: {step['agent']}")
        elif step["type"] == "tool_call":
            print(f"  🔧 调用工具: {step['name']}({step['args']})")
        elif step["type"] == "tool_result":
            print(f"  ✅ 工具结果: {step['name']} → {step['result'][:50]}...")
        elif step["type"] == "sub_agent_done":
            print(f"  ✅ 完成: {step['agent']}")
        elif step["type"] == "answer":
            print(f"\n  💬 最终回答:\n  {step['content']}")
