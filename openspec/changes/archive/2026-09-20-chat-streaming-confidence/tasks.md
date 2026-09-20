# Tasks

## 1. 置信度归一化(post / generator / config)

- [x] 1.1 `app/core/config.py` 新增 `CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))`,注释写明口径(重排 logit 经 sigmoid 归一,阈值 0.6 对应 logit≈0.41)。验证:缺省与 .env 覆盖两种读法
- [x] 1.2 `app/rag/post.py` 重排后给每条 node 写 `n.confidence = round(1/(1+math.exp(-s)), 4)`(s 为 BGE 原始分;注意 score 可能为负,exp 溢出用 try/except 或 clamp,负 700 以下直接 0.0),`n.score` 保留原值。验证:构造 3 条不同 logit(如 2.0/0.5/-3.0)走一遍 process,打印 confidence 与手算一致(≈0.88/0.62/0.05)
- [x] 1.3 `app/rag/generator.py` sources 构建处每项增加 `"confidence": getattr(n, "confidence", None)`(容错:post 未跑过时为 None,前端隐藏)。验证:打印 sources 结构含 confidence 键

## 2. 生成器流式(generator / llm)

- [x] 2.1 先写最小验证脚本(不进仓):用现有 `LLMClient(role="main")` 调 `OpenAILike.stream_chat`,打印 chunk 类型与内容形态,确认 M3 流式可用、think 块是否混入。验证:脚本跑通,拿到逐块文本;(若 stream_chat 不存在/不可用,改用 openai SDK 直接流式,同一凭据,记录到 design)
- [x] 2.2 `app/rag/generator.py` 新增 `generate_stream(query, nodes) -> tuple[Iterator[str], list[dict]]`:sources 流前构建(同 1.3);LLM 流式逐块 yield;内部累计全文
- [x] 2.3 部分流 think 过滤器(design D2):缓冲 + 已闭合块 sub 剥除 + 尾部 ` think` 前缀滞留 + 结束 flush 截断未闭合段;写 5 个手算用例(块跨 3 chunk、正文含 " think" 字面量、尾部滞留 "3 < 5" 不误伤、未闭合尾、正常无 think)逐一断言。验证:用例全过
- [x] 2.4 `app/rag/pipeline.py` 新增 `query_stream(question, history)` 生成器:yield 事件元组 `("meta", {sources, confidence: top1 或 None, low_confidence: bool, threshold: float, meta: dict})` → N 个 `("delta", text)` → `("done", full_answer)`;pre/retrieve/post 沿用同步调用;生成异常 yield `("error", message)` 后 return。验证:临时脚本跑一遍事件序列,meta 在首个 delta 之前、done 文本 == 各 delta 拼接

## 3. 流式路由(chat / config)

- [x] 3.1 `app/api/chat.py` 新增 `POST /chat/stream`:校验(空问题 400、会话不存在 404 —— 流开始前按普通 HTTP 返回);校验通过后进 pipeline.query_stream,StreamingResponse 包装为 SSE 帧(`data: {json}\n\n`);done 后尽力落库(问题 + 完整答案 + sources(含 confidence) + meta;落库失败只告警,不影响已推完的流,同现状 D4);error 事件不落库。验证:curl -N 调接口,肉眼确认事件序列与帧格式
- [x] 3.2 非流式 `POST /chat` 的 sources 自动带 confidence(经 1.3 的同一构建路径),SourceItem 模型加 `confidence: float | None`。验证:curl 旧接口,响应 sources 含 confidence,原有字段不变

## 4. 前端流式(index.html / app.js / style.css)

- [x] 4.1 `static/index.html` 的 `send()`:改 fetch `POST /chat/stream` + 读 body stream,按 `\n\n` 切帧、剥 `data: ` 前缀解析 JSON;bot 气泡先占位("检索中…"),meta 帧换来源块(逐条 来源名 + 置信度 数值,None 不显示)+ low_confidence 时渲染提示条(文案含 confidence 与 0.6 阈值语义),delta 帧追加答案(每帧重跑 escapeHtml + renderChatImages,滚底),done 定格解禁, error 气泡错误样式。验证:浏览器 Network 可见逐帧到达,答案逐字出现
- [x] 4.2 `static/app.js`:来源行渲染加置信度(`s.confidence != null` 才显示,标签由 `score=` 改 `置信度=`,原始 score 不再展示);新增提示条渲染函数(或内联进来源块)。验证:旧历史消息(无 confidence)渲染不报错、不显示数值与提示
- [x] 4.3 `static/style.css`:提示条样式(弱警示色,正文对比度 ≥4.5:1,与 ui-style 的 token 一致)与"检索中…"占位样式。验证:提示条文字可读、不撑破气泡
- [x] 4.4 历史回显路径(`messageHtml` collapsed 分支)确认无需改动也能显示新 confidence(走 4.2 的来源行渲染)。验证:切到带新答案的旧会话,来源置信度正常显示

## 5. 整体验证(起服务手动调)

- [x] 5.1 起服务(/opt/anaconda3/envs/rag/bin/python -m uvicorn main:app,端口 8011);浏览器首页提问:确认"检索中…"→ 来源块先出 → 答案逐字出;来源带置信度
- [x] 5.2 低置信度路径:问一个知识库外的问题(如"量子计算的最新突破"),确认 top1 confidence < 0.6 时出现友情提示条;再问一个库内明确主题确认不出现
- [x] 5.3 回归:非流式 `POST /chat` 响应含 confidence 且行为不变;管理页历史回溯正常;新建会话落库后管理页可见新答案与 confidence
- [x] 5.4 负路径:会话不存在 POST /chat/stream 返回 404(非流帧);空问题 400
- [x] 5.5 .env 加 `CONFIDENCE_THRESHOLD=0.9` 重启,确认阈值随配置生效(提示触发边界上移),验证后改回 0.6

## 6. 实施中发现的 bug(已修)

- [x] 6.1 `app/rag/post.py`:`NodeWithScore` 是 pydantic 模型,直接 `n.confidence = ...` 抛 `"object has no field"`,改用 `n.__dict__["confidence"] = ...` 绕过校验(getattr 仍可读,model_dump 不含此字段符合预期)
- [x] 6.2 `app/core/llm.py`:`strip_thinking` 在 cleaned 为空时 `or text.strip()` 回退原文本,把完整 think 块原样泄露进 meta.rewritten / answer。删除回退;下游 `_rewrite` / `_intent` / `_expand` 都有空字符串兜底,语义不变
