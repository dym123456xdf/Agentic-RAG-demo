# Design

## Context

现状链路全同步:chat 路由 → pipeline.query()(pre 3 次 LLM + 融合召回 + BGE 重排 + 生成),前端 fetch 等全量 JSON。等待 = 全程串行,且 BGE 重排冷启 ~13s、生成 max_tokens=800,体感 20s+。来源 `score` 是 BGE 原始 logit(约 -10~10,无界),UI 直接 `score=${s.score}` 展示,套阈值无意义。约束:前端零依赖原生 JS;M3 流式会吐 `think` 推理块(现有 `strip_thinking` 只支持整段文本);落库尽力而为(chat.py D4);`POST /chat` 需保留(管理页等旧调用方)。

## Goals / Non-Goals

**Goals:**
- 首字延迟大幅下降:检索+重排完成即推 meta(来源可见),答案逐字流出。
- 来源带 0-1 置信度;主证据 <0.6(可配)显示友情提示。
- 非流式 `/chat` 保留,来源同样带 confidence,新旧前端兼容。

**Non-Goals:**
- 不引入 markdown 渲染库(答案仍纯文本 + 图片白名单渲染)。
- 不改检索/重排/入库链路,不做检索质量优化。
- 管理页历史回溯不走流式(只读展示,保持现状)。
- 不做 `think` 块的可选透出(产品上就不该给用户看)。

## Decisions

### D1: 新接口 `/chat/stream`,SSE 事件序列 meta → delta* → done / error

请求体与 `/chat` 相同。事件为 `data: {json}\n\n` 帧(标准 SSE 帧格式;前端是 POST + fetch,EventSource 不可用,故前端手动解析,但帧格式保持 SSE 以便 curl/wscat 直接观测):

```
event 帧:
  data: {"type":"meta","sources":[...含 confidence],"confidence":0.83,"low_confidence":false,"threshold":0.6,"meta":{...}}
  data: {"type":"delta","text":"..."}        (N 条)
  data: {"type":"done","answer":"全文"}
  data: {"type":"error","message":"..."}      (异常路径,与 done 二选一)
```

- 备选 1(NDJSON):解析更简单,但 curl 观测与未来切 EventSource 不友好;SSE 帧解析也不难(按 `\n\n` 切、剥 `data: ` 前缀)。选 SSE。
- 备选 2(delta 里夹来源):来源在生成前已确定,合并进 meta 一条推完,前端代码最少。
- meta 里冗余一个顶层 `confidence`(= top1 置信度)供前端提示判断,避免前端再算一遍。
- 会话不存在/问题为空的校验失败发生在流开始前,按普通 HTTP 404/400 返回(非流式错误),进入流后的运行时错误才用 `error` 事件。

### D2: 生成器流式 + 部分流 think 过滤器

`Generator.generate_stream(query, nodes)` 返回 `(iter[str], sources)`:sources 在流开始前就构建好(meta 事件要用),迭代器逐块 yield 清洗后的答案文本;迭代完内部累计全文供落库。

- 用 `OpenAILike.stream_chat`(llama-index 自带,底层 OpenAI client `stream=True`),与现有 `chat()` 同客户端,只是换调用方式。
- M3 流式会把 `think...` 推理块混进 delta。整段 `strip_thinking` 不可用(看不到后文),需部分流过滤:
  - 持有缓冲;每 push 一个 chunk:先对缓冲做 `_THINK_RE.sub` 剥掉**已闭合**的块;再看缓冲尾部是否有 `<` 开头且是 ` think` 的前缀(未闭合,可能还要增长),有则滞留缓冲不发出;其余全部发出。
  - 流结束 flush 时:若缓冲残留未闭合的 ` think` 段,直接截掉(推理块没写完整,不留给用户)。
  - 非 think 的普通 `<`(如答案里 "3 < 5")在尾部窗口内只有是 ` think` 前缀才滞留,不影响正文即时性。

### D3: 置信度 = sigmoid(BGE 原始分)

BGE cross-encoder logit 无界,sigmoid 归一到 0-1 后 0.6 对应 logit≈0.41,语义上"较相关",阈值可解释。

- `post.py` 重排后:`n.confidence = round(1/(1+exp(-s)), 4)`;`n.score` 保留原 logit(兼容)。
- `generator.py` sources 构建时带出 `confidence`(非流式 `/chat` 与流式 meta 共用同一 sources 结构)。
- 无召回/重排空列表时不发 confidence(meta 事件 sources 为空,顶层 confidence 缺省不出现,前端不显示提示)。
- 备选 1(直接用原 retrieval distance 归一化):否决 —— distance 口径随入库向量变,且 COSINE distance 与相似度反向,语义混乱(见 CLAUDE.md 硬约束)。
- 备选 2(让 LLM 自评置信度):否决 —— 主观、不稳定、多一次 LLM 成本。

### D4: 阈值与提示文案

`Config.CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))`,阈值判断在服务端做(meta 事件多带一个布尔 `low_confidence` 或前端拿 confidence 与写死的 0.6 比?)—— **服务端判断**:阈值是服务端配置,提示触发点随 meta 事件下发布尔 `low_confidence`,前端只负责显示,避免前后端阈值漂移。

> **决策修订**:初版默认 0.8 (logit≈1.39) 在 BGE 实际打分中过于保守 —— 即使 BGE 判为几乎满分 (logit≈1.0),sigmoid 归一也只到 0.73,sigmoid 在 logit≥1 区间饱和使 0.8 阈值几乎触不到 high_confidence 路径。下调到 0.6 (logit≈0.41) 反映 BGE 的真实打分分布,既保留"提示需有信息量"的初衷,又让高置信度路径在常规相关片段下能正常触发。

- 文案(前端固定模板,见 `static/app.js` 低置信度友情提示函数):`参考置信度 {confidence}({threshold} 及以上较可靠),答案可能不够可靠,建议核对原文档。`
- 主证据 = 置信度最高一条(top1 已按重排分排序,sources[0]);不取 min(5 条里混一条弱的不拖全局)。

### D5: 前端流式渲染

`send()` 改走 `POST /chat/stream` + `fetch` body 流式读:

```
bot 气泡创建(占位文案"检索中…")
  meta   -> 占位文案换成(low_confidence ? 提示条) + 来源块(逐条:来源名 + 置信度)
  delta* -> 追加进答案 span(每帧重跑 escapeHtml + 图片白名单渲染,
            未完成句法留在文本里,闭合后自然变图 —— 白名单正则只匹配完整引用)
  done   -> 定格,自动滚底;发送按钮解禁
  error  -> 气泡变 error 样式 + 错误文案
```

- 图片语法在流中可能半截出现(`![a](/c`),`renderChatImages` 的正则要求完整 `![...](/converted/...)`,半截保持文本,闭合后重渲染变图 —— 无需特殊处理。
- 每帧重渲染成本:答案上限 800 token,文本量小,可忽略。
- 历史回显(`messageHtml`)不动;旧消息 sources 缺 confidence 时,来源行不显示置信度数值(容错:`s.confidence != null` 才渲染)。
- 取消/切会话:不做请求中断(原实现也没有),流读完即止;切会话清空 chatEl 不影响后台 fetch(数据仍落库)。

### D6: 落库

`done` 后**只在 done 时落库**,整条答案 + sources(含 confidence) + meta(调试 meta + `confidence` / `low_confidence` / `threshold` 三字段,与流式接口同一形态,见 chat.py 落库逻辑);与现状"生成完整答案后尽力落库"一致。error 路径不落库(半成品答案进历史会污染后续改写上下文)。

## Risks / Trade-offs

- [OpenAILike 流式行为] → 实施首任务先写最小脚本验证 stream_chat 可用性与 chunk 形态,不可用则 fallback 到直接用 OpenAI SDK 流式(同一凭据)。
- [think 过滤器边界 case(正文含 " think" 字面量)] → 流式 `ThinkStreamFilter` 与现有整段 `strip_thinking` 行为一致(都只剥完整 `<think>...</think>` 标签,不剥裸 " think" 字面量),不新增风险。
- [meta 早推但生成失败] → 前端已显示来源,收到 error 后气泡保留来源 + 错误提示,可接受(来源本身是有效信息)。
- [sigmoid 后阈值语义漂移(换重排模型)] → 阈值可配,且文档在 config 注释里写明口径。

## Migration Plan

1. 合码后重启服务。
2. 前端自动切流式接口;`/chat` 旧接口保留,无数据迁移(MySQL JSON 列自动带新字段)。
3. 回滚:revert 代码即恢复原阻塞 fetch + 无 confidence 展示,数据层无需回滚(旧前端读不到 confidence 字段自然忽略)。
