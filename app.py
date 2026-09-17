"""
AI Agent 工作台 - 主界面
========================
升级内容：
1. 支持指挥官模式（多Agent协作）
2. 对话持久化（SQLite）
3. 实时展示完整执行过程

运行方式：streamlit run app.py
"""

import streamlit as st
from agent import Agent, CollaborativeAgent
from agents_config import get_agent_names, AGENTS_CONFIG
from memory import ChatMemory

# ---- 页面配置 ----
st.set_page_config(page_title="AI Agent 工作台", page_icon="🤖", layout="wide")

# ---- 初始化持久化 ----
memory = ChatMemory()

if "current_agent" not in st.session_state:
    st.session_state.current_agent = get_agent_names()[0]

# 从数据库加载历史对话
if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {}
    for name in get_agent_names():
        st.session_state.chat_histories[name] = memory.load_history(name)

if "tool_call_logs" not in st.session_state:
    st.session_state.tool_call_logs = {name: [] for name in get_agent_names()}

# ============================================================
# 侧边栏
# ============================================================
st.sidebar.title("🤖 AI Agent 工作台")
st.sidebar.write("---")

agent_names = get_agent_names()
selected_agent = st.sidebar.radio(
    "选择一个 Agent：",
    agent_names,
    index=agent_names.index(st.session_state.current_agent),
)

if selected_agent != st.session_state.current_agent:
    st.session_state.current_agent = selected_agent

# Agent 信息
config = AGENTS_CONFIG[selected_agent]
st.sidebar.write("---")
st.sidebar.write(f"### {selected_agent}")
st.sidebar.write(config["description"])

tools_list = config["tools"]
if tools_list:
    st.sidebar.write(f"**可用工具：** {', '.join(tools_list)}")
else:
    st.sidebar.write("**可用工具：** 无（纯大模型对话/任务调度）")

st.sidebar.write("---")

# 清除对话按钮
if st.sidebar.button("🗑️ 清除当前对话"):
    st.session_state.chat_histories[selected_agent] = []
    st.session_state.tool_call_logs[selected_agent] = []
    memory.clear_history(selected_agent)
    st.rerun()

# 数据库信息
st.sidebar.write("---")
all_agents = memory.get_all_agents()
if all_agents:
    st.sidebar.write(f"💾 **已保存对话的Agent：** {len(all_agents)} 个")
else:
    st.sidebar.write("💾 暂无保存的对话")

# ============================================================
# 主区域
# ============================================================
st.title(f"{config['avatar']} {config['name']}")

# 显示历史消息
chat_history = st.session_state.chat_histories[selected_agent]
tool_logs = st.session_state.tool_call_logs[selected_agent]

for i, log_entry in enumerate(tool_logs):
    if log_entry["type"] == "user":
        with st.chat_message("user"):
            st.write(log_entry["content"])

    elif log_entry["type"] == "commander_plan":
        with st.chat_message("assistant"):
            st.info(f"📋 任务拆解计划：\n{log_entry['plan']}")

    elif log_entry["type"] == "sub_agent_start":
        with st.chat_message("assistant"):
            st.write(f"▶️ 启动子Agent：{log_entry['agent']}")

    elif log_entry["type"] == "steps":
        with st.chat_message("assistant"):
            steps = log_entry["steps"]
            for step in steps:
                if step["type"] == "tool_call":
                    st.info(f"🔧 调用工具：{step['name']}({step['args']})")
                elif step["type"] == "tool_result":
                    st.success(f"✅ 工具结果：{step['name']} → {step['result']}")
            st.write(log_entry["answer"])

    elif log_entry["type"] == "sub_agent_done":
        with st.chat_message("assistant"):
            st.write(f"✅ {log_entry['agent']} 完成：{log_entry['answer'][:100]}...")

    elif log_entry["type"] == "direct_answer":
        with st.chat_message("assistant"):
            st.write(log_entry["content"])


# ============================================================
# 用户输入 + Agent 处理
# ============================================================
question = st.chat_input("输入你的问题...")

if question:
    # 显示用户消息
    with st.chat_message("user"):
        st.write(question)

    # 保存用户消息
    chat_history.append({"role": "user", "content": question})
    memory.save_message(selected_agent, "user", question)

    # 判断是否用指挥官模式
    if selected_agent == "🎯 指挥官":
        # ---- 指挥官协作模式 ----
        collab = CollaborativeAgent()
        steps = []
        final_answer = ""
        plan_text = ""

        with st.chat_message("assistant"):
            status_placeholder = st.empty()
            status_placeholder.markdown("🎯 **指挥官正在分析任务...**")

            for step in collab.run(question):
                if step["type"] == "commander_plan":
                    plan_text = step["plan"]
                    st.info(f"📋 任务拆解计划：\n{plan_text}")
                    status_placeholder.markdown("⚙️ **执行中...**")

                elif step["type"] == "sub_agent_start":
                    st.write(f"▶️ 启动子Agent：{step['agent']}")
                    steps.append(step)

                elif step["type"] == "tool_call":
                    steps.append(step)
                    st.info(f"🔧 调用工具：{step['name']}({step['args']})")

                elif step["type"] == "tool_result":
                    steps.append(step)
                    st.success(f"✅ 工具结果：{step['name']} → {step['result'][:80]}...")

                elif step["type"] == "sub_agent_done":
                    st.write(f"✅ {step['agent']} 完成")
                    steps.append(step)

                elif step["type"] == "answer":
                    final_answer = step["content"]

            status_placeholder.empty()
            st.write(final_answer)

        # 记录日志
        tool_logs.append({"type": "commander_plan", "plan": plan_text})
        for s in steps:
            tool_logs.append(s)
        tool_logs.append({"type": "direct_answer", "content": final_answer})

    else:
        # ---- 单Agent模式 ----
        agent = Agent(selected_agent)
        steps = []
        final_answer = ""

        with st.chat_message("assistant"):
            status_placeholder = st.empty()
            status_placeholder.markdown("🤔 **思考中...**")

            for step in agent.run(question, chat_history=chat_history):
                if step["type"] == "thinking":
                    status_placeholder.markdown("🤔 **思考中...**")

                elif step["type"] == "tool_call":
                    steps.append(step)
                    status_placeholder.info(f"🔧 调用工具：{step['name']}({step['args']})")

                elif step["type"] == "tool_result":
                    steps.append(step)
                    status_placeholder.success(f"✅ 工具结果：{step['name']} → {step['result'][:80]}...")

                elif step["type"] == "answer":
                    final_answer = step["content"]

            status_placeholder.empty()

            if steps:
                for step in steps:
                    if step["type"] == "tool_call":
                        st.info(f"🔧 调用工具：{step['name']}({step['args']})")
                    elif step["type"] == "tool_result":
                        st.success(f"✅ 工具结果：{step['name']} → {step['result']}")
                st.write(final_answer)
                tool_logs.append({"type": "steps", "steps": steps, "answer": final_answer})
            else:
                st.write(final_answer)
                tool_logs.append({"type": "direct_answer", "content": final_answer})

    # 保存助手回复
    chat_history.append({"role": "assistant", "content": final_answer})
    memory.save_message(selected_agent, "assistant", final_answer)
