# 附录 D：术语表

---

| 术语 | 英文 | 定义 |
|---|---|---|
| **MCP** | Model Context Protocol | 模型上下文协议，定义 AI 应用与外部工具/数据源的通信标准 |
| **Host** | Host | 宿主应用，用户直接交互的程序（如 Claude Desktop、Cursor） |
| **Client** | MCP Client | Host 内部的连接器，负责与 Server 通信（1 Client : 1 Server） |
| **Server** | MCP Server | 提供能力的服务端，暴露 Tool/Resource/Prompt |
| **Tool** | Tool | LLM 可调用的外部函数/操作，可以有副作用 |
| **Resource** | Resource | LLM 可读取的只读数据，通过 URI 标识 |
| **Prompt** | Prompt Template | 预定义的提示词模板，可参数化和复用 |
| **Sampling** | Sampling | Server 请求 Client 的 LLM 进行推理的反向调用机制 |
| **stdio** | Standard I/O | 标准输入输出传输方式，Server 作为子进程运行 |
| **SSE** | Server-Sent Events | 基于 HTTP 的服务端推送传输方式 |
| **Streamable HTTP** | Streamable HTTP | MCP 新增的 HTTP 传输方式，支持断线重连 |
| **JSON-RPC** | JSON-RPC 2.0 | MCP 使用的消息格式标准 |
| **LLM** | Large Language Model | 大语言模型（如 GPT-4、Claude、Gemini） |
| **RAG** | Retrieval-Augmented Generation | 检索增强生成，让 LLM 基于检索到的文档回答 |
| **Embedding** | Embedding | 将文本转换为向量表示 |
| **向量数据库** | Vector Database | 专门存储和检索向量的数据库（如 Milvus、Qdrant） |
| **语义缓存** | Semantic Cache | 基于语义相似度匹配的缓存，而非精确匹配 |
| **多租户** | Multi-tenancy | 多个项目/用户共享同一服务但数据隔离 |
| **Fallback** | Fallback | 主服务不可用时的降级备选方案 |
| **Trace** | Distributed Trace | 分布式追踪，用 trace_id 串联一次请求的完整链路 |
| **PII** | Personally Identifiable Information | 个人可识别信息（手机号、身份证等） |
| **Rerank** | Reranking | 对初步检索结果用交叉编码器重新排序，提升精度 |
| **Token** | Token | LLM 处理文本的最小单位，也是计费单位 |
| **QPS** | Queries Per Second | 每秒查询数，衡量系统吞吐量 |
| **SLA** | Service Level Agreement | 服务级别协议，定义可用性和性能承诺 |
| **灰度发布** | Canary Release | 新版本先对部分流量生效，验证后再全量 |
| **蓝绿部署** | Blue-Green Deployment | 两套环境交替上线，实现零停机发布 |

---

[← 附录 C](./附录C-常见问题FAQ.md) | [返回目录](../MCP多项目共享服务教程大纲.md)
