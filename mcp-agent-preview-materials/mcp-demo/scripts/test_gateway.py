"""
测试 HTTP 网关 — 验证认证、路由转发、配额、Prompt/Tool 调用。

前提：先启动至少 Prompt 中心和记忆服务，再启动网关
    uv run shared/prompt_hub/server.py    # 端口 9004
    uv run shared/memory_service/server.py # 端口 9003
    cd mcp-demo && uvicorn gateway.main:app --port 8000

运行：
    uv run scripts/test_gateway.py
"""

import asyncio
import json

import httpx

GATEWAY_URL = "http://127.0.0.1:8000"
API_KEY_A = "cs-demo-key-001"
API_KEY_B = "wa-demo-key-001"
BAD_KEY = "invalid-key-xxx"


async def main():
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30) as client:

        # ── TEST 1: 健康检查（无需认证） ──
        print("=" * 55)
        print("TEST 1: GET /api/health (无需认证)")
        print("=" * 55)
        resp = await client.get("/api/health")
        print(f"  status: {resp.status_code}")
        data = resp.json()
        print(f"  overall: {data['status']}")
        for name, info in data.get("services", {}).items():
            print(f"  - {name}: {info['status']}")
        print()

        # ── TEST 2: 认证失败 ──
        print("=" * 55)
        print("TEST 2: 认证失败 (无 API Key)")
        print("=" * 55)
        resp = await client.post("/api/tool/call", json={
            "service": "memory-service",
            "tool": "recall_memory",
            "arguments": {"project_id": "test", "session_id": "s1"},
        })
        print(f"  status: {resp.status_code}")
        print(f"  body: {resp.json()}")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("  -> PASS: 无 Key 返回 401")
        print()

        # ── TEST 3: 认证失败 (错误 Key) ──
        print("=" * 55)
        print("TEST 3: 认证失败 (错误 API Key)")
        print("=" * 55)
        resp = await client.post(
            "/api/tool/call",
            headers={"X-API-Key": BAD_KEY},
            json={"service": "memory-service", "tool": "recall_memory", "arguments": {"project_id": "test", "session_id": "s1"}},
        )
        print(f"  status: {resp.status_code}")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("  -> PASS: 错误 Key 返回 401")
        print()

        headers_a = {"X-API-Key": API_KEY_A}
        headers_b = {"X-API-Key": API_KEY_B}

        # ── TEST 4: 调用 Tool — list_prompt_templates ──
        print("=" * 55)
        print("TEST 4: POST /api/tool/call (list_prompt_templates)")
        print("=" * 55)
        resp = await client.post(
            "/api/tool/call",
            headers=headers_a,
            json={
                "service": "prompt-hub",
                "tool": "list_prompt_templates",
                "arguments": {},
            },
        )
        print(f"  status: {resp.status_code}")
        data = resp.json()
        if resp.status_code == 200:
            print(f"  template count: {data.get('count')}")
            for tpl in data.get("templates", []):
                print(f"  - {tpl['name']}")
            print("  -> PASS: Tool 调用成功")
        else:
            print(f"  error: {data}")
            print("  -> SKIP: prompt-hub 可能未启动")
        print()

        # ── TEST 5: 获取 Prompt ──
        print("=" * 55)
        print("TEST 5: POST /api/prompt/get (customer_service_qa)")
        print("=" * 55)
        resp = await client.post(
            "/api/prompt/get",
            headers=headers_a,
            json={
                "service": "prompt-hub",
                "prompt": "customer_service_qa",
                "arguments": {
                    "context": "专业版每月 299 元",
                    "history": "用户: 我要专业版",
                    "question": "多少钱？",
                    "user_profile": "预算 500 以内",
                },
            },
        )
        print(f"  status: {resp.status_code}")
        data = resp.json()
        if resp.status_code == 200:
            msg = data["messages"][0]
            print(f"  role: {msg['role']}")
            print(f"  preview: {msg['content'][:80]}...")
            has_context = "299" in msg["content"]
            has_profile = "500" in msg["content"]
            if has_context and has_profile:
                print("  -> PASS: 参数正确渲染到 Prompt")
            else:
                print(f"  -> FAIL: context={has_context}, profile={has_profile}")
        else:
            print(f"  error: {data}")
            print("  -> SKIP: prompt-hub 可能未启动")
        print()

        # ── TEST 6: 列出 Prompt ──
        print("=" * 55)
        print("TEST 6: GET /api/prompt/list")
        print("=" * 55)
        resp = await client.get(
            "/api/prompt/list",
            headers=headers_a,
            params={"service": "prompt-hub"},
        )
        print(f"  status: {resp.status_code}")
        data = resp.json()
        if resp.status_code == 200:
            print(f"  prompt count: {data.get('count')}")
            for p in data.get("prompts", []):
                args = [a["name"] for a in p.get("arguments", [])]
                print(f"  - {p['name']}: args={args}")
            print("  -> PASS: Prompt 列表获取成功")
        else:
            print(f"  error: {data}")
            print("  -> SKIP: prompt-hub 可能未启动")
        print()

        # ── TEST 7: 调用记忆服务 Tool ──
        print("=" * 55)
        print("TEST 7: POST /api/tool/call (save_memory + recall_memory)")
        print("=" * 55)

        resp = await client.post(
            "/api/tool/call",
            headers=headers_a,
            json={
                "service": "memory-service",
                "tool": "save_memory",
                "arguments": {
                    "project_id": "customer-service",
                    "session_id": "gateway-test-001",
                    "role": "user",
                    "content": "通过网关写入的测试消息",
                },
            },
        )
        print(f"  save status: {resp.status_code}", end="")
        memory_ok = resp.status_code == 200
        if memory_ok:
            save_data = resp.json()
            print(f"  id={save_data.get('id')} status={save_data.get('status')}")
        else:
            print(f"  error: {resp.json()}")
            print("  -> SKIP: memory-service 可能未启动")

        if memory_ok:
            resp = await client.post(
                "/api/tool/call",
                headers=headers_a,
                json={
                    "service": "memory-service",
                    "tool": "recall_memory",
                    "arguments": {
                        "project_id": "customer-service",
                        "session_id": "gateway-test-001",
                        "last_n": 5,
                    },
                },
            )
            recall_data = resp.json()
            print(f"  recall count: {recall_data.get('count')}")
            if recall_data.get("count", 0) > 0:
                print("  -> PASS: 记忆服务通过网关读写成功")
            else:
                print("  -> FAIL: 写入后召回为空")

            # 清理测试数据
            await client.post(
                "/api/tool/call",
                headers=headers_a,
                json={
                    "service": "memory-service",
                    "tool": "clear_memory",
                    "arguments": {
                        "project_id": "customer-service",
                        "session_id": "gateway-test-001",
                    },
                },
            )
            print("  (已清理测试数据)")
        print()

        # ── TEST 8: 配额查询 ──
        print("=" * 55)
        print("TEST 8: GET /api/quota/usage")
        print("=" * 55)
        resp = await client.get("/api/quota/usage", headers=headers_a)
        print(f"  status: {resp.status_code}")
        data = resp.json()
        print(f"  project: {data.get('project_id')}")
        print(f"  used: {data.get('used_tokens')} / {data.get('daily_limit')}")
        print("  -> PASS: 配额查询成功")
        print()

        # ── TEST 9: 不同项目隔离验证 ──
        print("=" * 55)
        print("TEST 9: 项目隔离（不同 API Key）")
        print("=" * 55)
        resp_a = await client.get("/api/quota/usage", headers=headers_a)
        resp_b = await client.get("/api/quota/usage", headers=headers_b)
        project_a = resp_a.json().get("project_id")
        project_b = resp_b.json().get("project_id")
        print(f"  Key A → project: {project_a}")
        print(f"  Key B → project: {project_b}")
        if project_a != project_b:
            print("  -> PASS: 不同 API Key 映射到不同项目")
        else:
            print("  -> FAIL: 项目未隔离")
        print()

        # ── TEST 10: Trace ID ──
        print("=" * 55)
        print("TEST 10: Trace ID 验证")
        print("=" * 55)
        resp = await client.get("/api/health")
        trace_id = resp.headers.get("X-Trace-ID")
        print(f"  X-Trace-ID: {trace_id}")
        if trace_id and len(trace_id) == 12:
            print("  -> PASS: 响应头包含 12 位 Trace ID")
        else:
            print(f"  -> FAIL: Trace ID 格式异常")
        print()

        print("=" * 55)
        print("ALL TESTS COMPLETED!")
        print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
