# Proposal

## Why

管理页的上传流程目前有两个问题:① 入库过程静默(用户拖完文件 UI 立刻回到 idle,但后端入库要十几秒 —— 切分 + embedding + Milvus flush,期间无任何提示,用户不知道是上传卡住还是服务挂了);② 重复上传体验差(响应后 toast 只说"跳过 N 个重复",不告诉用户是哪几个;用户等十几秒才发现白传了)。

本次变更同时解决两个问题:**让入库过程可见**(Loading 遮罩),**在前端拦截重复文件**(用户选了已上传的文件直接弹模态,不发入库请求)。

## What Changes

- 管理页上传前先做**前端预检**:拉 `GET /upload/files` 拿已入库列表,任一文件名命中即弹模态告知,**不发任何入库请求**;只有全部新增才走正常上传流程
- 正常上传期间显示 Loading 遮罩(半透明 + 旋转 + 文件名列表),fetch 返回后立即关闭
- 结果反馈只剩两种 toast:
  - 成功:`✓ 入库 N 个片段,共 M 条` 2.2s 深底(`var(--text)` 背景 + 米白字)
  - 失败:`✗ 上传失败: <后端 detail>` 6s 红色
- 重复上传走模态弹窗(独立于 toast,语义更正式):标题「以下文件已上传,请勿重复上传」+ 副标题「请从选择中移除这些文件后重新上传。」+ 文件名 chip 列表(全部列出,不做折叠;`.dup-body` 设 `max-height: 50vh` + `overflow: auto`,过长时内部滚动而非截断)+ 「我知道了」按钮(右上角关闭 X / 点遮罩空白 / ESC 均可关闭)
- 目录入库(`btnDir`)不做前端预检(用户输入的是路径,无法预选过滤),后端跳过已存在文件后用 toast 告知跳过了 N 个
- 新增 CSS:`.toast` 多行排版 + 备用 `.toast.warn`(本变更未触发)+ `.loading-mask` / `.loading-spinner` 全屏遮罩 + `.dup-overlay` / `.dup-box` 重复上传模态

## Capabilities

### New Capabilities

无(只在现有 capability 上扩展行为)。

### Modified Capabilities

- `manage-page`:在"管理页文件管理"场景下新增一条 requirement,描述"上传前端预检拦截 + Loading 遮罩 + 成功/失败 toast + 重复上传模态"的可见行为
- `ui-style`:新增一条 requirement,定义 toast 多行排版约定 + Loading 遮罩样式 + 重复上传模态视觉(`.toast.warn` 保留备用)

## Impact

- 改动文件:
  - `static/manage.html` —— `uploadFiles()` 重写为预检拦截分支;新增 `precheckAndFilter(fileArr)` / `showLoading(items)` / `hideLoading()` / `showDupModal(names)` / `hideDupModal()`;新增 `#dupOverlay` DOM 节点;`$("btnDir").onclick` 接入 loading 遮罩
  - `static/style.css` —— `.toast` 多行排版;备用 `.toast.warn`;`.loading-mask` / `.loading-spinner`;`.dup-overlay` / `.dup-box` / `.dup-icon-circle` / `.dup-title` / `.dup-subtitle` / `.dup-close` / `.dup-files`(chip 风格)
  - `static/app.js` —— `showToast(msg, type?, durationMs?)` 签名扩展(runtime 触发两态:成功 2.2s / 错误 6s;`warn` 在函数能力上保留 5000ms 但本变更不触发),向后兼容旧 `showToast(msg, true)` 调用
- 后端 0 改动:`app/api/upload.py`、`app/rag/pipeline.py`、`app/rag/indexer.py` 全部不动
- 入库接口契约不变(响应字段 `saved` / `skipped_files` / `chunks_ingested` / `total_entities` / `detail` 仍由后端返回,前端只读 `files` / `chunks_ingested` / `total_entities` / `detail`)
- 无新依赖,无 breaking change