# HTTP 网关测试指南

测试脚本覆盖 10 个场景：健康检查、认证失败、Tool 调用、Prompt 获取、配额查询、项目隔离、Trace ID。

---

## 启动服务

网关测试需要至少启动 **Prompt 中心** 和 **记忆服务**（测试脚本会调用这两个服务的 Tool），然后启动网关：

```bash
cd mcp-demo

# 终端 1 — Prompt 中心
uv run shared/prompt_hub/server.py

# 终端 2 — 记忆服务
uv run shared/memory_service/server.py

# 终端 3 — 网关
uv run uvicorn gateway.main:app --port 8000
```

或者一键启动所有服务：

```bash
uv run scripts/start_all.py
```

---

## 运行测试

```bash
uv run scripts/test_gateway.py
```

---

## 预期输出

```
=======================================================
TEST 1: GET /api/health (无需认证)
=======================================================
  status: 200
  overall: ok
  - llm-gateway: ok
  - rag-service: ok
  - memory-service: ok
  - prompt-hub: ok

=======================================================
TEST 2: 认证失败 (无 API Key)
=======================================================
  status: 401
  body: {'error': '无效的 API Key', 'hint': '请在请求头中设置 X-API-Key'}
  -> PASS: 无 Key 返回 401

=======================================================
TEST 3: 认证失败 (错误 API Key)
=======================================================
  status: 401
  -> PASS: 错误 Key 返回 401

=======================================================
TEST 4: POST /api/tool/call (list_prompt_templates)
=======================================================
  status: 200
  template count: 2
  - customer_service_qa
  - writing_assistant
  -> PASS: Tool 调用成功

=======================================================
TEST 5: POST /api/prompt/get (customer_service_qa)
=======================================================
  status: 200
  role: user
  preview: 你是一个专业的客服助手。请严格根据提供的参考资料回答用户问题。...
  -> PASS: 参数正确渲染到 Prompt

=======================================================
TEST 6: GET /api/prompt/list
=======================================================
  status: 200
  prompt count: 2
  - customer_service_qa: args=['context', 'history', 'question', 'user_profile']
  - writing_assistant: args=['topic', 'references', 'style', 'user_profile']
  -> PASS: Prompt 列表获取成功

=======================================================
TEST 7: POST /api/tool/call (save_memory + recall_memory)
=======================================================
  save status: 200  id=1 status=ok
  recall count: 1
  -> PASS: 记忆服务通过网关读写成功
  (已清理测试数据)

=======================================================
TEST 8: GET /api/quota/usage
=======================================================
  status: 200
  project: customer-service
  used: 0 / 100000
  -> PASS: 配额查询成功

=======================================================
TEST 9: 项目隔离（不同 API Key）
=======================================================
  Key A → project: customer-service
  Key B → project: writing-assistant
  -> PASS: 不同 API Key 映射到不同项目

=======================================================
TEST 10: Trace ID 验证
=======================================================
  X-Trace-ID: a1b2c3d4e5f6
  -> PASS: 响应头包含 12 位 Trace ID

=======================================================
ALL TESTS COMPLETED!
=======================================================
```

> 如果某个 MCP 服务未启动，对应的测试会显示 `-> SKIP` 而不是失败。

---

## 验证要点

| 测试 | 验证的治理能力 | 通过标准 |
|------|-------------|---------|
| TEST 1 | 健康检查 | 返回所有 4 个服务的状态，无需认证 |
| TEST 2 | 认证 — 无 Key | 返回 401 + 错误提示 |
| TEST 3 | 认证 — 错误 Key | 返回 401 |
| TEST 4 | Tool 转发 | 通过网关调用 Prompt 中心的 Tool 成功 |
| TEST 5 | Prompt 转发 | 通过网关获取渲染后的 Prompt，参数全部填充 |
| TEST 6 | Prompt 列表 | 通过网关列出所有可用 Prompt |
| TEST 7 | 记忆服务全链路 | 写入 → 召回 → 清理，数据一致 |
| TEST 8 | 配额查询 | 返回正确的项目 ID 和配额信息 |
| TEST 9 | 项目隔离 | 两个 API Key 映射到不同 project_id |
| TEST 10 | 链路追踪 | 响应头含 12 位 Trace ID |

---

## 测试流程图解

```
test_gateway.py              网关 (:8000)                MCP 服务
   │                            │                          │
   │── GET /api/health ───────→│── check_health ─────────→│ 逐个探测 4 个服务
   │←─ {status, services} ────│←─ {ok/error} ───────────│
   │                            │                          │
   │── POST /api/tool/call ──→│                          │
   │   (无 API Key)            │                          │
   │←─ 401 Unauthorized ──────│  AuthMiddleware 拦截      │
   │                            │                          │
   │── POST /api/tool/call ──→│                          │
   │   (错误 API Key)          │                          │
   │←─ 401 Unauthorized ──────│  AuthMiddleware 拦截      │
   │                            │                          │
   │── POST /api/tool/call ──→│── call_tool ────────────→│ prompt-hub
   │   Key=cs-demo-key-001     │   "list_prompt_templates" │  :9004/mcp
   │←─ {templates, count} ────│←─ {templates:[...]} ────│
   │                            │                          │
   │── POST /api/prompt/get ─→│── get_prompt ───────────→│ prompt-hub
   │   "customer_service_qa"   │   (MCP 原生 Prompt)      │  :9004/mcp
   │←─ {messages} ────────────│←─ 渲染后的 Prompt ──────│
   │                            │                          │
   │── GET /api/prompt/list ──→│── list_prompts ─────────→│ prompt-hub
   │←─ {prompts, count} ──────│←─ prompt 列表 ──────────│
   │                            │                          │
   │── POST (save_memory) ───→│── call_tool ────────────→│ memory-service
   │←─ {status: ok, id: 1} ──│←─ 保存成功 ─────────────│  :9003/mcp
   │                            │                          │
   │── POST (recall_memory) ─→│── call_tool ────────────→│ memory-service
   │←─ {messages, count: 1} ──│←─ 召回成功 ─────────────│  :9003/mcp
   │                            │                          │
   │── POST (clear_memory) ──→│── call_tool ────────────→│ memory-service
   │←─ {status: ok} ──────────│←─ 清理成功 ─────────────│
   │                            │                          │
   │── GET /api/quota/usage ──→│                          │
   │←─ {used_tokens, limit} ──│  从内存读取配额计数器     │
   │                            │                          │
   │── GET /api/quota/usage ──→│  (Key A)                │
   │── GET /api/quota/usage ──→│  (Key B)                │
   │   验证两个 project_id 不同│                          │
   │                            │                          │
   │── GET /api/health ───────→│                          │
   │   检查 X-Trace-ID 响应头  │                          │
   │←─ 200 + X-Trace-ID ──────│                          │
```

---

## 手动测试（curl）

如果不想跑脚本，也可以用 curl 逐个验证：

### 健康检查

```bash
curl http://127.0.0.1:8000/api/health
```

### 调用 Tool

```bash
curl -X POST http://127.0.0.1:8000/api/tool/call \
  -H "X-API-Key: cs-demo-key-001" \
  -H "Content-Type: application/json" \
  -d '{"service":"memory-service","tool":"recall_memory","arguments":{"project_id":"customer-service","session_id":"test","last_n":5}}'
```

### 获取 Prompt

```bash
curl -X POST http://127.0.0.1:8000/api/prompt/get \
  -H "X-API-Key: cs-demo-key-001" \
  -H "Content-Type: application/json" \
  -d '{"service":"prompt-hub","prompt":"customer_service_qa","arguments":{"context":"专业版 2999 元/月","history":"无","question":"多少钱？","user_profile":""}}'
```

### 查看配额

```bash
curl -H "X-API-Key: cs-demo-key-001" http://127.0.0.1:8000/api/quota/usage
```

---

## 常见问题

### Q: TEST 1 显示某个服务 status=error？

说明该 MCP 服务未启动。检查对应端口是否在监听：

```bash
# Windows
netstat -ano | findstr "9001 9002 9003 9004"
# Mac/Linux
lsof -i :9001,:9002,:9003,:9004
```

### Q: TEST 4/5/6 显示 SKIP？

Prompt 中心 (:9004) 未启动。网关可以启动但无法转发到不可用的服务。

### Q: TEST 7 的 save_memory 返回 502？

记忆服务 (:9003) 未启动。确认 `uv run shared/memory_service/server.py` 已执行。

### Q: 所有 TEST 都返回 401？

检查 `gateway/config.yaml` 中 projects 下的 api_key 是否与测试脚本中的 `API_KEY_A` / `API_KEY_B` 一致。

### Q: 想看网关的详细日志？

网关默认以 INFO 级别输出。启动时可以在网关终端看到每个请求的 Trace ID、项目 ID、耗时等信息：

```
[gateway.access] [a1b2c3d4e5f6] → POST /api/tool/call
[gateway.auth]   [a1b2c3d4e5f6] 认证通过: project=customer-service
[gateway.mcp]    call_tool | service=memory-service tool=save_memory
[gateway.access] [a1b2c3d4e5f6] ← 200  85ms
```
