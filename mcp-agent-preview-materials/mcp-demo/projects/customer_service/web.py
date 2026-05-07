"""
智能客服 — Web 界面入口。

通过浏览器与客服 Agent 交互，方便测试全部功能。

启动前确保网关和各共享服务已运行：
    cd mcp-demo
    uvicorn gateway.main:app --port 8000

然后启动本 Web 界面：
    cd mcp-demo
    uv run -m uvicorn projects.customer_service.web:app --port 8501 --reload

浏览器打开 http://127.0.0.1:8501
"""

import uuid
import sys
from pathlib import Path

import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("customer-service.web")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import CustomerServiceAgent
from gateway_client import GatewayClient

API_KEY = "cs-demo-key-001"
PROJECT_ID = "customer-service"
DEFAULT_USER = "demo-user"

app = FastAPI(title="SmartAssist Pro — 智能客服")

sessions: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ClearRequest(BaseModel):
    session_id: str


class ProfileRequest(BaseModel):
    session_id: str


def _get_or_create_session(session_id: str | None) -> str:
    if session_id and session_id in sessions:
        return session_id
    sid = session_id or f"session-{uuid.uuid4().hex[:8]}"
    sessions[sid] = {"user_id": DEFAULT_USER}
    return sid


@app.post("/api/chat")
async def chat(req: ChatRequest):
    sid = _get_or_create_session(req.session_id)
    user_id = sessions[sid]["user_id"]

    try:
        async with GatewayClient(API_KEY) as gw:
            agent = CustomerServiceAgent(gw, user_id=user_id, session_id=sid)
            reply = await agent.handle_message(req.message)
    except BaseException as e:
        real = e.exceptions[0] if hasattr(e, "exceptions") else e
        logger.error("chat 处理失败: %s", real)
        return JSONResponse(status_code=502, content={
            "error": str(real),
            "session_id": sid,
        })

    return {"reply": reply, "session_id": sid}


@app.post("/api/clear")
async def clear_memory(req: ClearRequest):
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
async def get_profile(req: ProfileRequest):
    sid = req.session_id
    user_id = sessions.get(sid, {}).get("user_id", DEFAULT_USER)

    async with GatewayClient(API_KEY) as gw:
        data = await gw.call_tool("memory-service", "recall_user_facts", {
            "user_id": user_id,
        })
    return {"facts": data.get("facts", [])}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


HTML_PAGE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SmartAssist Pro — 智能客服</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #f0f2f5;
    --card: #ffffff;
    --primary: #4f46e5;
    --primary-hover: #4338ca;
    --user-bubble: #4f46e5;
    --bot-bubble: #ffffff;
    --text: #1f2937;
    --text-light: #6b7280;
    --border: #e5e7eb;
    --shadow: 0 1px 3px rgba(0,0,0,.08);
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
  }

  .app {
    width: 460px;
    max-width: 100vw;
    height: 94vh;
    background: var(--card);
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,.12);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ---- header ---- */
  .header {
    padding: 16px 20px;
    background: var(--primary);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  .header h1 { font-size: 16px; font-weight: 600; }
  .header .actions { display: flex; gap: 8px; }
  .header button {
    background: rgba(255,255,255,.18);
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    cursor: pointer;
    transition: background .2s;
  }
  .header button:hover { background: rgba(255,255,255,.3); }

  /* ---- session bar ---- */
  .session-bar {
    padding: 8px 20px;
    background: #f9fafb;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    color: var(--text-light);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  .session-bar button {
    background: none; border: 1px solid var(--border); border-radius: 4px;
    padding: 2px 8px; font-size: 11px; cursor: pointer; color: var(--text-light);
  }
  .session-bar button:hover { background: var(--border); }

  /* ---- messages ---- */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 2px; }

  .msg { max-width: 82%; line-height: 1.55; font-size: 14px; }
  .msg .bubble {
    padding: 10px 14px;
    border-radius: 14px;
    box-shadow: var(--shadow);
    white-space: pre-wrap;
    word-break: break-word;
  }
  .msg.user { align-self: flex-end; }
  .msg.user .bubble { background: var(--user-bubble); color: #fff; border-bottom-right-radius: 4px; }
  .msg.bot  { align-self: flex-start; }
  .msg.bot  .bubble { background: var(--bot-bubble); border: 1px solid var(--border); border-bottom-left-radius: 4px; }

  .msg .label { font-size: 11px; color: var(--text-light); margin-bottom: 3px; padding: 0 4px; }
  .msg.user .label { text-align: right; }

  .typing .bubble { color: var(--text-light); font-style: italic; }

  /* system toast */
  .system-msg {
    align-self: center;
    background: #fef3c7;
    color: #92400e;
    font-size: 12px;
    padding: 4px 14px;
    border-radius: 12px;
  }

  /* profile panel */
  .profile-panel {
    align-self: center;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 10px;
    padding: 10px 16px;
    font-size: 13px;
    max-width: 90%;
  }
  .profile-panel h4 { font-size: 13px; margin-bottom: 4px; color: #166534; }
  .profile-panel ul { margin: 0; padding-left: 18px; }
  .profile-panel li { margin: 2px 0; }

  /* ---- input area ---- */
  .input-area {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    display: flex;
    gap: 8px;
    flex-shrink: 0;
    background: #fff;
  }
  .input-area textarea {
    flex: 1;
    resize: none;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 14px;
    font-family: inherit;
    outline: none;
    transition: border-color .2s;
    min-height: 42px;
    max-height: 120px;
  }
  .input-area textarea:focus { border-color: var(--primary); }
  .input-area button {
    background: var(--primary);
    color: #fff;
    border: none;
    border-radius: 10px;
    padding: 0 20px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background .2s;
    flex-shrink: 0;
  }
  .input-area button:hover { background: var(--primary-hover); }
  .input-area button:disabled { opacity: .5; cursor: not-allowed; }
</style>
</head>
<body>

<div class="app">
  <div class="header">
    <h1>SmartAssist Pro — 智能客服</h1>
    <div class="actions">
      <button onclick="clearMemory()">清空记忆</button>
      <button onclick="showProfile()">用户画像</button>
    </div>
  </div>
  <div class="session-bar">
    <span id="sessionInfo">会话: 未开始</span>
    <button onclick="newSession()">新建会话</button>
  </div>
  <div class="messages" id="messages">
    <div class="msg bot">
      <div class="label">客服</div>
      <div class="bubble">你好！我是 SmartAssist Pro 智能客服，有什么可以帮你的？</div>
    </div>
  </div>
  <div class="input-area">
    <textarea id="input" placeholder="输入消息… (Enter 发送，Shift+Enter 换行)" rows="1"></textarea>
    <button id="sendBtn" onclick="send()">发送</button>
  </div>
</div>

<script>
let sessionId = null;
const msgBox = document.getElementById('messages');
const input  = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

function scrollDown() {
  requestAnimationFrame(() => msgBox.scrollTop = msgBox.scrollHeight);
}

function addMsg(role, html, cls) {
  const wrap = document.createElement('div');
  if (cls) { wrap.className = cls; }
  else {
    wrap.className = 'msg ' + role;
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = role === 'user' ? '你' : '客服';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.innerHTML = html;
    wrap.appendChild(label);
    wrap.appendChild(bubble);
  }
  if (cls) wrap.innerHTML = html;
  msgBox.appendChild(wrap);
  scrollDown();
  return wrap;
}

function setLock(locked) {
  sendBtn.disabled = locked;
  input.disabled = locked;
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';

  addMsg('user', esc(text));
  const typing = addMsg('bot', '', '');
  typing.className = 'msg bot typing';
  typing.innerHTML = '<div class="label">客服</div><div class="bubble">思考中...</div>';
  scrollDown();
  setLock(true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message: text, session_id: sessionId }),
    });
    let data;
    try { data = await res.json(); } catch (_) {
      throw new Error('服务端返回了非 JSON 响应 (HTTP ' + res.status + ')');
    }
    if (!res.ok) throw new Error(data.error || data.detail || '请求失败');

    sessionId = data.session_id;
    document.getElementById('sessionInfo').textContent = '会话: ' + sessionId;
    typing.classList.remove('typing');
    typing.querySelector('.bubble').innerHTML = esc(data.reply);
  } catch (e) {
    typing.classList.remove('typing');
    typing.querySelector('.bubble').innerHTML = '<span style="color:#ef4444">出错了: ' + esc(String(e)) + '</span>';
  }
  setLock(false);
  scrollDown();
  input.focus();
}

async function clearMemory() {
  if (!sessionId) { alert('还没有开始对话'); return; }
  try {
    const res = await fetch('/api/clear', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    const el = document.createElement('div');
    el.className = 'system-msg';
    el.textContent = data.msg;
    msgBox.appendChild(el);
    scrollDown();
  } catch(e) { alert('清空失败: ' + e); }
}

async function showProfile() {
  if (!sessionId) { alert('还没有开始对话'); return; }
  try {
    const res = await fetch('/api/profile', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    const facts = data.facts || [];
    let html = '<h4>用户画像</h4>';
    if (facts.length === 0) {
      html += '<div>暂无用户画像信息</div>';
    } else {
      html += '<ul>' + facts.map(f => '<li><b>' + esc(f.key) + '</b>: ' + esc(f.value) + (f.source ? ' <i>(来源: ' + esc(f.source) + ')</i>' : '') + '</li>').join('') + '</ul>';
    }
    const el = document.createElement('div');
    el.className = 'profile-panel';
    el.innerHTML = html;
    msgBox.appendChild(el);
    scrollDown();
  } catch(e) { alert('获取画像失败: ' + e); }
}

function newSession() {
  sessionId = null;
  msgBox.innerHTML = '';
  addMsg('bot', '你好！我是 SmartAssist Pro 智能客服，有什么可以帮你的？');
  document.getElementById('sessionInfo').textContent = '会话: 未开始';
  input.focus();
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

input.focus();
</script>
</body>
</html>
"""
