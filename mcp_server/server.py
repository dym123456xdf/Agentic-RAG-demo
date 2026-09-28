"""MCP server —— 暴露 web_search 工具,后端 Brave Search API。

⚠️ 本文件按 mcp SDK **2.x** API 编写(MCPServer + @server.tool()):
   v1 的 `Server` + `@server.list_tools()` / `@server.call_tool()` 装饰器在 2.x 已移除,
   升降级 SDK 时注意同步改这里(2.x 迁移指南:https://py.sdk.modelcontextprotocol.io/v2/migration)。

工具契约:
  输入:{query: str, count: int = 5}(schema 由函数签名类型注解自动生成)
  输出:str —— [{title, url, snippet}, ...] 的 JSON 字符串,由 SDK 包成 TextContent 返回

兜底:无 BRAVE_SEARCH_API_KEY 或网络/鉴权失败时返回提示性 JSON,不抛未捕获异常。
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer


server = MCPServer("rag-web-search")


def _format_brave(payload: dict) -> str:
    """Brave Search JSON → [{title, url, snippet}, ...] 文本块(JSON 序列化)。"""
    results = (payload.get("web") or {}).get("results") or []
    items: list[dict[str, Any]] = []
    for r in results:
        items.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("description", ""),
        })
    return json.dumps(items, ensure_ascii=False)


@server.tool()
async def web_search(query: str, count: int = 5) -> str:
    """用 Brave Search API 检索最新网页信息。

    Args:
        query: 检索关键词。
        count: 返回条数(1-20)。
    """
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        return json.dumps(
            [{"title": "(未启用)", "url": "", "snippet": "BRAVE_SEARCH_API_KEY not configured"}],
            ensure_ascii=False,
        )
    query = query.strip()
    if not query:
        return json.dumps([], ensure_ascii=False)

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": count},
                headers={"X-Subscription-Token": api_key},
            )
            resp.raise_for_status()
            return _format_brave(resp.json())
        except Exception as e:  # 网络 / 鉴权失败统一兜底为文本,不抛
            return json.dumps(
                [{"title": "(错误)", "url": "", "snippet": f"brave search failed: {e!s}"}],
                ensure_ascii=False,
            )


def main() -> None:
    """stdio 入口:python -m mcp_server 时被 __main__.py 调用。"""
    import asyncio

    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    sys.exit(main())
