---
paths:
  - app/core/mcp_client.py
  - app/core/config.py
  - app/api/config.py
  - app/api/chat.py
  - mcp_server/**
---

# MCP 双 transport 规则

- **自建服务** `mcp_server/server.py`:Brave Search web_search 工具,stdio transport
- **外部** xiaohongshu-mcp:小红书搜索,Streamable HTTP,独立部署(默认 `http://127.0.0.1:18060/mcp`)

## 小红书模式前置条件

- 需独立部署 xiaohongshu-mcp(二进制 / Docker)并扫码登录(跑 `xiaohongshu-login`);本服务**不做**该服务的部署与登录
- `.env` 配 `XHS_MCP_ENABLED=true` 后,本服务启动期只校验 URL 非空、不做网络探测
- 服务未起 / 未登录 / 超时(60s)时小红书提问**降级为空结果**,答案如实说「不知道」
- **同账号互踢**:同一小红书账号在多处网页端登录会互踢登录态 —— 服务侧跑无头浏览器时,别在别的浏览器 / 设备同时登着同账号网页端

## 部署级主开关

`GET /api/config`(`app/api/config.py`)返回 `{web_search_enabled, xhs_enabled}` 两个布尔,前端加载时据此决定「联网搜索 / 小红书」选项是否渲染,两者均 false 时下拉整体隐藏;该路由只读、不含任何密钥
