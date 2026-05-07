"""
HTTP 路由 — 将 REST 请求转发到 MCP 共享服务。

端点：
  POST /api/tool/call     — 调用 MCP Tool
  POST /api/prompt/get    — 获取渲染后的 MCP Prompt
  GET  /api/prompt/list   — 列出可用 Prompt
  GET  /api/tool/list     — 列出可用 Tool
  GET  /api/health        — 健康检查（无需认证）
  GET  /api/quota/usage   — 查看当前项目的配额使用情况
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .mcp_client_manager import MCPCallError

logger = logging.getLogger("gateway.router")

router = APIRouter(prefix="/api")


# ── 请求体模型 ──────────────────────────────────────────


class ToolCallRequest(BaseModel):
    service: str
    tool: str
    arguments: dict = {}


class PromptGetRequest(BaseModel):
    service: str
    prompt: str
    arguments: dict = {}


# ── Tool 端点 ───────────────────────────────────────────


@router.post("/tool/call")
async def call_tool(request: Request, body: ToolCallRequest):
    """调用指定 MCP 服务的 Tool。"""
    trace_id = getattr(request.state, "trace_id", "?")
    project_id = getattr(request.state, "project_id", "?")
    mcp = request.app.state.mcp

    logger.info(
        "[%s] tool/call | project=%s service=%s tool=%s",
        trace_id, project_id, body.service, body.tool,
    )

    try:
        result = await mcp.call_tool(body.service, body.tool, body.arguments)
    except MCPCallError as e:
        return JSONResponse(status_code=502, content={"error": str(e), "trace_id": trace_id})
    except BaseException as e:
        real = e.exceptions[0] if hasattr(e, "exceptions") else e
        logger.error("[%s] MCP 调用异常: %s", trace_id, real)
        return JSONResponse(status_code=502, content={
            "error": f"MCP 服务调用失败: {real}",
            "hint": f"请确认 {body.service} 服务已启动",
            "trace_id": trace_id,
        })

    if body.tool == "chat_completion" and isinstance(result, dict) and "usage" in result:
        total_tokens = result["usage"].get("total_tokens", 0)
        if total_tokens > 0:
            request.app.state.quota.add(project_id, total_tokens)

    return result


@router.post("/tool/list")
async def list_tools_for_service(request: Request, body: dict):
    """列出指定 MCP 服务的所有 Tool。"""
    service = body.get("service", "")
    mcp = request.app.state.mcp
    trace_id = getattr(request.state, "trace_id", "?")

    try:
        return await mcp.list_tools(service)
    except MCPCallError as e:
        return JSONResponse(status_code=502, content={"error": str(e), "trace_id": trace_id})
    except Exception as e:
        return JSONResponse(status_code=502, content={
            "error": f"MCP 服务调用失败: {e}",
            "hint": f"请确认 {service} 服务已启动",
            "trace_id": trace_id,
        })


# ── Prompt 端点 ─────────────────────────────────────────


@router.post("/prompt/get")
async def get_prompt(request: Request, body: PromptGetRequest):
    """获取渲染后的 MCP Prompt（填入参数后的完整提示词）。"""
    trace_id = getattr(request.state, "trace_id", "?")
    mcp = request.app.state.mcp

    logger.info(
        "[%s] prompt/get | service=%s prompt=%s",
        trace_id, body.service, body.prompt,
    )

    try:
        return await mcp.get_prompt(body.service, body.prompt, body.arguments)
    except MCPCallError as e:
        return JSONResponse(status_code=502, content={"error": str(e), "trace_id": trace_id})
    except Exception as e:
        logger.exception("[%s] MCP 调用异常", trace_id)
        return JSONResponse(status_code=502, content={
            "error": f"MCP 服务调用失败: {e}",
            "hint": f"请确认 {body.service} 服务已启动",
            "trace_id": trace_id,
        })


@router.get("/prompt/list")
async def list_prompts(request: Request, service: str = "prompt-hub"):
    """列出指定服务的所有可用 Prompt。"""
    mcp = request.app.state.mcp
    trace_id = getattr(request.state, "trace_id", "?")

    try:
        return await mcp.list_prompts(service)
    except MCPCallError as e:
        return JSONResponse(status_code=502, content={"error": str(e), "trace_id": trace_id})
    except Exception as e:
        return JSONResponse(status_code=502, content={
            "error": f"MCP 服务调用失败: {e}",
            "hint": f"请确认 {service} 服务已启动",
            "trace_id": trace_id,
        })


# ── 治理端点 ────────────────────────────────────────────


@router.get("/health")
async def health(request: Request):
    """健康检查 + 各服务连通性检测。"""
    mcp = request.app.state.mcp
    services = {}
    for name in mcp.service_names:
        services[name] = await mcp.check_health(name)
    all_ok = all(s["status"] == "ok" for s in services.values())
    return {"status": "ok" if all_ok else "degraded", "services": services}


@router.get("/quota/usage")
async def quota_usage(request: Request):
    """查看当前项目的 Token 配额使用情况。"""
    project_id = getattr(request.state, "project_id", None)
    if not project_id or project_id == "__anonymous__":
        return JSONResponse(status_code=401, content={"error": "需要认证"})
    return request.app.state.quota.get_usage(project_id)
