"""MCP client 封装 —— LangGraph 节点内 stdio 拉起 python -m mcp_server 并调工具。

为什么 stdio 而不是 HTTP:
- 同一进程内拉起,无 8765 端口监听,部署简化;
- FastAPI 主进程启动慢一点(每次 web_search 节点触发都 spawn 子进程),但 web_search
  节点仅在 factual + WEB_SEARCH_ENABLED 时挂载,默认关闭,不影响常规查询性能。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 项目根(app/core/mcp_client.py → 上两级);子进程 cwd 钉死在这里,
# 否则服务从其他目录启动时 `python -m mcp_server` 找不到包。
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])


async def call_tool(tool_name: str, arguments: dict[str, Any]) -> list[dict]:
    """stdio 拉起 mcp_server 子进程,调指定工具,解析 TextContent JSON 返回 list[dict]。

    返回:工具输出的解析结果(可能为空 list);失败/未配置时返回 [{title:'(错误)', ...}]。
    """
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server"],
        cwd=_PROJECT_ROOT,
        env=None,  # 继承当前环境(BRAVE_SEARCH_API_KEY)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if not result or not result.content:
                return []
            # TextContent 第一个元素的 text 字段是 JSON 字符串
            try:
                return json.loads(result.content[0].text)
            except (json.JSONDecodeError, IndexError, AttributeError):
                return [{"title": "(错误)", "url": "", "snippet": "failed to parse MCP response"}]
