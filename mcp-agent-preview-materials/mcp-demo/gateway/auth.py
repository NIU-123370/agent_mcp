"""
项目级 API Key 认证中间件。

从请求头 X-API-Key 读取密钥，匹配 config.yaml 中的 projects 配置。
认证成功后将 project_id 写入 request.state.project_id 供下游使用。
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("gateway.auth")

SKIP_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, projects: dict):
        super().__init__(app)
        self._key_to_project = {
            cfg["api_key"]: project_id
            for project_id, cfg in projects.items()
        }

    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS:
            request.state.project_id = "__anonymous__"
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        project_id = self._key_to_project.get(api_key)

        if not project_id:
            trace_id = getattr(request.state, "trace_id", "?")
            logger.warning("[%s] 认证失败: 无效的 API Key", trace_id)
            return JSONResponse(
                status_code=401,
                content={"error": "无效的 API Key", "hint": "请在请求头中设置 X-API-Key"},
            )

        request.state.project_id = project_id
        logger.info(
            "[%s] 认证通过: project=%s",
            getattr(request.state, "trace_id", "?"),
            project_id,
        )
        return await call_next(request)
