"""
HTTP 网关入口 — FastAPI 应用，组装中间件，转发请求到 MCP 共享服务。

启动：
  cd mcp-demo
  uvicorn gateway.main:app --port 8000

或通过 start_all.py 一键启动全部服务。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI

from .auth import AuthMiddleware
from .logger import LoggerMiddleware
from .mcp_client_manager import MCPClientManager
from .quota import QuotaMiddleware, QuotaTracker
from .router import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)
logger = logging.getLogger("gateway")

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

with open(CONFIG_PATH, encoding="utf-8") as f:
    config = yaml.safe_load(f)

mcp_manager = MCPClientManager(config["services"])
quota_tracker = QuotaTracker(config["projects"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HTTP 网关启动")
    logger.info("  注册服务: %s", ", ".join(mcp_manager.service_names))
    logger.info("  注册项目: %s", ", ".join(config["projects"].keys()))
    yield
    logger.info("HTTP 网关关闭")


app = FastAPI(
    title="MCP 共享服务网关",
    description="统一入口：认证 → 日志 → 配额 → 转发到 MCP 服务",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.mcp = mcp_manager
app.state.quota = quota_tracker

app.include_router(router)

app.add_middleware(QuotaMiddleware, tracker=quota_tracker)
app.add_middleware(AuthMiddleware, projects=config["projects"])
app.add_middleware(LoggerMiddleware)
