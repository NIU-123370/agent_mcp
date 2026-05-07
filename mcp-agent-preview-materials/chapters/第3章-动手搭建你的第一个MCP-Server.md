# 第 3 章：动手搭建你的第一个 MCP Server

> 一句话：用 Python 几十行代码就能跑起一个 MCP Server，接入 Claude Desktop / Cursor 立即可用。本章只给关键步骤，不展开细节。

---

## 3.1 环境与 SDK 选择

| | Python SDK | TypeScript SDK |
|---|---|---|
| 包名 | `mcp[cli]` | `@modelcontextprotocol/sdk` |
| 要求 | Python 3.10+ | Node.js 18+ |
| 推荐场景 | 快速原型、AI/数据项目 | Web 服务、前端生态 |

本章用 **Python** 演示（最少代码量），TypeScript 写法几乎是等价的。

```bash
mkdir my-mcp-server && cd my-mcp-server
uv init && uv add "mcp[cli]"
```

---

## 3.2 最小 Server：4 行代码

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

if __name__ == "__main__":
    mcp.run()
```

这就是一个完整的 MCP Server。它通过 stdio 等待 Client 连接，只是还没注册任何能力。

---

## 3.3 注册 Tool 和 Resource

```python
from mcp.server.fastmcp import FastMCP
import json

mcp = FastMCP("my-server")

# ── Tool：LLM 可以调用的操作 ──────────────────────
@mcp.tool()
async def get_weather(city: str) -> str:
    """获取指定城市的天气。用户问天气时使用。"""
    # 实际项目中调用真实 API
    data = {"北京": "晴 22°C", "上海": "多云 26°C", "深圳": "阵雨 30°C"}
    return data.get(city, f"暂不支持 {city}")

@mcp.tool()
async def query_database(sql: str) -> str:
    """执行 SQL 查询并返回结果。需要查数据时使用。"""
    # 实际项目中执行真实查询
    return json.dumps({"rows": 42, "sample": "..."})

# ── Resource：LLM 可以读取的上下文 ────────────────
@mcp.resource("db://schema")
async def get_schema() -> str:
    """数据库表结构"""
    return "users(id, name, email) | orders(id, user_id, amount, date)"

@mcp.resource("notes://{name}")
async def get_note(name: str) -> str:
    """读取笔记内容"""
    notes = {"todo": "- 学习MCP\n- 搭建Server", "ideas": "- 智能客服\n- 知识库"}
    return notes.get(name, "不存在")

if __name__ == "__main__":
    mcp.run()
```

**模式很简单**：`@mcp.tool()` 注册操作，`@mcp.resource()` 注册数据，docstring 就是给 LLM 看的描述。

---

## 3.4 调试：MCP Inspector

官方提供了可视化调试工具，一行命令启动：

```bash
npx @modelcontextprotocol/inspector uv run main.py
```

打开 `http://localhost:5173`，可以看到所有注册的 Tool/Resource，手动测试调用，查看 JSON-RPC 通信日志。

> **开发 MCP Server 的标准流程**：写代码 → Inspector 调试 → 接入 Host 验证。

---

## 3.5 接入 Claude Desktop / Cursor

接入本质上就是**告诉 Host 如何启动你的 Server**。

### Claude Desktop

编辑配置文件（macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`，Windows: `%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/my-mcp-server", "main.py"]
    }
  }
}
```

### Cursor

项目根目录下创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/my-mcp-server", "main.py"]
    }
  }
}
```

重启后，LLM 就能自动发现并调用你的 Tool。

---

## 3.6 这和多项目共享有什么关系？

目前的接入方式是 **stdio**：每个 Host 各自启动一个 Server 子进程。

```
Claude Desktop → 启动 → Server 进程 A（独占）
Cursor         → 启动 → Server 进程 B（独占）
你的 App       → 启动 → Server 进程 C（独占）
```

问题已经出现了：**三个 Server 进程跑着完全相同的代码，各自独立，无法共享状态。**

要实现多项目共享，需要把传输方式从 stdio 切换到 **SSE / Streamable HTTP**：

```
Claude Desktop ──┐
Cursor         ──┼──► 网络请求 ──► 共享 MCP Server（一个实例）
你的 App       ──┘
```

这就是后续章节要解决的架构问题。

```
当前位置                        目标
───────                        ────
stdio 模式                     SSE/HTTP 模式
每个 Host 独占一个 Server       多个 Host 共享一个 Server
无状态管理                      集中管理、统一日志、统一鉴权
每个项目各搞一套                抽象为共享基础设施
        │                              │
        └──── 第 4-7 章解决这个跨越 ────┘
```

---

## 本章小结

```
搭建 MCP Server = 几十行 Python，装饰器注册 Tool/Resource
调试 = MCP Inspector（可视化 Web 工具）
接入 = 配置 JSON 告诉 Host 启动命令
关键认知 = stdio 模式是单机独占的，要共享必须走网络（SSE/HTTP）
```

> **下一章**：看一个真实 AI 项目中有哪些 MCP Server，感受单项目的完整 MCP 生态。

---

[← 上一章](./第2章-MCP能做什么.md) | [返回目录](../MCP多项目共享服务教程大纲.md) | [下一章 →](./第4章-一个典型AI项目中有哪些MCP.md)
