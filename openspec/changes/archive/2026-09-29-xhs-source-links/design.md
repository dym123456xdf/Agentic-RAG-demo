# Design

## Context

`chat-source-links` 已建立来源 → `url` → 前端 `<a target="_blank">` 的完整链路,映射集中在 `app/rag/pipeline.py` `_source_url()`(web/xhs 透出 `file_dir`,vector 拼 `/converted` 代理路径)。xhs 召回侧 `_normalize_xhs_item()` 把笔记链接以裸链写入 `file_dir`,同时把 `search_feeds` 返回的 `xsecToken` 存进 `metadata.xsec_token`(注释明言「留给未来详情补全」)—— 本次就是补这个口。链路通畅性已实测:会话 40 落库 sources 的 `url` 均为裸 `explore/<feed_id>`,token 在 metadata 里一路存活到 `_build_sources` 的输入(rrf / cliff_rerank 均以 `{**c}` 整字典透传)。

上游事实依据:xiaohongshu-mcp 自身访问笔记页用的就是 `https://www.xiaohongshu.com/explore/<feed_id>?xsec_token=<token>&xsec_source=pc_feed`(`xiaohongshu/feed_detail.go` `makeFeedDetailURL`),本设计直接对齐。

## Goals / Non-Goals

**Goals:**

- xhs 来源链接点开直达笔记页,不再落「笔记暂时无法浏览」/登录墙。
- 改动收敛在 `_source_url()` 一处;召回侧、前端、API 契约、web / vector 分支零改动。

**Non-Goals:**

- 不做 token 时效检测、过期回填、逐条重取(见 D4)。
- 不做 xhs 笔记详情补全(`get_feed_detail`,摘要仍只有标题 + desc)。
- 不动召回规范化的字段结构(`file_dir` 语义保持「裸笔记链接」)。

## Decisions

### D1:token 拼接放 `_source_url()`(出口层),不改召回侧

备选是让 `_normalize_xhs_item` 直接把带 token 的完整链接写进 `file_dir`。否决:`file_dir` 还有两个非展示用途 —— `_doc_id_of()` 用它拼稳定 doc_id(`xhs::<file_dir>`),生成节点 prompt 与日志也以 doc_id / doc_name 标识来源。token 是「一次性的访问凭证」而非「笔记身份」,掺进 `file_dir` 会让 doc_id 随 token 漂移、日志难读。放在 `_source_url()`(该函数职责就是「把文档映射为可跳转链接」)语义最正,且 token 从 `metadata.xsec_token` 现取,链路已验证通畅。

### D2:URL 格式与上游逐字对齐,token 原样拼接、不做百分号编码

`?xsec_token=<token>&xsec_source=pc_feed`,`xsec_source` 取上游同款 `pc_feed`。token 实测为 URL-safe base64 变体(含 `-` `_` `=`):`=` 落在 query value 中按标准解析属于值的一部分,上游 Go 端也是原样 `fmt` 拼接且工作正常;引入百分号编码反而与上游行为不一致,多一个变量。`xsec_source` 若与 token 的签发上下文不匹配会被小红书拒绝,`pc_feed` 正是 feed 流来源的配对值,不自行发明。

### D3:缺 token 降级为裸链,而不是 `null`

上游某条 feed 没返回 `xsecToken` 时,退回裸链(与现状同形)。置 `null` 会让前端连「这是个笔记链接」都丢掉,严格劣化;裸链至少保留跳转尝试的可能。

### D4:落库即快照,不检测时效

`xsec_token` 有时效(数小时到数天),历史消息里的链接过期后打开见墙 —— 与现状完全一致,不做回填(旧记录根本没有 token 可补)、不做检测(需逐条回调小红书 / MCP,收益不抵开销)。新问答天然携带新 token。

## Risks / Trade-offs

- [token 过期,历史链接逐步失效] → 接受:退化即现状;时效内(当轮 / 近期)点击是主要场景。
- [上游改 token 字段名或 URL 格式] → 字段侧 `_normalize_xhs_item` 已有多字段 fallback(`xsecToken` / `xsec_token`);URL 格式侧与上游 `makeFeedDetailURL` 同进退,跟进改一处常量即可。
- [小红书收紧 `pc_feed` 放行策略] → 与上游 xiaohongshu-mcp 共同面对;跟进上游取值。

## Migration Plan

无迁移:部署即生效,新问答的 `url` 自带 token;旧历史保持裸链现状。回滚 = revert `_source_url()` 单函数改动,无数据影响。
