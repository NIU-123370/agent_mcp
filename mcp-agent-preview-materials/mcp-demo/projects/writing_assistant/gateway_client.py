"""
网关 HTTP 客户端 — 写作项目通过此客户端访问所有 MCP 共享服务。

用法：
    async with GatewayClient("wa-demo-key-001") as gw:
        result = await gw.call_tool("llm-gateway", "chat_completion", {...})
        prompt = await gw.get_prompt("prompt-hub", "writing_assistant", {...})
"""

from __future__ import annotations

import httpx

GATEWAY_URL = "http://127.0.0.1:8000"


class GatewayError(Exception):
    """网关调用失败，携带状态码和错误详情。"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        super().__init__(f"[{status_code}] {detail}")


class GatewayClient:
    def __init__(self, api_key: str, base_url: str = GATEWAY_URL, timeout: float = 60):
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GatewayClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"X-API-Key": self._api_key},
        )
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    @staticmethod
    def _check(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            body = resp.json()
            detail = body.get("error") or body.get("detail") or resp.text
        except Exception:
            detail = resp.text or f"HTTP {resp.status_code}"
        raise GatewayError(resp.status_code, detail)

    async def call_tool(self, service: str, tool: str, arguments: dict | None = None) -> dict:
        """调用指定 MCP 服务的 Tool，返回解析后的 JSON。"""
        resp = await self._client.post(
            "/api/tool/call",
            json={"service": service, "tool": tool, "arguments": arguments or {}},
        )
        self._check(resp)
        return resp.json()

    async def get_prompt(self, service: str, prompt: str, arguments: dict | None = None) -> dict:
        """获取渲染后的 MCP Prompt。"""
        resp = await self._client.post(
            "/api/prompt/get",
            json={"service": service, "prompt": prompt, "arguments": arguments or {}},
        )
        self._check(resp)
        return resp.json()

    async def list_prompts(self, service: str = "prompt-hub") -> dict:
        """列出指定服务的所有 Prompt。"""
        resp = await self._client.get("/api/prompt/list", params={"service": service})
        self._check(resp)
        return resp.json()
