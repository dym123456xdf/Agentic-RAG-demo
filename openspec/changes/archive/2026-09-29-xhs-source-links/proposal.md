# Proposal

## Why

`chat-source-links` 已让参考来源可点击,但小红书来源点开到不了笔记:小红书对搜索来源的笔记链接强制校验 `xsec_token`,而召回侧拼的是裸链 `https://www.xiaohongshu.com/explore/<feed_id>`(token 被存进 `metadata.xsec_token`「留给未来」),浏览器打开只会得到「笔记暂时无法浏览」/登录墙。实测落库历史(会话 40)确认 xhs 来源 `url` 全部是裸链 —— 链接渲染了,却跳不过去。

## What Changes

- **xhs 来源 URL 补 token**:`app/rag/pipeline.py` `_source_url()` 的 `xhs` 分支在 `file_dir` 基础上追加 `?xsec_token=<token>&xsec_source=pc_feed`(`token` 取召回规范化时已存入 `metadata` 的 `xsec_token`);格式与上游 xiaohongshu-mcp `makeFeedDetailURL`(`feed_detail.go`)完全一致。`xsec_source` 用上游同款 `pc_feed`。
- **缺 token 降级不劣化**:`metadata.xsec_token` 缺失 / 为空时退回裸链(与现状同形,不比今天差);`file_dir` 本身缺失仍为 `null`。
- **改动面收敛在一处**:召回侧 `_normalize_xhs_item` 不动(`file_dir` 保持裸链,doc_id / 日志 / prompt 不掺 token);前端不动(链接渲染已存在,`url` 非空即渲染);web / vector 分支不动;落库随 `url` 字段自然携带完整链接,历史回溯原样返回。
- **旧历史不回填**:本变更前落库的 xhs 来源只有裸链、无 token 可补,保持现状(可点但打不开),不做迁移。

## Capabilities

### New Capabilities

(无)

### Modified Capabilities

- `chat-streaming`: 「答案来源携带 0-1 置信度」需求中 xhs 的 `url` 映射规则变更 —— 由「`file_dir` 直接透出(裸笔记链接)」改为「裸链 + `xsec_token` / `xsec_source` 查询参数,token 缺失退回裸链」,并新增对应场景。

## Impact

- **代码**:仅 `app/rag/pipeline.py` 的 `_source_url()`(约 5 行改动);无新依赖、无配置项、无前端改动。
- **兼容性**:API 契约不变(`url` 仍为 0 或 1 字符串,可为 `null`),旧前端 / 旧数据行为不变。
- **已知限制**:xsec_token 有时效性(数小时到数天),历史消息里的链接过期后退化为现状行为(打开见墙);不做过期检测与回填。
