"""
统一日志中间件 — 为每个请求分配 Trace ID，记录请求/响应摘要和耗时。

Trace ID 通过 request.state.trace_id 传递给下游中间件和路由，
同时写入响应头 X-Trace-ID 供调用方关联日志。
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("gateway.access")


class LoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = uuid.uuid4().hex[:12]
        request.state.trace_id = trace_id

        start = time.monotonic()
        logger.info("[%s] → %s %s", trace_id, request.method, request.url.path)

        response = await call_next(request)

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "[%s] ← %d  %.0fms",
            trace_id, response.status_code, elapsed_ms,
        )

        response.headers["X-Trace-ID"] = trace_id
        return response
