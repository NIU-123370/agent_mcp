"""
LLM 网关 MCP Server — 统一的大模型调用入口。

暴露 Tool：
  - chat_completion : 对话补全（自动路由到配置的模型）
  - embedding       : 文本向量化
  - list_models     : 列出可用模型

启动：uv run shared/llm_gateway/server.py
端口：9001
传输：Streamable HTTP → http://127.0.0.1:9001/mcp
"""

import os
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from doubao import DoubaoClient
from router import ModelRouter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("llm-gateway")

# ── 初始化 ──────────────────────────────────────────────

server = FastMCP("llm-gateway", host="127.0.0.1", port=9001)

doubao = DoubaoClient(
    api_key=os.environ["ARK_API_KEY"],
    base_url=os.environ["ARK_BASE_URL"],
)

router = ModelRouter()

CHAT_ENDPOINT = os.environ["ARK_CHAT_MODEL"]
EMBEDDING_ENDPOINT = os.environ["ARK_EMBEDDING_MODEL"]


# ── Tools ───────────────────────────────────────────────

@server.tool()
async def chat_completion(
    messages: list[dict],
    project_id: str,
    model: str = "auto",
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> dict:
    """统一的 LLM 对话接口，自动路由到配置的模型。

    Args:
        messages: 对话消息列表，格式 [{"role": "user", "content": "..."}]
        project_id: 调用方项目标识（用于日志和配额追踪）
        model: 模型选择 — "auto" 使用默认模型，或指定 "doubao-pro" / "doubao-lite"
        temperature: 生成温度，0-1 之间
        max_tokens: 最大生成 token 数
    """
    model_name = router.resolve(model)
    model_cfg = router.get_model_config(model_name)
    effective_max_tokens = min(max_tokens, model_cfg.get("max_tokens", max_tokens))

    logger.info(
        "chat_completion | project=%s model=%s max_tokens=%d",
        project_id, model_name, effective_max_tokens,
    )

    result = await doubao.chat_completion(
        model=CHAT_ENDPOINT,
        messages=messages,
        temperature=temperature,
        max_tokens=effective_max_tokens,
    )
    result["model"] = model_name
    result["project_id"] = project_id
    return result


@server.tool()
async def embedding(
    texts: list[str],
    project_id: str,
) -> dict:
    """统一的文本向量化接口。

    Args:
        texts: 要向量化的文本列表
        project_id: 调用方项目标识
    """
    logger.info("embedding | project=%s texts=%d", project_id, len(texts))

    result = await doubao.embedding(
        model=EMBEDDING_ENDPOINT,
        texts=texts,
    )
    result["project_id"] = project_id
    return result


@server.tool()
async def list_models() -> dict:
    """列出所有可用的 LLM 模型及其配置信息。"""
    return {"models": router.list_models()}


# ── 入口 ────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("LLM 网关 MCP Server 启动中...")
    logger.info("  Chat Endpoint:      %s", CHAT_ENDPOINT)
    logger.info("  Embedding Endpoint: %s", EMBEDDING_ENDPOINT)
    logger.info("  默认模型:           %s", router.default_model)
    server.run(transport="streamable-http")
