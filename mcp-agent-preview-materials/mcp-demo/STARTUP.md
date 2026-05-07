# MCP 多项目共享服务 — 启动指南

> 本文档说明如何从零搭建环境、启动所有服务、运行业务项目。

---

## 前置条件

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.11+ | 推荐 3.12 |
| uv | 0.4+ | Python 包管理器，[安装文档](https://docs.astral.sh/uv/getting-started/installation/) |
| 豆包 API Key | — | 在 [火山引擎控制台](https://console.volcengine.com/ark) 创建推理接入点 |

---

## 1. 环境搭建

### 1.1 克隆项目 & 进入目录

```bash
cd mcp-demo
```

### 1.2 安装依赖

```bash
uv sync
```

这会根据 `pyproject.toml` 创建虚拟环境并安装所有依赖：
- `mcp[cli]` — MCP Python SDK（Streamable HTTP 传输）
- `httpx` — HTTP 客户端
- `openai` — 豆包 API（兼容 OpenAI 格式）
- `fastapi` + `uvicorn` — HTTP 网关
- `chromadb` — 向量数据库
- `pyyaml` + `python-dotenv` — 配置管理

### 1.3 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的豆包 API 信息：

```env
ARK_API_KEY=your-ark-api-key-here
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_CHAT_MODEL=your-chat-endpoint-id
ARK_EMBEDDING_MODEL=your-embedding-endpoint-id
```

> **获取方式**：登录火山引擎控制台 → 模型推理 → 创建推理接入点 → 复制 Endpoint ID。

---

## 2. 验证基础环境（Step 1 — 已完成）

在搭建完整系统之前，先用 Hello World 服务验证 MCP SDK 和 Streamable HTTP 传输是否正常。

### 2.1 启动 Hello World MCP Server

```bash
uv run scripts/hello_server.py
```

预期输出：

```
Streamable HTTP server running on http://127.0.0.1:9000/mcp
```

### 2.2 测试连通性（新开终端）

```bash
uv run scripts/test_hello.py
```

预期输出：

```
正在连接 MCP Server: http://127.0.0.1:9000/mcp
连接成功!

可用工具 (2 个):
  - hello: 向指定的人打招呼，用于验证 MCP Server 是否正常工作
  - add: 两数相加，用于验证参数传递和返回值

调用 hello: 你好, MCP 演示项目! 欢迎使用 MCP 共享服务。
调用 add:   42

所有测试通过!
```

验证通过后，按 `Ctrl+C` 停止 Hello World Server。

---

## 3. 启动完整系统

> **以下为完整系统建成后的启动流程（Step 2-8 完成后可用）。**

### 3.1 进程总览

```
进程                      端口     角色
──────────────────────────────────────────────
LLM 网关 MCP Server       9001    共享服务 ①
RAG 服务 MCP Server       9002    共享服务 ②
记忆服务 MCP Server       9003    共享服务 ③
Prompt 中心 MCP Server    9004    共享服务 ④
HTTP 网关 (FastAPI)       8000    治理层入口
──────────────────────────────────────────────
客服项目 A                  -     业务项目
写作项目 B                  -     业务项目
```

### 3.2 方式一：一键启动

```bash
uv run scripts/start_all.py
```

该脚本会按顺序拉起 4 个 MCP Server + 1 个 HTTP 网关，等待所有服务就绪后输出状态。

### 3.3 方式二：手动逐个启动

如果需要调试，可以分别在不同终端中手动启动各服务。

**终端 1 — LLM 网关**

```bash
uv run shared/llm_gateway/server.py
```

**终端 2 — RAG 服务**

```bash
uv run shared/rag_service/server.py
```

**终端 3 — 记忆服务**

```bash
uv run shared/memory_service/server.py
```

**终端 4 — Prompt 中心**

```bash
uv run shared/prompt_hub/server.py
```

**终端 5 — HTTP 网关**

```bash
uv run uvicorn gateway.main:app --port 8000 --reload
```

> 确保 4 个 MCP Server 全部就绪后再启动网关，网关启动时会尝试连接所有服务。

---

## 4. 初始化知识库

首次运行需要将演示数据导入向量数据库：

```bash
uv run scripts/init_knowledge.py
```

该脚本会：
- 读取 `data/knowledge/products.md`（产品资料 → 项目 A 的知识库）
- 读取 `data/knowledge/writing_guides.md`（写作素材 → 项目 B 的知识库）
- 调用 RAG 服务的 `ingest_document` Tool 完成分块 + 向量化 + 入库

---

## 5. 运行业务项目

### 5.1 项目 A — 智能客服

```bash
uv run projects/customer_service/app.py
```

进入命令行对话模式，输入问题即可与客服 Agent 交互：

```
[客服] 你好！有什么可以帮你的？
[你]   这款产品支持哪些功能？
[客服] 根据产品资料，这款产品支持以下功能……
```

### 5.2 项目 B — AI 写作助手

```bash
uv run projects/writing_assistant/app.py
```

进入命令行交互模式，输入写作主题：

```
[写作助手] 请输入你想写的主题：
[你]        人工智能在教育中的应用
[写作助手] 正在检索参考资料……正在生成文章……
```

---

## 6. 验证演示场景

启动两个项目后，可以验证以下核心场景：

| 场景 | 验证方式 |
|------|---------|
| **共享生效** | 两个项目同时对话，观察网关日志，确认都路由到同一个 LLM 网关 |
| **数据隔离** | 客服问写作相关问题 → 搜不到；写作问产品问题 → 搜不到 |
| **统一日志** | 查看网关终端输出，每条请求都带 Trace ID 和 project_id |
| **配额限流** | 快速发送大量请求使项目 A 超出配额，观察返回限流错误，项目 B 不受影响 |
| **模型切换** | 修改 `shared/llm_gateway/config.yaml` 中的默认模型，两个项目无需改代码即生效 |

---

## 7. 常见问题

### Q: `uv sync` 报错找不到 Python 3.11+

确保系统已安装 Python 3.11 或更高版本，并且在 PATH 中可用：

```bash
python --version
```

如果版本不对，可以用 uv 安装指定版本：

```bash
uv python install 3.12
```

### Q: MCP Server 启动后客户端连不上

- 检查端口是否被占用：`netstat -ano | findstr :9001`
- 确认防火墙没有拦截本地端口
- 确认 Server 输出了 `running on http://127.0.0.1:PORT/mcp`

### Q: 豆包 API 调用失败

- 确认 `.env` 中的 `ARK_API_KEY` 正确且未过期
- 确认 `ARK_CHAT_MODEL` 和 `ARK_EMBEDDING_MODEL` 是推理接入点的 Endpoint ID（不是模型名）
- 检查网络是否能访问 `https://ark.cn-beijing.volces.com`

### Q: ChromaDB 报错

ChromaDB 数据持久化在 `data/chromadb/` 目录。如果数据损坏，可以删除后重新初始化：

```bash
rm -rf data/chromadb/
uv run scripts/init_knowledge.py
```

---

## 8. 目录快速参考

```
mcp-demo/
├── shared/                    # 共享 MCP 服务（4 个独立进程）
│   ├── llm_gateway/           #   ① LLM 统一网关      :9001
│   ├── rag_service/           #   ② RAG 检索服务      :9002
│   ├── memory_service/        #   ③ 会话记忆          :9003
│   └── prompt_hub/            #   ④ Prompt 管理中心   :9004
├── gateway/                   # HTTP 网关 (FastAPI)   :8000
├── projects/                  # 业务项目
│   ├── customer_service/      #   项目 A：智能客服
│   └── writing_assistant/     #   项目 B：AI 写作助手
├── data/                      # 演示数据 + 持久化存储
├── scripts/                   # 启动 & 初始化脚本
├── .env                       # 环境变量（不提交 git）
└── pyproject.toml             # 依赖声明
```
