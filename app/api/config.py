"""部署级主开关查询路由 —— 单一职责:前端下拉选择器按可用性过滤选项。

GET /api/config 返回 {web_search_enabled, xhs_enabled} 两个布尔(只读、不含任何密钥),
前端加载时据此决定「联网搜索 / 小红书」选项是否渲染;两者均 false 时下拉整体隐藏。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import Config

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def get_config() -> dict:
    """返回外部召回源的主开关状态(前端过滤搜索模式下拉选项用)。"""
    return {
        "web_search_enabled": Config.WEB_SEARCH_ENABLED,
        "xhs_enabled": Config.XHS_MCP_ENABLED,
    }
