# Design

## Context

来源数据的定位信息在管道各环节的形态(实测代码确认):

- **web 召回**(`NodeWebSearch`):`file_dir = it.get("url")` —— 原网页 URL。
- **xhs 召回**(`NodeXhsSearch` / `_normalize_xhs_item`):`file_dir = https://www.xiaohongshu.com/explore/<feed_id>` —— 笔记链接(需登录态的小红书网页,外部服务可用即链接有效)。
- **kb 召回**(`NodeEmbeddingSearch` / `NodeHydeSearch` → `milvus_hybrid.hybrid_search`):hit 带 `doc_name`(原文件名如 `报告.pdf`)+ `file_dir`(`converted/<stem>/` MinIO 前缀)。MinerU 转换产物对象 key 有固定约定 `converted/<stem>/<stem>.md`(见 `ingest_nodes.py` NodePdfToMd:staging 落 `<stem>/<stem>.md`,`import_milvus` 整目录上传 MinIO 保持前缀;`upload.py _has_converted` 用 `minio_client.object_exists(f"converted/{stem}/{stem}.md")` 判定)。`/converted/{stem:path}` 代理路由(converted.py)按该 key 流式回放 MinIO。

当前 `_build_sources`(pipeline.py)只取 `doc_name / text / score / confidence / source_type`,`doc_name` 与 `file_dir` 被丢弃 —— 链接信息其实一直都在 chunk 上,只是没透出。

前端唯一渲染点 `srcItemHtml`(app.js,首页流式 tailHtml 与管理页历史 details 共用)当前输出 `[#n] <b>来源名</b> 置信度 … + 摘要`。

## Goals / Non-Goals

**Goals:** 来源项带 `url`(可为 null);前端来源名为新标签跳转链接(web/xhs/kb 三类);缺定位信息或旧数据不渲染链接、不报错;视觉随既有设计令牌,两页一致。

**Non-Goals:** 不做 xhs 详情补全、不做 chunk 级锚点定位、不做服务端链接可达性探测、不改置信度 / meta / 低置信度提示任何既有行为。

## Decisions

### D1:映射逻辑放 `_build_sources` 内联(单一出口),不进图节点

来源构造本就是「管道收尾整形」而非业务节点职责 —— `cliff_rerank` 产 `reranked_docs`(带 `file_dir` / `doc_name` / `source_type`),`_build_sources` 是唯一把 rerank 结果转成 API 来源项的地方,非流式 `_build_response` 与流式 `query_stream` 共用。在这里按 `source_type` 分支取 URL:

```python
def _source_url(d: dict) -> str | None:
    st = d.get("source_type", "vector")
    file_dir = (d.get("file_dir") or "").strip()
    doc_name = (d.get("doc_name") or "").strip()
    if st in ("web", "xhs"):
        return file_dir or None          # 召回时已写好原 URL / 笔记链接
    # vector(知识库): 按 MinerU 产物 key 约定拼转换 MD 代理 URL
    stem = Path(doc_name).stem if doc_name else ""
    if file_dir and stem:
        return f"/converted/{stem}/{stem}.md"
    if stem:
        return f"/converted/{stem}/{stem}.md"
    return None
```

`url` 进 `_build_sources` 返回 dict、进 `SourceItem` 模型,一次改动两出口同时生效;落库 JSON 自然带 url,历史回显免费获得链接。

### D2:kb 链接不查 MinIO 存在性,404 即弱链接

逐条 `object_exists` 会给每次问答 / 历史渲染加 MinIO IO(且流式 meta 要求检索完成即推,不能阻塞)。MinerU 关闭时或 .md/.txt 直读通道入库的文件没有 `converted/<stem>/<stem>.md` 对象,点击得到代理路由 404 文本页 —— 用户上下文已给出(来源名 + 摘要 + 置信度),可接受。管理页「查看转换MD」按钮本就按 `has_converted` 显隐,是离线核对路径。

stem 取 `doc_name` 去后缀(`Path(doc_name).stem`),与入库 `file_title` 同义(file_title 即 stem)。注意 `doc_name` 是**原文件名**(含后缀,如 `报告.pdf`),拼接前必须去后缀。

### D3:前端只改 `srcItemHtml` 一处,链接行为统一

`srcItemHtml` 是首页流式(top3)与管理页历史(全量)的共用渲染函数,在这里改一次两页同时生效。规则:

- `s.url` 非空:来源名渲染为 `<a class="src-link" href target="_blank" rel="noopener">` 并跟在外链图标后;`#n` 序号与摘要行不变。
- `s.url` 为空 / 缺(旧数据):现状纯文本,零回归。
- URL 经 `escapeHtml` 转义进 `href` 属性(与 alt/src 同规则防属性逃逸);`target="_blank"` + `rel="noopener"` 防反向 tab 劫持。
- 外链图标加进 `SVG` 常量(与 file/clip 等同一 stroke 风格),颜色走 `--accent`,hover `--accent-hover`,不硬编码内联样式(ui-style 既有约束)。

### D4:旧数据兼容 = 缺省语义

MySQL 历史消息的 `sources` JSON 无 `url` key(本变更前落库的),前端 `s.url` 为 `undefined` → 走 D3 第二分支不渲染链接。无需数据迁移。

## Risks / Trade-offs

- [kb 弱链接(MinerU 关闭 / md 直读文件 404)] → 可接受:来源名 + 摘要仍完整;管理页 has_converted 提供离线核对。
- [xhs 笔记链接需登录态才可见正文] → 属外部服务使用约束(同账号互踢已写进 CLAUDE.md),本变更不放大该约束,只是把链接给出去。
- [doc_name 被人为改成与 stem 不一致(极端情况)] → 入库幂等以 doc_name 为准,file_title 恒为原 stem,正常流程不会发散;拼不出即 url=None。

## Migration Plan

纯增量字段,无数据迁移;旧历史消息渲染降级纯文本(现状行为)。回滚 = 撤掉 `url` 字段与前端链接渲染即可,无外部依赖。
