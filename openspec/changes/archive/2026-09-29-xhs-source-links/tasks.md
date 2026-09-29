# Tasks

## 1. 实现

- [x] 1.1 改 `app/rag/pipeline.py` `_source_url()`:把 `web` / `xhs` 合并分支拆开,`xhs` 分支从 `d["metadata"]["xsec_token"]` 取 token,非空时返回 `{file_dir}?xsec_token={token}&xsec_source=pc_feed`,为空 / 缺 metadata 时退回裸 `file_dir`,`file_dir` 缺失仍 `null`;同步更新函数 docstring 的映射规则说明(design D1/D2/D3)。验证:`conda run -n rag python -c` 内联构造三条样例文档(带 token / 缺 token / web)调 `_source_url`,输出分别为带参链接 / 裸链 / 原 URL

## 2. 端到端验证(项目无测试框架,按惯例起服务手动调 API)

- [x] 2.1 确认服务在 8011 跑着(uvicorn --reload 会热加载),前端选「小红书」模式提问,curl `POST /chat/stream` 抓 `meta` 事件,确认 `source_type=xhs` 各条 `url` 形如 `https://www.xiaohongshu.com/explore/<feed_id>?xsec_token=<token>&xsec_source=pc_feed`
- [x] 2.2 浏览器打开 2.1 拿到的任一 `url`,确认直达笔记正文页而非「笔记暂时无法浏览」/登录墙;前端来源行点击行为同路径生效
- [x] 2.3 查 `GET /sessions/<id>/messages`,确认新落库 sources 的 `url` 已带 token(历史快照固化);旧会话(如 40)消息保持裸链、前端渲染不报错(旧数据兼容)
