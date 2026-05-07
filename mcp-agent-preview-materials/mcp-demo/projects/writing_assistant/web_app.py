"""
AI 写作助手 — Web 界面入口。

启动前确保网关与各共享服务已运行：
    cd mcp-demo
    uvicorn gateway.main:app --port 8000

启动本 Web 应用：
    cd mcp-demo
    uv run -m uvicorn projects.writing_assistant.web_app:app --port 8501 --reload

浏览器打开 http://127.0.0.1:8501
"""

import uuid
import sys
from pathlib import Path

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("writing-assistant.web")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import WritingAssistantAgent
from gateway_client import GatewayClient

API_KEY = "wa-demo-key-001"
PROJECT_ID = "writing-assistant"
DEFAULT_USER = "demo-user"
ALLOWED_STYLES = frozenset({"正式", "轻松", "学术", "幽默"})

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="InkFlow 写作助手")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

sessions: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class StyleRequest(BaseModel):
    style: str
    session_id: str | None = None


class SessionRequest(BaseModel):
    session_id: str


def _get_or_create_session(session_id: str | None) -> str:
    if session_id and session_id in sessions:
        return session_id
    sid = session_id or f"session-{uuid.uuid4().hex[:8]}"
    sessions[sid] = {"user_id": DEFAULT_USER, "style": "正式"}
    return sid


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/chat")
async def chat(req: ChatRequest):
    sid = _get_or_create_session(req.session_id)
    sess = sessions[sid]

    try:
        async with GatewayClient(API_KEY) as gw:
            agent = WritingAssistantAgent(
                gw,
                user_id=sess["user_id"],
                session_id=sid,
                style=sess["style"],
            )
            reply = await agent.handle_message(req.message)
    except BaseException as e:
        real = e.exceptions[0] if hasattr(e, "exceptions") else e
        logger.error("chat 处理失败: %s", real)
        return JSONResponse(status_code=502, content={
            "error": str(real),
            "session_id": sid,
        })

    return {"reply": reply, "session_id": sid}


@app.post("/api/style")
async def set_style(req: StyleRequest):
    if req.style not in ALLOWED_STYLES:
        return {"error": f"可选文风: {', '.join(sorted(ALLOWED_STYLES))}"}
    sid = _get_or_create_session(req.session_id)
    sessions[sid]["style"] = req.style
    return {"style": req.style, "session_id": sid}


@app.post("/api/clear")
async def clear_memory(req: SessionRequest):
    sid = req.session_id
    if sid not in sessions:
        return {"ok": False, "msg": "会话不存在"}

    async with GatewayClient(API_KEY) as gw:
        await gw.call_tool("memory-service", "clear_memory", {
            "project_id": PROJECT_ID,
            "session_id": sid,
        })
    return {"ok": True, "msg": "会话记忆已清空"}


@app.post("/api/profile")
async def get_profile(req: SessionRequest):
    user_id = sessions.get(req.session_id, {}).get("user_id", DEFAULT_USER)

    async with GatewayClient(API_KEY) as gw:
        data = await gw.call_tool("memory-service", "recall_user_facts", {
            "user_id": user_id,
        })
    return {"facts": data.get("facts", [])}
