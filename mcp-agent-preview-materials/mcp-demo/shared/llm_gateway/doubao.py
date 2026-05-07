"""
豆包 API 调用封装 — chat 用 OpenAI SDK，embedding 用 httpx 直调。

- Chat: 走 OpenAI 兼容的 /chat/completions 端点
- Embedding: 走火山引擎专有的 /embeddings/multimodal 端点
  （多模态模型的路径和输入格式与 OpenAI SDK 不兼容，需 httpx 直调）
"""

import logging

import httpx
from openai import AsyncOpenAI, APIError

logger = logging.getLogger("llm-gateway.doubao")


class DoubaoClient:
    """豆包 API 客户端，封装 chat completion 和 embedding 调用。"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """调用豆包对话接口（OpenAI 兼容格式）。

        Returns:
            {"content": str, "usage": {"prompt_tokens": int, ...}}
        """
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APIError as e:
            msg = f"豆包 Chat API 调用失败: {e.message}"
            try:
                logger.error("Chat API error: %s", msg)
            except Exception:
                pass
            raise RuntimeError(msg) from e

        choice = response.choices[0]
        usage = response.usage
        return {
            "content": choice.message.content or "",
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        }

    async def embedding(self, model: str, texts: list[str]) -> dict:
        """调用豆包 Embedding 接口。

        自动判断模型类型：
        - 多模态模型 (含 "vision"): httpx → /embeddings/multimodal
        - 纯文本模型: OpenAI SDK → /embeddings

        Returns:
            {"embeddings": [[float, ...], ...], "dimensions": int}
        """
        if "vision" in model:
            return await self._embedding_multimodal(model, texts)
        return await self._embedding_text(model, texts)

    async def _embedding_text(self, model: str, texts: list[str]) -> dict:
        """标准 OpenAI 兼容的文本 embedding（/embeddings 端点）。"""
        try:
            response = await self.client.embeddings.create(
                model=model,
                input=texts,
            )
        except APIError as e:
            msg = f"豆包 Embedding API 调用失败: {e.message}"
            try:
                logger.error("Embedding API error: %s", msg)
            except Exception:
                pass
            raise RuntimeError(msg) from e

        vectors = [item.embedding for item in response.data]
        return {
            "embeddings": vectors,
            "dimensions": len(vectors[0]) if vectors else 0,
        }

    async def _embedding_multimodal(self, model: str, texts: list[str]) -> dict:
        """多模态 embedding（/embeddings/multimodal 端点）。

        火山引擎多模态 embedding 返回格式: {"data": {"embedding": [...]}}
        每次调用返回一个向量，所以逐条文本分别调用。
        """
        url = f"{self.base_url}/embeddings/multimodal"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        vectors = []
        async with httpx.AsyncClient(timeout=30.0) as http:
            for text in texts:
                payload = {
                    "model": model,
                    "input": [{"type": "text", "text": text}],
                }
                try:
                    resp = await http.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    body = e.response.text
                    logger.error("Multimodal embedding error: %d %s", e.response.status_code, body)
                    raise RuntimeError(f"豆包多模态 Embedding API 调用失败: {body}") from e

                data = resp.json()
                emb_data = data["data"]
                if isinstance(emb_data, list):
                    vectors.append(emb_data[0]["embedding"])
                elif isinstance(emb_data, dict):
                    vectors.append(emb_data["embedding"])
                else:
                    raise RuntimeError(f"豆包多模态 Embedding 返回格式异常: data type={type(emb_data)}")

        return {
            "embeddings": vectors,
            "dimensions": len(vectors[0]) if vectors else 0,
        }
