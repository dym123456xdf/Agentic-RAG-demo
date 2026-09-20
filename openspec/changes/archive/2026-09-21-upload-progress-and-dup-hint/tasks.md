# Tasks

## 1. CSS 样式扩展

- [x] 1.1 在 `static/style.css` 给 `.toast` 增加 `max-width: 380px`、`white-space: pre-line`、`word-break: break-word`、`line-height: 1.5`
- [x] 1.2 在 `static/style.css` 新增 `.toast.warn`(暖橙底 + 深棕字,使用设计令牌)+ `--warn-bg` / `--warn-text` 设计令牌;`.toast.warn` 本变更不触发,仅作 CSS 备用
- [x] 1.3 在 `static/style.css` 新增 `.loading-mask`(全屏 fixed 半透明暖灰 + z-index 100 高于 .toast + `pointer-events: auto`)与 `.loading-spinner`(CSS 旋转动画)

## 2. JS 工具函数

- [x] 2.1 在 `static/manage.html` 新增 `showLoading(items)` 与 `hideLoading()`:构造/复用 `.loading-mask` DOM,把文件名列表渲染到遮罩中央
- [x] 2.2 扩展现有 `showToast(msg, type?, durationMs?)`:按 type 加 `.err` / `.warn` class 并按 durationMs 设置 setTimeout,默认 2.2s、`"err"` 6s、`"warn"` 5s;向后兼容旧 `showToast(msg, true)` 调用

## 3. 前端预检 + 拦截(主分支改造)

- [x] 3.1 在 `static/manage.html` 新增 `precheckAndFilter(fileArr)`:拉取 `GET /upload/files` 拿已入库列表,返回命中已存在的文件名数组(命中即抛错交给外层 catch)
- [x] 3.2 重写 `uploadFiles()`:入口先 `precheckAndFilter(fileArr)`,命中(任意数量)直接 `showDupModal(dupNames)` 并 `return`(不发入库请求,不显示 Loading 遮罩);只有全部新增才走 `showLoading` → fetch → 成功 toast 流程;`fetch` 抛错或 `r.ok === false` 走外层 err toast

## 4. 目录入库接入遮罩

- [x] 4.1 在 `static/manage.html` 给 `$("btnDir").onclick` 加 `showLoading([path])` / `finally` 块 `hideLoading()`;目录入库不做前端预检(用户输入的是路径,无法预选过滤),后端跳过已存在文件后用 toast 告知跳过了 N 个

## 5. 端到端验证

- [x] 5.1 启动 `conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8011 --reload`,打开管理页手动跑三类场景:① 拖已入库文件 → 模态弹出 + 无网络请求(浏览器 DevTools Network 验证);② 拖全新文件 → Loading 遮罩显示 + 成功 toast;③ 触发后端 `detail` 错误的请求 → err toast 6s;逐条核对模态/遮罩/toast 文案、持续时间、显隐时机是否符合 `specs/manage-page/spec.md` 的 6 个 scenario(Loading 遮罩 / 预检拦截 / 全新上传 / 失败 / chip 内部滚动 / 遮罩生命周期),确认所有失败路径 Loading 遮罩不会卡住不消失

## 6. 重复上传模态弹窗(独立于 toast)

- [x] 6.1 在 `static/style.css` 新增 `.dup-overlay`(全屏 fixed 半透明 + z-index 110 高于 loading-mask 100 + `pointer-events: auto`)与 `.dup-box`(居中白底卡片,`width: min(440px, 92vw)` 最大 440px / 响应式 92vw + 标题区 + body 区 + footer 区),沿用 `.md-overlay` 视觉约定;新增 `.dup-icon-circle` / `.dup-title` / `.dup-subtitle` / `.dup-close` / `.dup-files`(chip 风格 flex-wrap)
- [x] 6.2 在 `static/manage.html` 末尾新增 `#dupOverlay` DOM 节点(暖色圆形图标 + 标题 + 副标题 + 文件名 chip 列表 + 「我知道了」按钮 + 右上角关闭 X);实现 `showDupModal(names)`(填充列表 + 加 `.show`)与 `hideDupModal()`(移除 `.show`),按钮 / X / 遮罩空白 / ESC 均可关闭
- [x] 6.3 模态 chip 列表**不折叠**:`showDupModal` 直接 `names.map` 渲染全部 chip(用户需要看清所有命中文件名);超出可视区域由 `.dup-body` 的 `max-height: 50vh` + `overflow: auto` 处理内部滚动(在 CSS 实现,JS 不参与)

## 7. 清理与一致性

- [x] 7.1 移除 v2 残留代码:`formatNames` 折叠函数(toast 不再需要)、`uploadFiles` 中的"全重复"warn toast 分支、`uploadFiles` 中的"部分跳过"分支(被前端预检拦掉,后端响应 `skipped_files` 永远为空)
- [x] 7.2 grep 验证:全仓库不再有 `data.skipped_files` 在前端被读取 / 不再有 `.toast.warn` 在 JS 中被触发 / 不再有 `formatNames` 残留引用