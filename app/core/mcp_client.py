"""MCP 客户端封装 —— 双 transport:stdio 自建服务 / HTTP 外部服务。

stdio(自建 Brave 搜索 server):
- LangGraph 节点内拉起 `python -m mcp_server` 子进程,同进程无端口监听,部署简化;
- 每次 web_search 节点触发都 spawn 子进程(FastAPI 主进程启动略慢),但该节点
  仅在联网模式下挂载,默认关闭,不影响常规查询性能。

HTTP(外部 xiaohongshu-mcp,Streamable HTTP):
- 外部服务由用户独立部署(二进制/Docker,默认 http://127.0.0.1:18060/mcp)+ 扫码登录,
  生命周期与本服务解耦;客户端按「每次调用独立建连」处理(建连 + initialize 握手 +
  call_tool + 关闭),与 stdio 的每调用生命周期同构,不维持持久会话。
- 坑(mcp 2.2.0):Streamable HTTP 客户端是 `streamable_http_client`(下划线命名,
  旧版叫 `streamablehttp_client`),headers 不直接入参,需经
  `create_mcp_http_client(headers=...)` 造 httpx2 客户端传入。
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


async def call_tool_http(url: str, tool_name: str, arguments: dict[str, Any],
                         headers: dict[str, str] | None = None) -> list[dict]:
    """Streamable HTTP 调外部 MCP 服务工具,解析 TextContent JSON 返回 list[dict]。

    每次调用独立建连(建连 + initialize 握手 + call_tool + 关闭),不在服务进程内
    维持长连接会话。headers 里的 Authorization: Bearer <token> 用于外部服务鉴权。
    抛异常由调用方(xhs_search 节点)捕获并降级为空路 —— 本函数不吞异常。
    """
    # 延迟 import:mcp 2.x 的 Streamable HTTP 客户端在 streamable_http 模块,
    # 且 headers 需经 create_mcp_http_client 造 httpx2 客户端(不直接入参)
    from mcp.client.streamable_http import streamable_http_client

    http_client = None
    if headers:
        from mcp.client.streamable_http import create_mcp_http_client
        http_client = create_mcp_http_client(headers=headers)
    try:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if not result or not result.content:
                    return []
                # 取第一个 TextContent 的 text(可能 JSON 字符串);其它内容块跳过
                for block in result.content:
                    text = getattr(block, "text", None)
                    if text is None:
                        continue
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return []
                return []
    finally:
        if http_client is not None:
            await http_client.aclose()
