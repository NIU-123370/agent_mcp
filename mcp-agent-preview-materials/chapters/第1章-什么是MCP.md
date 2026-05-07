# 第 1 章：什么是 MCP？

> 一句话：MCP 是 AI 世界的 USB-C —— 一个让 LLM 连接外部工具和数据的标准协议。

---

## 1.1 MCP 解决什么问题？

LLM 很聪明，但它是一个**关在房间里的天才** —— 不能读你的文件、查你的数据库、调你的 API。

为了让 LLM "动手做事"，之前每个项目都要自己写一套对接代码。3 个项目 × 4 个工具 = 12 套重复代码。这就是 **N×M 问题**。

MCP 在中间插入一层标准协议，把 N×M 降为 **N+M**：

```
  没有 MCP：每条线都是一套定制代码        有了 MCP：每边只实现一次协议

  项目A ─┬─ 数据库                     项目A ─┐          ┌─ 数据库 Server
         ├─ 搜索                       项目B ─┼─ MCP ────┼─ 搜索 Server
         ├─ 文件                       项目C ─┘          ├─ 文件 Server
         └─ 微信                                         └─ 微信 Server
  项目B ─┬─ 数据库
         ├─ 搜索                       3 + 4 = 7 套代码
         ├─ 文件                       而不是 3 × 4 = 12 套
         └─ 微信
  项目C ─┬─ ……
```

**记住这个核心价值：项目越多、工具越多，MCP 的收益越大。**

---

## 1.2 六个核心概念（30 秒看懂）

```
┌─────────────────────────────────────────────────┐
│                   Host（宿主）                    │
│        Claude Desktop / Cursor / 你的 App        │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Client A │  │ Client B │  │ Client C │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
└───────┼──────────────┼──────────────┼────────────┘
        │              │              │
  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
  │ Server    │  │ Server    │  │ Server    │
  │ 数据库    │  │ 搜索引擎   │  │ 文件系统   │
  │           │  │           │  │           │
  │ • Tools   │  │ • Tools   │  │ • Tools   │
  │ • Resources│ │ • Resources│ │ • Resources│
  │ • Prompts │  │ • Prompts │  │ • Prompts │
  └───────────┘  └───────────┘  └───────────┘
```

| 概念 | 一句话理解 | 类比 |
|---|---|---|
| **Host** | 用户交互的应用，管理所有 Client | 电脑 |
| **Client** | Host 内部的连接器，1 个 Client 连 1 个 Server | USB 接口 |
| **Server** | 提供能力的服务，暴露 Tool/Resource/Prompt | USB 设备 |
| **Tool** | LLM 可调用的**操作**（有副作用） | 手 —— 做事 |
| **Resource** | LLM 可读取的**数据**（只读） | 眼睛 —— 看信息 |
| **Prompt** | 预定义的提示词模板（可复用） | 标准操作手册 |

---

## 1.3 MCP vs 传统 API：本质区别

传统 API：**开发者在写代码时**就决定了"什么条件调什么接口、传什么参数"。

MCP：**LLM 在运行时**根据用户的自然语言，自主判断调哪个 Tool、传什么参数。

```
传统 API                              MCP
─────────                            ─────
if "发邮件" in input:                 LLM 看到 Tool 描述 →
    email = parse(input)              自动理解"发邮件"意图 →
    send_api(email, subject, body)    自动生成参数 →
                                      调用 send_email Tool
↑ 开发者硬编码逻辑                    ↑ LLM 自主决策
```

核心推论：**Tool 的 description 写得好不好，直接决定 LLM 调用得准不准。** 这是 MCP 开发中最重要的事。

---

## 1.4 两种通信方式

| | stdio | SSE / Streamable HTTP |
|---|---|---|
| **原理** | Server 作为子进程，通过 stdin/stdout 通信 | Server 通过网络通信（HTTP） |
| **适用** | 本地开发、桌面应用 | 远程部署、**多项目共享**（本教程核心） |
| **优点** | 简单、零配置 | 可共享、可扩展 |

**对本教程而言，SSE/Streamable HTTP 是重点** —— 因为只有走网络，才能实现多个项目共享同一个 MCP Server。

---

## 1.5 四大能力速览

| 能力 | 方向 | 一句话 |
|---|---|---|
| **Tool** | Client → Server | LLM 调用外部函数执行操作 |
| **Resource** | Client → Server | LLM 读取外部数据作为上下文 |
| **Prompt** | Client → Server | Server 分发标准化提示词模板 |
| **Sampling** | Server → Client | Server 反过来请求 LLM 推理（高级） |

使用频率：Tool ≫ Resource > Prompt > Sampling。入门阶段只关注 **Tool** 就够了。

---

## 本章小结

```
MCP = 标准协议，连接 LLM 和外部世界
核心价值 = N×M → N+M，工具写一次、所有项目复用
六个角色 = Host > Client > Server（提供 Tool/Resource/Prompt）
本质区别 = LLM 自主决策调用，不是开发者硬编码
通信方式 = stdio（本地）vs SSE（远程共享 ← 本教程重点）
```

> **下一章**：理论够了，直接看一个真实项目中 MCP 是什么样的。

---

[返回目录](../MCP多项目共享服务教程大纲.md) | [下一章 →](./第2章-MCP能做什么.md)
