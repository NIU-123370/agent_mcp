# 附录 B：项目模板与代码仓库

---

## 共享 MCP Server 项目模板（Python）

```
shared-mcp-server/
├── pyproject.toml
├── src/
│   ├── server.py          # MCP Server 入口
│   ├── tools/             # Tool 定义
│   │   ├── __init__.py
│   │   ├── llm.py         # LLM 相关 Tool
│   │   ├── rag.py         # RAG 相关 Tool
│   │   └── memory.py      # 记忆相关 Tool
│   ├── resources/         # Resource 定义
│   │   ├── __init__.py
│   │   └── schema.py
│   ├── config/            # 配置
│   │   ├── settings.py
│   │   └── routes.yaml    # 模型路由配置
│   ├── middleware/         # 中间件
│   │   ├── auth.py        # 认证
│   │   ├── rate_limit.py  # 限流
│   │   ├── logging.py     # 日志
│   │   └── cache.py       # 语义缓存
│   └── utils/
│       ├── db.py
│       └── vector.py
├── tests/
│   ├── test_tools.py
│   └── test_resources.py
├── Dockerfile
└── docker-compose.yaml
```

### 关键文件示意

**server.py**（入口）：

```python
from mcp.server.fastmcp import FastMCP
from src.tools import llm, rag, memory
from src.middleware import auth, rate_limit, logging

mcp = FastMCP("shared-service")

# 注册 Tool（分模块组织）
llm.register(mcp)
rag.register(mcp)
memory.register(mcp)

if __name__ == "__main__":
    mcp.run(transport="sse", port=8080)
```

**tools/rag.py**（模块化 Tool）：

```python
def register(mcp):
    @mcp.tool()
    async def rag_search(query: str, collection: str, top_k: int = 5) -> str:
        """在知识库中语义检索相关文档"""
        # 实现...

    @mcp.tool()
    async def rag_upload(file_path: str, collection: str) -> str:
        """上传文档到知识库"""
        # 实现...
```

---

## MCP 网关项目模板

```
mcp-gateway/
├── src/
│   ├── gateway.py         # 网关入口
│   ├── router.py          # 请求路由
│   ├── registry.py        # 服务注册表
│   ├── auth/
│   │   ├── token.py       # 项目令牌验证
│   │   └── permissions.py # 权限检查
│   ├── middleware/
│   │   ├── rate_limiter.py
│   │   ├── logger.py
│   │   └── metrics.py
│   └── config/
│       ├── servers.yaml   # Server 注册配置
│       └── quotas.yaml    # 配额配置
├── Dockerfile
└── docker-compose.yaml
```

**servers.yaml**（服务注册配置）：

```yaml
servers:
  llm-gateway:
    url: http://llm-service:8081
    health_check: /health
    tools: [chat_completion, embedding, summarize]

  rag-service:
    url: http://rag-service:8082
    health_check: /health
    tools: [rag_search, rag_upload]
    resources: [rag://collections/*]

  memory-service:
    url: http://memory-service:8083
    health_check: /health
    tools: [memory_save, memory_recall]
```

---

## 客户端 SDK 接入示例

**Python 项目接入**：

```python
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    async with sse_client("http://gateway:8080/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 列出可用 Tool
            tools = await session.list_tools()

            # 调用 Tool
            result = await session.call_tool(
                "rag_search",
                arguments={"query": "退货政策", "collection": "FAQ"}
            )
            print(result)
```

**docker-compose.yaml**（一键启动全套服务）：

```yaml
services:
  gateway:
    build: ./mcp-gateway
    ports: ["8080:8080"]
    depends_on: [llm-service, rag-service, redis, qdrant]

  llm-service:
    build: ./llm-server
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}

  rag-service:
    build: ./rag-server
    depends_on: [qdrant]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  qdrant:
    image: qdrant/qdrant
    ports: ["6333:6333"]
```

---

[← 附录 A](./附录A-技术选型参考.md) | [返回目录](../MCP多项目共享服务教程大纲.md) | [附录 C →](./附录C-常见问题FAQ.md)
