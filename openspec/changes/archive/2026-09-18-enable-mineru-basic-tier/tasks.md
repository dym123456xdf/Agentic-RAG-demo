# Tasks

> 状态说明(2026-09-18 归档前核对):本变更为 MinerU 链条中间环,多数任务的实际达成
> 由后续变更 `integrate-mineru-with-image-extraction` / `render-images-in-chat` 承接:
> CLI 形态从 `mineru parse` 演进为 `mineru-kit parse`,产物布局从顶层 `converted/<原文件名>.md`
> 演进为 `converted/<stem>/<stem>.md`。任务 2.2(转换前删旧产物)被最终定稿的
> "产物已存在直接复用"语义(render-images-in-chat)明确取代,不再适用。

## 1. MinerU 配置启用 parse-server

- [x] 1.1 `mineru config set parse_server.local.mode managed` + `mineru config set parse_server.local.managed_tier basic`。验证:`mineru config show | grep parse_server.local` 显示 mode=managed、managed_tier=basic
- [x] 1.2 `mineru server restart` 让 parse-server 跟随启动。验证:`mineru server status` 含 parse-server running 行(tier=basic)。(后续 basic tier 出图验证依赖此步,间接证实)

## 2. loader.py 切到 basic tier

- [x] 2.1 `app/rag/loader.py::convert_to_markdown` 把 `--tier flash` 改为 `--tier basic`。验证:grep 出 `tier basic` 不再含 `tier flash`。(最终由 `integrate-mineru-with-image-extraction` 以 `mineru-kit parse --tier basic` 形态落地,见 loader.py 现行实现)
- [ ] 2.2 ~~同一函数起首删除旧 `converted/<name>.md`~~(被取代:最终语义为产物已存在直接复用,详见 render-images-in-chat 的布局重构)

## 3. 端到端验证

- [x] 3.1 删旧 `converted/尚硅谷-01-LangChain概述.pdf.md`,重传 PDF,基本后台跑完转换。验证:响应 `chunks_ingested > 0`,`converted/<name>.md` 非空且包含真实图片引用。(实际验证由后续变更的端到端任务覆盖:render-images-in-chat 5.2-5.4)
- [x] 3.2 管理页"查看转换结果"弹层显示真实图片。验证:浏览器打开 `static/manage.html` → 文件列表 → 点"查看转换MD",弹层里 image block 渲染成实际图片而非 alt 文字。(由 integrate-mineru-with-image-extraction 4.3 覆盖)
- [x] 3.3 真实问答含图片上下文(可选:仅验证 RAG 链路不挂)。验证:`POST /chat` 提交 PDF 内容相关问题,响应 200、`sources` 非空、`answer` 含具体事实。(由 render-images-in-chat 5.3 覆盖)

## 4. 回滚路径

- [x] 4.1 文档/注释:`loader.py` 头部 docstring 与 `convert_to_markdown` 的 CLI 选型注释已写明当前 `mineru-kit parse --tier basic`,回滚改 tier 参数即可
