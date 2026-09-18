# Design

## Context

见 proposal.md 的 Why。当前链路断点:`app.js messageHtml()` 只 `escapeHtml`;Milvus chunk 里是 `images/<hash>.<ext>` 相对路径(`loader.py _extract_base64_images` 生成,图片实际落在 `converted/<原文件名含后缀>/images/`,`main.py` 已挂 `/converted` 静态路由);`generator.py` 的 SYSTEM prompt 无图片约束,实测 LLM 编造过 `output/images/<40位hash>-14_0.jpg` 这类磁盘上不存在的路径。约束:前端是零依赖原生 JS;入库按文件名幂等跳过(CLAUDE.md 硬约束);`converted/` 落盘 md 是人工核对的质量凭证。

实测澄清(本变更立项期间用 mineru-kit 4.0.0 验证):`mineru-kit parse -o <dir> -f markdown` 的产物是**单个 md 文件、图片 base64 内嵌**,不产生文件夹与 pdf;"每文档一个文件夹,内含真实图片文件 + layout pdf"是顶层 CLI / webui / zip 模式的**目录产物形态**。本变更不切换解析模式(继续 `-f markdown` + base64 抽取,链路实测健康),只重构落盘的目录布局。

## Goals / Non-Goals

**Goals:**
- 聊天链路三处渲染面(首页实时、首页回溯、管理页历史)显示 `/converted/` 图片,且渲染层防注入。
- 入库文本自包含可渲染的绝对 URL,下游(检索、LLM、前端)不再需要知道图片属于哪个文件。
- 存量数据一次性重建,重建后 chunk 内引用即绝对 URL。

**Non-Goals:**
- 不做完整 markdown 渲染(标题/表格/代码块仍按纯文本显示)。
- 不清洗 MySQL 历史里的旧答案(旧路径按原文显示,属预期)。
- 不改 `converted/` 落盘格式、管理页"查看转换MD"弹层现有渲染、检索/重排链路。
- 不处理 `.md` 直传文件的图片搬运(spec 已明确不改写)。

## Decisions

### D1:入库改写放在读入后的内存层,不改落盘产物

`loader.py _load_one` 的 MinerU 分支读入 converted md 后,内存中把 `![...](images/...)` 改写为 `![...](/converted/<原文件名含后缀>/images/...)` 再返回 Document;`converted/<name>.md` 落盘文件保持相对路径。

- 备选 A(落盘时写绝对 URL):否决 —— 落盘 md 是人工核对凭证,相对路径在本地 markdown 查看器里可正常解析(与 md 同级有 `images/`),写死 `/converted/...` 后本地反而看不了;且管理页弹层 `renderMdWithImages` 的正则只匹配 `images/` 前缀,会连带失效。
- 备选 B(检索/渲染阶段按 source 拼 URL):否决 —— 答案文本经 LLM 改写后可能变形,后处理无法可靠还原归属;URL 在最上游自包含后,全链路免猜。

改写时机在产物复用路径同样生效(读盘后改写,与产物新旧无关),满足 spec 的"复用时同样改写"场景。

### D2:改写规则与 URL 形态

- 仅匹配 `![...](images/<file>)` —— 这是 `_extract_base64_images` 产出的唯一形态,不做泛化匹配。
- URL 前缀用新目录布局:`/converted/<stem>/images/<file>`(`stem` 为原文件名去后缀,见 D6)。图片目录名保持 `images/`(MinerU 惯例 + `_extract_base64_images` 既有产出形态),不改名为 `img/`。
- 中文文件名原样写入 URL,不做百分号编码:StaticFiles 与浏览器均按 UTF-8 处理,现状弹层已用同形态 URL 且可访问;文本里预编码反而与 markdown 语义不符。

### D3:前端渲染 = escape 之后白名单正则替换

`app.js` 新增共用函数(如 `renderImages(escaped)`):输入已 `escapeHtml` 的文本,把 `![alt](/converted/...)` 替换为 `<img class="chat-img" src="..." alt="...">`;alt 与 src 中的 `"` 先替换为 `&quot;`(`escapeHtml` 不覆盖引号,防属性逃逸)。`messageHtml()` 与 `manage.html` 历史回溯接入;弹层 `renderMdWithImages` 匹配的是相对 `images/`,语义不同,保持现状。

- 备选(引入 marked + DOMPurify 做完整渲染):否决 —— 为单一语法引两个外部库,与零依赖原生前端不一致;回答主体是纯文本+图片语法,够用。

### D4:prompt 约束 + 截断保护,白名单兜底

SYSTEM prompt 增加规则:参考资料中的图片引用逐字保留、不得改写或编造、资料无图不得添加。同时 `generator.py` 构建 snippet 时(现截断 200 字符)先把全文中的图片引用整条抽出、截断后完整追加到 snippet 末尾 —— 否则长引用(中文文件名可达 80+ 字符)被截在中间,LLM 拿到半截 URL 更容易脑补。

LLM 约束是概率性的,真正的安全边界是 D3 白名单:库内引用(D1 产出)必然可渲染;LLM 编造的路径不满足 `/converted/` 前缀(或指向不存在的文件),按原文显示,不出现裂图与外链加载。

### D5:清库重灌,新旧数据可共存

迁移 = drop `personal_kb` collection → 重传 `uploads/` 的 PDF(converted 产物已存在直接复用,仅花 embedding)→ 验证 chunk 文本含 `/converted/`。不先清库直接重传是无效的(同名幂等跳过)。新旧 chunk 在新旧前端下都只是"图片显示与否"的差异,无错误渲染,故迁移不需要停机一致性,做完即生效。

### D6:产物目录重构为每文档一个无后缀文件夹

落盘布局由"顶层 md + `<原文件名含后缀>/` 文件夹"改为 `converted/<stem>/<stem>.md` + `converted/<stem>/images/`。`converted_md_path()` 是唯一落盘定位点(`upload.py` 的 `has_converted` 与转换产物读取接口都经由它),改一处即全链路生效;管理页弹层图片 URL 前缀同步改为 stem(`dataset.name` 去后缀)。md 文件名取 `<stem>.md`(与文件夹同名,最直观)。

- 已知取舍:同 stem 不同后缀的文档(如 `a.pdf` 与 `a.docx`)会共用 `converted/a/` 产物文件夹,图片可能混放 —— 个人知识库场景概率极低,接受;原"带原后缀防同名冲突"的防护随顶层 md 取消而消失,不再补偿。
- 备选(文件夹名保留后缀):否决 —— 用户明确要无后缀;且与 MinerU 目录形态产物的惯例一致。
- 存量迁移:纯文件挪移(`converted/<name>.md` + `converted/<name>/` → `converted/<stem>/`),不重新转换;迁移脚本在实施任务中一次性执行。

## Risks / Trade-offs

- [LLM 仍可能改写/编造路径] → D3 白名单:非 `/converted/` 一律按文本显示;D1 保证库内引用本身可渲染,常规路径已闭环。
- [图片引用落入 200 字符截断边界] → D4 截断前抽出、截断后完整追加。
- [中文文件名的 URL 编码差异] → 与现状弹层同形态,风险低;任务含端到端验证(提问 → 图片显示)。
- [清库期间问答质量下降] → 库内只有 2 份文档、180 chunk,重建分钟级;迁移窗口内检索结果为空时回答"我不知道",可接受。

## Migration Plan

1. 合码后重启服务(改动了 loader/upload/generator/静态资源)。
2. 执行存量产物挪移:旧 `converted/<原文件名>.md` + `converted/<原文件名>/` → 新 `converted/<stem>/` 布局(纯 mv)。
3. 清空 Milvus `personal_kb` collection(drop 或全删)。
4. 管理页重传 `uploads/` 下的 PDF(产物复用,不入库转换)。
5. 验证:提问含图文档 → 答案显示图片;`/converted/<stem>/images/<hash>.jpeg` 可直接 GET;管理页弹层图片正常。
6. 回滚:revert 代码 + 把产物挪回旧布局即可,新旧 chunk 对新旧前端均无错误渲染,无需数据回滚。
