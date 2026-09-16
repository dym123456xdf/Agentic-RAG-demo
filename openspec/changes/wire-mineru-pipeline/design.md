# Design: Wire MinerU into the Loader Pipeline

## Context

MinerU 是 MinerU 团队的开源 PDF / DOCX / PPTX 解析工具,内部用 ONNX/Paddle 跑版面分析 + OCR + 表格还原,中文/扫描件/复杂排版的召回质量明显优于通用 unstructured 库。M 系列 16 GB 内存可以本地跑(任务里已确认)。

当前 `app/rag/loader.py:_load_one` 对所有非 md 后缀统一走 `UnstructuredReader.load_data(file=str(path), split_documents=False)`。这条路径对中文 PDF 召回质量差,且无法保留 MinerU 那套版面分析得到的标题层级 — 也就是 `MarkdownNodeParser` 切不出有意义的 chunks。

接入点很自然:**在走 UnstructuredReader 之前先尝试 MinerU,产出 markdown 后复用现有 markdown 直读路径**。这样 splitter/indexer 完全不需要改动。

## Decisions

### 触发条件:`MINERU_ENABLED AND suffix ∈ {.pdf, .docx, .pptx}`

- `.md/.markdown/.txt` 直读路径已经够好,不引入 MinerU(它对纯文本无价值)
- `.docx/.pptx` 也走 MinerU 是因为 MinerU 对办公文档的章节识别比 UnstructuredReader 强

### 缓存策略:文件名即缓存键

- 缓存路径:`MINERU_OUTDIR / f"{path.stem}.md"`
- 命中条件:文件存在(不校验 mtime — 解析结果稳定,且原 PDF 改了的场景罕见;如果以后需要校验,加 `os.path.getmtime` 比较即可)
- 不缓存失败:解析失败抛错,但缓存目录里**不留下半成品 .md**,靠 minerU 自身的原子写保证

### 错误处理:不静默 fallback

设计上**故意**不做"minerU 失败 → fallback 到 UnstructuredReader":

- 静默 fallback 会让用户开了 `MINERU_ENABLED=true` 但召回质量差却不知道为什么
- 显式抛错让用户在第一次上传就能发现"MinerU 没装好"或"PDF 损坏"
- 真要降级,以后改成 `MINERU_ENABLED=warn` 这样的第三档,而不是默认行为

### 执行方式:同步 subprocess

- `subprocess.run([Config.MINERU_BIN, "-i", str(path), "-o", str(Config.MINERU_OUTDIR)], timeout=Config.MINERU_TIMEOUT_S, capture_output=True, text=True)`
- `timeout` 防单 PDF 卡死(MinerU 自带超时配置,但双层保险)
- `capture_output=True` 让 stderr 在异常时可用

### 图片处理:留盘不入库

- MinerU 会把图片抽到 `MINERU_OUTDIR/<stem>/images/`
- 不把这些图片作为 metadata 字段塞进 Document(否则 Milvus 又要报未注册字段)
- 也不读图片本身进文本(MinerU 已经在 markdown 里嵌入图片相对路径 `![](images/xxx.png)`,MarkdownNodeParser 会原样保留)
- 后续如果要做多模态,这是单独的 change

### 与现有 markdown 路径的一致性

`_load_via_mineru` 走完后,产出的 `Document` 和现有 `.md` 直读路径**形态一致**:同样是 `Document(text=..., metadata={"source": path.name, ...})`,下游 `splitter.split` → `indexer` 完全无感。

## Explicit Non-Designs

- **不引入 MinerU 进度回调**:本仓库无 SSE,前端看不到进度;真要做走单独的 streaming change
- **不解析 PDF 之外的电子书格式(.epub/.mobi)**:用户用不到
- **不解析加密 PDF**:`subprocess.run` 在密码错时会非零退出,自然报错,不专门处理

## Verification Hook

本 change archive 前必须验证(对应 `tasks.md` §3):

1. `MINERU_ENABLED=false` 路径回归 — 已上传的 `data/sample_kb.md` 仍能正常检索(这是**不破坏**已有功能的硬性条件)
2. `MINERU_ENABLED=true` 路径新增 — PDF 解析成功 + chunks 落库
3. 缓存命中 — 二次上传无新 minerU 子进程
4. 失败路径 — 缺失二进制 / 超时都抛明确错误