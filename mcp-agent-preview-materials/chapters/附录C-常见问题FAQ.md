# 附录 C：常见问题 FAQ

---

### Q1：MCP 和 LangChain 是什么关系？

```
LangChain = 框架（Python/JS 库，提供 Agent、Chain 等抽象）
MCP      = 协议（定义 LLM 和工具之间的通信标准）

类比：
  LangChain 像 Express.js（Web 框架）
  MCP 像 HTTP（通信协议）

它们不是替代关系，可以同时使用：
  LangChain Agent → 通过 MCP Client → 调用 MCP Server

区别：
  LangChain Tool 绑定在框架内，换框架要重写
  MCP Server 独立运行，任何 Client 都能调用（不绑框架）
```

---

### Q2：已有项目如何平滑迁移到共享服务？

```
迁移路径（渐进式，不要一步到位）：

阶段 1：共存
  旧代码继续运行
  新建共享 MCP Server
  新功能优先接入共享服务
  旧功能暂时不动

阶段 2：逐步切换
  选一个低风险的能力（如 RAG）先迁移
  双写一段时间，验证共享服务的稳定性
  确认无误后，关闭旧的 RAG 实现

阶段 3：全面迁移
  按优先级逐个迁移其他能力
  保留旧代码作为 Fallback（至少一个月）
  最后下线旧代码

关键原则：
  ✅ 渐进式迁移，不搞大爆炸
  ✅ 新旧并行，随时可回滚
  ✅ 先迁低风险、高收益的模块
  ❌ 不要试图一次全部迁移
```

---

### Q3：小团队（3-5 人）需要这么完整的架构吗？

```
不需要。

小团队的务实方案：

  必须做（第一天就需要）：
    ✅ LLM 统一网关（一个，管理所有 Key 和模型选择）
    ✅ 基本的日志记录

  建议做（有 2-3 个 AI 项目时）：
    ✅ RAG 共享服务（避免重复建设）
    ✅ 统一的成本看板

  可以不做：
    ❌ 多区域部署
    ❌ 完整的 Tool 注册中心
    ❌ 可视化工作流编排
    ❌ 应用市场
    ❌ Serverless 部署

  架构简化版：

    项目 A ──┐
    项目 B ──┼── 共享 LLM 网关 + RAG 服务（一个进程就够）
    项目 C ──┘

  一个进程、一个 Docker 容器，搞定。
  不要为 3 个项目搞微服务架构。
```

---

### Q4：MCP 和 Function Calling 有什么区别？

```
Function Calling = 模型厂商的私有实现
  OpenAI 的 function_call 格式
  Claude 的 tool_use 格式
  各家格式不同，切模型要改代码

MCP = 开放的标准协议
  统一的 Tool 定义和调用格式
  不绑定任何模型厂商
  切模型不需要改 Tool 代码

MCP 底层仍然依赖模型的 Function Calling 能力，
但在上层提供了一个统一的抽象。
```

---

### Q5：MCP Server 用 Python 还是 TypeScript？

```
选 Python 如果：
  ✅ 团队更熟悉 Python
  ✅ 做数据处理 / AI / 科学计算
  ✅ 想用最少的代码快速出原型

选 TypeScript 如果：
  ✅ 团队是全栈 JS/TS 技术栈
  ✅ Server 需要和 Web 前端深度集成
  ✅ 追求强类型安全

两者功能完全对等，不存在"谁更好"，只有"谁更适合你的团队"。
```

---

### Q6：已有 REST API，怎么包装成 MCP Server？

```
不需要重写，只需要加一层 MCP 适配：

  已有的 REST API（不改）
       │
  MCP Server（薄薄一层包装）
       │
  @mcp.tool()
  async def search_products(keyword: str) -> str:
      """搜索商品"""
      # 直接调用已有的 REST API
      response = await http_client.get(
          f"https://api.internal.com/products?q={keyword}"
      )
      return response.text

核心工作：
  1. 为每个 API 端点写一个 Tool wrapper
  2. 重点写好 description（给 LLM 看的）
  3. 做好错误处理和返回值格式化
```

---

### Q7：MCP 的安全性如何保证？LLM 会不会乱调 Tool？

```
安全保障是多层的：

  层 1：Tool 描述（软约束）
    在 description 中说明"这个 Tool 会删除数据，谨慎使用"
    LLM 会参考描述来决定是否调用

  层 2：Host 确认（人在回路）
    高危操作弹窗让用户确认
    用户可以拒绝 LLM 的调用请求

  层 3：Server 端校验（硬约束）
    参数校验、权限检查
    敏感操作需要二次确认 token

  层 4：网关层管控
    按项目/用户限制可调用的 Tool
    审计日志记录所有操作
    异常行为自动告警

结论：LLM 可能会"想"乱调，但多层防护确保它"做不到"。
```

---

[← 附录 B](./附录B-项目模板与代码仓库.md) | [返回目录](../MCP多项目共享服务教程大纲.md) | [附录 D →](./附录D-术语表.md)
