# Design

## Context

管理页(`static/manage.html`)当前上传流程 `uploadFiles()`(`static/manage.html:102`)用一次 `fetch` 把 `FormData` 推到 `/upload/files`,等响应后调 `showToast()` 显示一行汇总文字。后端入库(`app/rag/pipeline.py:89` → `app/rag/indexer.py:36`)是同步操作:落盘 → 切分 → embedding → 写 Milvus → flush,典型十几秒。期间前端无任何反馈,响应后 toast 也只说"片段数 / 跳过数",不报文件名。详见 `proposal.md - Why` 与 `specs/manage-page/spec.md`。

## Goals / Non-Goals

**Goals:**
- 入库期间给用户"正在处理"的可见反馈(Loading 遮罩 + 文件名列表)
- 结果反馈只剩两种 toast(成功 / 失败);重复上传是"值得正式打断"的语义,独立走模态弹窗(不进 toast 体系)
- 后端零改动(沿用现有响应字段 `saved` / `skipped_files` / `chunks_ingested` / `total_entities` / `detail`)
- 沿用现有 `.toast` 体系,扩展多行排版约定;`.toast.warn` CSS 备用但本变更不触发

**Non-Goals:**
- 不做真实字节级上传进度(fetch 上传阶段无法读取 progress;要走 XHR 才能暴露 upload.onprogress,本变更不做)
- 不做入库阶段细粒度进度(后端无 SSE/yield 事件;切分/embedding 是 llama-index 内部操作,改造成本场景大,不在本变更范围内)
- 不引入新的 modal 弹层组件:**复用现有 `.md-overlay` 视觉约定**(全屏遮罩 + 居中白底卡片)新建 `.dup-overlay`,不引入第三方 UI 框架
- 不动 `convert_only` 路径(那是另一语义,本变更只覆盖 `uploadFiles()` 主路径与目录入库 $("btnDir") 提示)

## Decisions

### D1: Loading 遮罩用全屏半透明 + 居中卡片 + 旋转图标

不用 inline spinner 也不用 button disabled 状态 —— 全屏遮罩能最直接告诉用户"系统在干活,别动",且能物理阻断上传区重复点击(避免用户在等待中再拖一次文件)。

**渲染位置**: 通过 JS 动态 `appendChild` 到 body 末尾(.toast 是 HTML 写死的 body 中段节点,不在末尾;loading-mask 是动态追加的),通过 class `.show` 控制显隐。
**触发**: `uploadFiles()` 入口显示遮罩,`fetch` 响应到达(成功或失败)立即隐藏。
**说明文字**: 列出本次提交的全部文件名(不做截断);文件数超过 8 个时折叠为前 8 个 + `等 N 个文件` 一项。模态 chip 列表则不折叠,改由 `max-height: 50vh` + `overflow: auto` 处理溢出(超出区域内部滚动而非截断文件名)。

**考虑过的替代**:
- 按钮 disabled + spinner: 仍然允许拖拽上传区,且不能让用户清楚"系统在做什么"
- 文件列表原地 spinner: 反馈太弱,用户会以为页面卡了

### D2: Toast 容器支持多 class 区分语义(runtime 触发两态:成功 / 错误),重复上传场景改用模态弹窗

- `.toast`(默认):成功 —— 深色字白底(`var(--text)` 底 + `--bg` 字),与现状一致
- `.toast.err`:失败 —— 红底白字(`var(--danger)` 底 + `#fff` 字)
- 前端预检命中(任一文件名已存在):**不再用 toast**,改用独立的 `dup-overlay` 模态弹窗(全屏半透明遮罩 + 居中卡片 + 标题 / 文件名 chip 列表 / 「我知道了」按钮)。toast 的 `.warn` 样式保留在 CSS 中备用,但当前不触发。

`showToast(msg, type, durationMs?)` 签名扩展,内部按 type 加 class,按 duration 设 setTimeout。runtime 触发两态:成功 2.2s、错误 6s;`"warn"` 在 JS 函数能力上支持(5000ms)但本变更不触发(模态弹窗替代了它原本要承担的"全重复"语义)。

`showDupModal(names)` 新增:接收文件名数组,渲染 `#dupOverlay` body,加 `.show`,按钮 onclick 移除 `.show`。

**为什么全重复不用 toast**: toast 自动消失,用户可能没看清文件名就错过了;重复上传是"你刚才白忙了"这种值得正式打断的反馈,弹窗确保用户主动确认。复用现有 `.md-overlay` 视觉约定(全屏遮罩 + 居中卡片)保持组件系统一致。

**考虑过的替代**:
- 用 `confirm()` 阻塞弹窗:`confirm()` 是原生阻塞弹窗,样式不可控(浏览器原生外观,与我们暖色极简体系割裂),文件名列表显示也很丑
- 沿用 warn toast 但延长到 30s:用户仍可能忽略,没有"必须确认"的语义

### D3: 重复上传模态的文件名 chip 不折叠,过长靠 `.dup-body` 内部滚动

每个文件一个 `<li>`,页面米白底(`var(--bg)` 背景 + `var(--text)` 文字)+ 圆角胶囊(`var(--radius-full)`)+ flex-wrap 自动换行,所有命中文件名全部渲染不做截断;`.dup-body` 设 `max-height: 50vh` + `overflow: auto`,超过视口高度时内部出现滚动条。

不用 `<details>` 折叠 —— 用户需要看清所有文件名(弹窗本身就是请用户确认全部命中),折叠会丢信息。
不用「等 N 个文件」字符串 —— 既然 chip 不截断,scroll 比截断更直白。
与 `.loading-files` 的「超过 8 个折叠」不同:loading 遮罩是「过程性反馈」,文件名只是辅助信息,截断可接受;模态是「确认性反馈」,文件名是核心信息,保留完整。

### D4: 上传前前端预检 + 拦截;只有全新增才发请求

```js
async function uploadFiles(files) {
  const fileArr = Array.from(files);
  // 前端预检:任何已存在的文件都拦截,弹模态告知,不发起入库请求
  const r = await fetch("/upload/files");
  const data = await r.json();
  const existing = new Set(data.files.map(f => f.name));
  const dupNames = fileArr.map(f => f.name).filter(n => existing.has(n));
  if (dupNames.length > 0) {
    showDupModal(dupNames);
    return;  // 完全不发入库请求
  }
  // 全部新增 → 正常上传
  showLoading(fileArr);
  try {
    // ... fetch + toast
  } finally {
    hideLoading();
  }
}
```

**变更原因(从 v2 演进到 v3)**: v2 设计的"上传后判定全重复弹模态"基于"用户希望系统帮他过滤"的假设,但用户实测反馈"已上传过的文件为啥还要显示出来"——他希望前端**直接拦截**,而不是"传完再告诉他白传了"。这能避免:
1. 无意义的入库请求(后端跑十几秒其实啥都没干)
2. Loading 遮罩的闪现(让用户以为系统在干活)
3. 用户等待十几秒的焦虑

**关于"部分重复场景"的取舍**: v3 设计选择了最严格的"任何重复都拦截"策略,即使用户拖了 3 个新文件 + 1 个已存在,也会弹模态让他重新选,不自动过滤。原因是用户原话"只要用户选择了已上传的文件 就直接拦截掉"语义最直接的解读。如果后续用户希望更友好(自动过滤 + 仅提示跳过的),可在此基础上放宽。

**踩坑要点(实现期由 curl 暴露)**:`app/api/upload.py:85` 把整个 `Config.UPLOAD_DIR` 传给 `pipeline.ingest()`,响应里 `data.skipped_files` 是"uploads/ 目录中已存在的全部文件",**不是"本次提交中重复的"**。如果退回到"后端判定"模式,必须用本次提交的文件名 ∩ `skipped_files` 求 `dupInBatch`,否则会误报。v3 用前端预检绕开了这个问题。

### D5: 失败 toast 文案直接透传后端 detail

`upload.py` 的 `HTTPException` 已经把可读错误信息塞进 `detail`(`不支持的文件格式: .exe(test.exe)` / `需要传 path` 等),前端直接 `data.detail || "上传失败"` 即可,不用前端再拼。

### D6: 样式改动集中在 `static/style.css`,HTML 几乎纯 JS 改动

- `static/style.css`:
  - `.toast` 增加 `max-width: 380px`、`word-break: break-word`、`line-height: 1.5`、`white-space: pre-line`
  - 新增 `.toast.warn`(暖橙底 + 深棕字,备用,本变更未触发)
  - 新增 `--warn-bg` / `--warn-text` 设计令牌
  - 新增 `.loading-mask` / `.loading-spinner` 全屏遮罩 + 旋转动画
  - 新增 `.dup-overlay` / `.dup-box` / `.dup-icon-circle` / `.dup-title` / `.dup-subtitle` / `.dup-close` / `.dup-files`(chip 风格)重复上传提示模态(沿用 `.md-overlay` 视觉约定,z-index 110 高于 loading-mask 100)
- `static/manage.html`:
  - `uploadFiles()` 重写为预检拦截分支:先 `precheckAndFilter()`,命中即 `showDupModal` + return;全新增走正常 `showLoading` → fetch → toast
  - 新增 `precheckAndFilter(fileArr)`:拉已入库列表,返回命中文件名
  - 新增 `showLoading(items)` / `hideLoading()`:复用 `.loading-mask` DOM,显示文件名列表
  - 新增 `showDupModal(names)` / `hideDupModal()`:渲染 `#dupOverlay`,按钮 / X / 遮罩空白 / ESC 均可关闭
  - 新增 `#dupOverlay` DOM 节点(暖色圆形图标 + 标题 + 副标题 + 文件名 chip 列表 + 「我知道了」按钮)
  - `$("btnDir").onclick` 接入 loading 遮罩(目录入库也是十几秒,同样静默问题)
- `static/app.js`:
  - `showToast(msg, type?, durationMs?)` 签名扩展(type 默认 "",durationMs 默认 2200 / "err" 6000 / "warn" 5000),向后兼容旧 `showToast(msg, true)` 调用

## Risks / Trade-offs

- **R1**: 全屏遮罩 + `pointer-events` 阻断下层交互,若后端响应意外挂死(没有 reject 也没有 resolve),用户卡死看不到响应 → 已通过 fetch 超时(fastapi 默认 keep-alive + 浏览器默认 fetch 无超时,但本项目后端无超时配置)规避:接受这个风险,实际生产中可后续再加 `AbortController` 超时(暂不在本变更范围)
- **R2**: 模态文件名列表过长时会撑高遮罩 → 已通过 `.dup-body` 设 `max-height: 50vh` + `overflow: auto` 让超长文件名内部滚动,不撑高遮罩
- **R3**: 前端预检依赖 `GET /upload/files` 的响应,如果该接口失败,`precheckAndFilter` 抛错 → `uploadFiles` 外层 catch 会触发失败 toast,提示用户刷新页面重试(文案「无法获取已入库文件列表,请刷新页面重试」)
- **R4**: Loading 遮罩只展示"入库中"一态(后端无 SSE/yield 进度事件,落盘 + 切分 + embedding + 写库同步执行,十几秒后才返回响应),无真正进度 → 已在 Goals/Non-Goals 明确接受,后续要做精细进度需改造后端

## Migration Plan

- 部署:静态文件改动,跟随下一次前端构建/部署即可,无后端发布依赖
- 回滚:`git revert` 本次提交即可,无数据库 / 集合状态变更
- 不需要重启服务(`uvicorn --reload` 会自动加载静态文件改动)

## Open Questions

无(已与用户对齐全部决策点:进度方案 = Loading 遮罩(单文案"正在入库,请稍候…");重复文件处理 = 前端预检 + 任何命中都拦截 + 弹模态;失败 toast = 6s + 透传后端 detail;成功 toast = 2.2s + 简短摘要;模态 chip 不折叠走内部滚动;`.toast.warn` 仅作 CSS 备用)。`specs/manage-page/spec.md` 共 6 个 scenario(Loading 遮罩 / 预检拦截 / 全新上传 / 失败 / chip 滚动 / 遮罩生命周期)。