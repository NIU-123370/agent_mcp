"""
客服 Agent 编排逻辑 — 串联共享服务完成一次完整问答。

流程：
  1. recall_memory     → 获取对话历史
  2. recall_user_facts → 获取用户画像
  3. search_knowledge  → 检索知识库
  4. get_prompt        → 组装 Prompt（含用户画像）
  5. chat_completion   → 生成回答
  6. save_memory       → 保存本轮对话
  7. extract_facts     → 提取用户事实并保存画像
"""

from __future__ import annotations

import json
import logging

from gateway_client import GatewayClient

logger = logging.getLogger("customer-service")

PROJECT_ID = "customer-service"

FACT_EXTRACTION_PROMPT = """\
你是一个信息提取助手。分析用户的最新消息，提取其中包含的个人事实或偏好。

用户事实包括：过敏信息、预算范围、偏好（口味/风格/品牌）、团队规模、行业等。

如果发现用户事实，严格输出 JSON 数组（不要 markdown 代码块）：
[{"key": "allergy", "value": "芒果过敏"}]

key 使用英文小写，常见类别：allergy, budget, preference, team_size, industry, usage_scenario
如果没有发现任何用户事实，输出：[]

只输出 JSON，不要输出任何其他文字。"""


class CustomerServiceAgent:
    def __init__(self, gw: GatewayClient, user_id: str, session_id: str):
        self._gw = gw
        self._user_id = user_id
        self._session_id = session_id

    async def handle_message(self, user_message: str) -> str:
        """处理一条用户消息，返回客服回复。"""

        # 1. 获取对话历史
        history_data = await self._gw.call_tool("memory-service", "recall_memory", {
            "project_id": PROJECT_ID,
            "session_id": self._session_id,
            "last_n": 10,
        })
        history_str = self._format_history(history_data)

        # 2. 获取用户画像
        facts_data = await self._gw.call_tool("memory-service", "recall_user_facts", {
            "user_id": self._user_id,
        })
        profile_str = self._format_profile(facts_data)

        # 3. 检索知识库
        knowledge_data = await self._gw.call_tool("rag-service", "search_knowledge", {
            "query": user_message,
            "project_id": PROJECT_ID,
            "top_k": 3,
        })
        context_str = self._format_context(knowledge_data)

        # 4. 组装 Prompt
        prompt_data = await self._gw.get_prompt("prompt-hub", "customer_service_qa", {
            "context": context_str,
            "history": history_str,
            "question": user_message,
            "user_profile": profile_str,
        })

        # 5. 调用 LLM 生成回答
        llm_result = await self._gw.call_tool("llm-gateway", "chat_completion", {
            "messages": prompt_data["messages"],
            "project_id": PROJECT_ID,
            "model": "auto",
            "temperature": 0.7,
            "max_tokens": 1000,
        })
        reply = llm_result.get("content", "抱歉，生成回答时出错了。")

        # 6. 保存本轮对话到记忆
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
            "content": reply,
        })

        # 7. 提取用户事实（异步，失败不影响主流程）
        try:
            await self._extract_and_save_facts(user_message)
        except Exception as e:
            logger.debug("事实提取跳过: %s", e)

        return reply

    async def _extract_and_save_facts(self, user_message: str):
        """用 LLM 从用户消息中提取个人事实，保存到用户画像。"""
        extract_result = await self._gw.call_tool("llm-gateway", "chat_completion", {
            "messages": [
                {"role": "system", "content": FACT_EXTRACTION_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "project_id": PROJECT_ID,
            "model": "auto",
            "temperature": 0.1,
            "max_tokens": 200,
        })

        raw = extract_result.get("content", "[]").strip()
        # 兼容 LLM 偶尔输出 markdown 代码块
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        facts = json.loads(raw)
        if not isinstance(facts, list):
            return

        for fact in facts:
            key = fact.get("key", "").strip()
            value = fact.get("value", "").strip()
            if key and value:
                await self._gw.call_tool("memory-service", "save_user_fact", {
                    "user_id": self._user_id,
                    "fact_key": key,
                    "fact_value": value,
                    "source_project": PROJECT_ID,
                })
                logger.info("保存用户事实: %s = %s", key, value)

    @staticmethod
    def _format_history(data: dict) -> str:
        messages = data.get("messages", [])
        if not messages:
            return "(无历史对话)"
        lines = []
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "客服"
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
            return "(未找到相关资料)"
        chunks = []
        for i, r in enumerate(results, 1):
            text = r.get("text", r.get("document", ""))
            chunks.append(f"[{i}] {text}")
        return "\n\n".join(chunks)
