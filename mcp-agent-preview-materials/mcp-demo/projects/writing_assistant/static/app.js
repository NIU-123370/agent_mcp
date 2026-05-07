let sessionId = null;
const msgBox  = document.getElementById('messages');
const input   = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const styleSelect = document.getElementById('styleSelect');

/* ---- 快捷键 ---- */
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

/* ---- 文风切换 ---- */
styleSelect.addEventListener('change', async () => {
  const style = styleSelect.value;
  try {
    const res = await fetch('/api/style', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ style, session_id: sessionId }),
    });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    sessionId = data.session_id;
    addSystemMsg('文风已切换为: ' + style);
  } catch (e) {
    alert('切换文风失败: ' + e);
  }
});

/* ---- 工具函数 ---- */
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function scrollDown() {
  requestAnimationFrame(() => { msgBox.scrollTop = msgBox.scrollHeight; });
}

function setLock(locked) {
  sendBtn.disabled = locked;
  input.disabled = locked;
}

function addMsg(role, html) {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + role;

  const label = document.createElement('div');
  label.className = 'label';
  label.textContent = role === 'user' ? '你' : '助手';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = html;

  wrap.appendChild(label);
  wrap.appendChild(bubble);
  msgBox.appendChild(wrap);
  scrollDown();
  return wrap;
}

function addSystemMsg(text) {
  const el = document.createElement('div');
  el.className = 'system-msg';
  el.textContent = text;
  msgBox.appendChild(el);
  scrollDown();
}

/* ---- 发送消息 ---- */
async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';

  addMsg('user', esc(text));

  const typing = document.createElement('div');
  typing.className = 'msg bot typing';
  typing.innerHTML = '<div class="label">助手</div><div class="bubble">创作中...</div>';
  msgBox.appendChild(typing);
  scrollDown();
  setLock(true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
    typing.querySelector('.bubble').innerHTML =
      '<span style="color:#ef4444">出错了: ' + esc(String(e)) + '</span>';
  }

  setLock(false);
  scrollDown();
  input.focus();
}

/* ---- 清空记忆 ---- */
async function clearMemory() {
  if (!sessionId) { alert('还没有开始对话'); return; }
  try {
    const res = await fetch('/api/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    addSystemMsg(data.msg);
  } catch (e) {
    alert('清空失败: ' + e);
  }
}

/* ---- 用户画像 ---- */
async function showProfile() {
  if (!sessionId) { alert('还没有开始对话'); return; }
  try {
    const res = await fetch('/api/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    const facts = data.facts || [];

    let html = '<h4>用户画像</h4>';
    if (facts.length === 0) {
      html += '<div>暂无用户画像信息</div>';
    } else {
      html += '<ul>' + facts.map(f =>
        '<li><b>' + esc(f.key) + '</b>: ' + esc(f.value) +
        (f.source ? ' <i>(来源: ' + esc(f.source) + ')</i>' : '') +
        '</li>'
      ).join('') + '</ul>';
    }

    const el = document.createElement('div');
    el.className = 'profile-panel';
    el.innerHTML = html;
    msgBox.appendChild(el);
    scrollDown();
  } catch (e) {
    alert('获取画像失败: ' + e);
  }
}

/* ---- 新建会话 ---- */
function newSession() {
  sessionId = null;
  msgBox.innerHTML = '';
  addMsg('bot', '你好！我是 InkFlow 写作助手。请告诉我写作主题或修改要求，我可以帮你创作和润色文章。');
  document.getElementById('sessionInfo').textContent = '会话: 未开始';
  input.focus();
}

input.focus();
