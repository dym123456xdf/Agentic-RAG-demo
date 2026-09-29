# Spec Delta

## MODIFIED Requirements

### Requirement: 答案来源携带 0-1 置信度

来源列表的每一项 SHALL 携带 `confidence` 字段,为 0-1 区间的浮点(由重排模型原始分归一化得出,原始 `score` 字段保留);流式接口的 `meta` 事件与非流式接口 `POST /chat` 的响应来源列表均携带该字段。

每一项 SHALL 额外携带 `url` 字段(0 或 1 字符串,可为 `null`),为该来源可跳转的原始出处链接:

- `source_type = web`:`url` 为召回时写入的来源 `file_dir`(原网页 URL),缺失时 `null`。
- `source_type = xhs`:`url` SHALL 为可直达笔记页的小红书链接 —— 在召回写入的 `file_dir`(裸笔记链接 `https://www.xiaohongshu.com/explore/<feed_id>`)基础上追加 `?xsec_token=<token>&xsec_source=pc_feed` 查询参数,`token` 取召回时随文档 `metadata` 存储的 `xsec_token`;`xsec_token` 缺失或为空时 SHALL 退回裸笔记链接(不带查询参数);`file_dir` 缺失时 `null`。
- `source_type = vector`(知识库):`url` 按 MinerU 转换产物对象约定拼为相对路径 `/converted/<stem>/<stem>.md`,其中 `stem` = 原文件名(`doc_name`)去后缀;`doc_name` 缺失时 `null`。
- 定位信息缺失(旧数据无 `doc_name` / `file_dir`)一律映射为 `null`,该条不渲染链接。

`url` 随来源落库(JSON 含该 key),历史回溯接口原样返回;带 `xsec_token` 的链接随落库快照固化,系统 SHALL 不对该 token 做时效性检测或回填(过期后的历史链接退化为裸链现状行为)。

#### Scenario: 非流式响应带置信度
- **WHEN** 客户端调用 `POST /chat`
- **THEN** 响应 `sources` 每项含 `confidence`(0-1),原有 `score`(原始分)字段不变

#### Scenario: 非流式响应带跳转链接
- **WHEN** 客户端调用 `POST /chat`
- **THEN** 响应 `sources` 每项含 `url`(字符串或 `null`),定位信息缺失时该条 `url` 为 `null`

#### Scenario: 流式 meta 帧带跳转链接
- **WHEN** 流式接口 `POST /chat/stream` 推送 `meta` 事件
- **THEN** 该事件 `sources` 每项与 `POST /chat` 响应同形(含 `url` 字段),历史落库 JSON 同步携带

#### Scenario: 小红书来源链接直达笔记页
- **WHEN** 任一出口(流式 `meta` 事件 / 非流式响应 / 历史回溯)返回 `source_type = xhs` 且召回 `metadata` 存有 `xsec_token` 的来源
- **THEN** 该条 `url` 形如 `https://www.xiaohongshu.com/explore/<feed_id>?xsec_token=<token>&xsec_source=pc_feed`,浏览器打开能进入对应笔记页,而非「笔记暂时无法浏览」/登录墙

#### Scenario: 小红书令牌缺失降级
- **WHEN** `source_type = xhs` 的来源 `metadata` 中 `xsec_token` 缺失或为空(如上游搜索结果未返回令牌)
- **THEN** 该条 `url` 为裸笔记链接 `https://www.xiaohongshu.com/explore/<feed_id>`(不带查询参数),其余来源不受影响

#### Scenario: 旧历史兼容
- **WHEN** 渲染的历史消息来源数据缺少 `confidence` 或 `url` 字段(旧落库记录)
- **THEN** 界面正常渲染:不显示置信度数值、不显示低置信度提示、来源行保持纯文本不渲染链接,不报错
