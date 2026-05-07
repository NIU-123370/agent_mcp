"""
写作 Agent 编排逻辑 — 串联共享服务完成一次写作任务。

流程：
  1. recall_memory     → 获取本轮会话中的写作对话（多轮润色/续写）
  2. recall_user_facts → 获取用户画像（风格偏好等）
  3. search_knowledge  → 检索写作素材库
  4. get_prompt        → writing_assistant（含用户偏好与历史）
  5. chat_completion   → 生成正文
  6. save_memory       → 保存本轮用户指令与生成结果
"""

from __future__ import annotations

from gateway_client import GatewayClient

PROJECT_ID = "writing-assistant"


class WritingAssistantAgent:
    def __init__(self, gw: GatewayClient, user_id: str, session_id: str, style: str = "正式"):
        self._gw = gw
        self._user_id = user_id
        self._session_id = session_id
        self.style = style

    async def handle_message(self, user_message: str) -> str:
        """处理一条用户输入（主题、润色指令等），返回模型生成的文本。"""

        history_data = await self._gw.call_tool("memory-service", "recall_memory", {
            "project_id": PROJECT_ID,
            "session_id": self._session_id,
            "last_n": 10,
        })
        history_str = self._format_history(history_data)

        facts_data = await self._gw.call_tool("memory-service", "recall_user_facts", {
            "user_id": self._user_id,
        })
        profile_str = self._format_profile(facts_data)

        knowledge_data = await self._gw.call_tool("rag-service", "search_knowledge", {
            "query": user_message,
            "project_id": PROJECT_ID,
            "top_k": 5,
        })
        references_str = self._format_context(knowledge_data)

        prompt_data = await self._gw.get_prompt("prompt-hub", "writing_assistant", {
            "topic": user_message,
            "references": references_str,
            "style": self.style,
            "user_profile": profile_str,
            "history": history_str,
        })

        llm_result = await self._gw.call_tool("llm-gateway", "chat_completion", {
            "messages": prompt_data["messages"],
            "project_id": PROJECT_ID,
            "model": "auto",
            "temperature": 0.75,
            "max_tokens": 2500,
        })
        text = llm_result.get("content", "抱歉，生成内容时出错了。")

        await self._gw.call_tool("memory-service", "save_memory", {
            "project_id": PROJECT_ID,
            "session_id": self._session_id,
            "role": "user",
            "content": user_message,
        })
        await self._gw.call_tool("memory-service", "save_memory", {
            "project_id": PROJECT_ID,
            "session_id": self._session_id,
            "role": "assistant",
            "content": text,
        })

        return text

    @staticmethod
    def _format_history(data: dict) -> str:
        messages = data.get("messages", [])
        if not messages:
            return "(无历史对话)"
        lines = []
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)

    @staticmethod
    def _format_profile(data: dict) -> str:
        facts = data.get("facts", [])
        if not facts:
            return "(无用户画像)"
        lines = [f"- {f['key']}: {f['value']}" for f in facts]
        return "\n".join(lines)

    @staticmethod
    def _format_context(data: dict) -> str:
        results = data.get("results", [])
        if not results:
            return "(未检索到素材，将仅根据主题与对话生成)"
        chunks = []
        for i, r in enumerate(results, 1):
            t = r.get("text", r.get("document", ""))
            chunks.append(f"[{i}] {t}")
        return "\n\n".join(chunks)
