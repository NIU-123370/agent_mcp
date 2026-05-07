# 第 2 章：MCP 能做什么？— 能力全景图

> 一句话：MCP 有四种能力 —— Tool（做事）、Resource（看数据）、Prompt（模板）、Sampling（反向推理）。90% 的场景只用 Tool。

---

## 2.1 Tool：让 LLM 动手做事

Tool 是 MCP 的核心，没有之一。

**本质**：LLM 说"我需要查数据库"，MCP 帮它真的去查。

```
用户："上周销售额多少？"
  │
  ▼
LLM 分析意图 → 决定调用 query_database Tool
  │
  ▼
MCP Client → Server 执行真实 SQL 查询 → 返回结果
  │
  ▼
LLM："上周销售总额 ¥128,000，环比增长 12%"
```

一个 Tool 的定义就三样东西：

| 字段 | 作用 | 关键程度 |
|---|---|---|
| `name` | 工具名称 | 一般 |
| `description` | 告诉 LLM 这个工具干什么、什么时候该用 | **决定性** |
| `inputSchema` | 参数定义（JSON Schema） | 高 |

> **架构启示**：Tool 的 description 是写给 LLM 看的，不是给人看的。写得好不好直接决定调用准确率。这在后续共享服务设计中会成为一个治理问题。

### Tool 的分类思维

```
         按副作用分
        ┌──────────────────────────┐
        │                          │
    只读查询                    有副作用操作
  （查天气、搜商品）          （发邮件、删文件、改配置）
        │                          │
   可放心让 LLM 自主调用       需要确认机制 / 权限控制
```

这个分类在设计共享服务时非常重要 —— **只读 Tool 可以大胆复用，有副作用的 Tool 必须加权限控制。**

---

## 2.2 Resource：给 LLM 喂上下文

Resource 是只读数据通道，通过 URI 标识：

```
file:///src/config.yaml          → 配置文件
db://production/users/schema     → 表结构
docs://api/v2/endpoints          → API 文档
```

**Resource vs Tool 的判断标准**：

```
需要获取数据 → 能用 URI 直接定位？ → 是 → Resource
                                   → 否 → 需要复杂参数/逻辑？ → Tool
```

实际场景：让 LLM 先通过 Resource 读取数据库表结构，再用 Tool 写出正确的 SQL。两者配合使用。

> **架构启示**：Resource 天然适合做共享服务 —— 数据库 schema、API 文档、公司 wiki 这些上下文数据，所有项目都需要，只需要一个 Server 提供。

---

## 2.3 Prompt：标准化的提示词分发

MCP Server 可以暴露预定义的 Prompt 模板，供所有接入的项目使用。

**没有 MCP Prompt**：每个人笔记里存一堆 Prompt，微信群里传来传去，版本混乱。

**有了 MCP Prompt**：团队沉淀的最佳 Prompt 放在 Server 上，所有项目统一调用、统一更新。

```
MCP Server（Prompt 中心）
  ├── code_review    → 代码审查模板（v3.2）
  ├── sql_optimizer  → SQL 优化模板（v2.1）
  └── translate      → 翻译模板（v1.5）

项目 A ──┐
项目 B ──┼── 统一拉取最新版本的 Prompt
项目 C ──┘
```

> **架构启示**：Prompt Template 是后续"Prompt 管理中心"（第 11 章）的基础能力。当 Prompt 成为共享资源，版本控制和 A/B 测试就自然成为需求。

---

## 2.4 Sampling：Server 反过来用 LLM

前三种能力都是 Client → Server。Sampling 反过来：**Server 请求 Client 的 LLM 做推理**。

```
常规：Client ──────► Server（"帮我查数据"）
Sampling：Server ──────► Client（"帮我用 LLM 分析这段文本"）
```

典型场景：MCP Server 处理客服工单，工单到达时需要 LLM 判断紧急程度 —— 这个 LLM 调用就是通过 Sampling 完成的。

关键设计：**所有 Sampling 请求必须经过 Host 审核**，Host 可以拒绝、修改、限流。防止 Server 滥用 LLM。

> **架构启示**：Sampling 使得 MCP Server 可以构建复杂的 Agent 工作流 —— Server 不只是被动被调用，还能主动借用 LLM 能力。这在多步骤自动化场景中很有价值。

---

## 2.5 能力全景与架构思考

```
┌──────────┬──────────┬──────────┬──────────┐
│   Tool   │ Resource │  Prompt  │ Sampling │
├──────────┼──────────┼──────────┼──────────┤
│ 做事     │ 看数据   │ 模板     │ 反向推理 │
│ C→S      │ C→S      │ C→S      │ S→C      │
│ LLM 决策 │ 应用选择 │ 用户选择 │ Server  │
│ ★★★★★   │ ★★★★☆   │ ★★★☆☆   │ ★★☆☆☆   │
└──────────┴──────────┴──────────┴──────────┘
```

**从共享服务的视角看**，哪些能力最值得抽象为共享服务？

| 能力 | 共享价值 | 原因 |
|---|---|---|
| Tool | ★★★★★ | 数据库查询、文件操作、第三方 API 调用，几乎每个项目都需要 |
| Resource | ★★★★☆ | 公司知识库、表结构、配置信息，天然的共享数据 |
| Prompt | ★★★★☆ | 最佳实践 Prompt 需要统一管理和版本控制 |
| Sampling | ★★☆☆☆ | 场景较少，通常在特定 Server 内部使用 |

> 这张表就是后续第 6 章"如何识别和抽象通用 MCP 服务"的思考起点。

---

## 本章小结

```
Tool     = 核心能力，LLM 做事的手，区分只读/有副作用
Resource = 只读数据通道，通过 URI 标识，天然适合共享
Prompt   = 提示词分发机制，解决团队 Prompt 管理混乱问题
Sampling = 反向调用，Server 借用 Client 的 LLM，构建 Agent 工作流

共享服务视角：Tool > Resource ≈ Prompt >> Sampling
```

> **下一章**：快速过一遍动手搭建的关键步骤，建立"MCP Server 到底长什么样"的直觉。

---

[← 上一章](./第1章-什么是MCP.md) | [返回目录](../MCP多项目共享服务教程大纲.md) | [下一章 →](./第3章-动手搭建你的第一个MCP-Server.md)
