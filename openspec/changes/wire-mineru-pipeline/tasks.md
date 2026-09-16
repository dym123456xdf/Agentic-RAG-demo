# Tasks: Wire MinerU into the Loader Pipeline

## 1. Extend `app/rag/loader.py`

- [ ] 1.1 新增私有函数 `_load_via_mineru(path: Path) -> List[Document]`:
  - 校验 `MINERU_BIN` 文件存在,否则抛 `FileNotFoundError`
  - 校验 `MINERU_ENABLED` 为 True(否则调用方不该走到这里)
  - 计算缓存路径:`MINERU_OUTDIR / f"{path.stem}.md"`
  - **缓存命中** → `read_text(缓存路径)` 直接返回
  - **缓存未命中** → `subprocess.run([MINERU_BIN, "-i", str(path), "-o", str(MINERU_OUTDIR)], timeout=MINERU_TIMEOUT_S, capture_output=True)`,非零退出码抛 `RuntimeError(f"mineru failed: {stderr[-500:]}")`,超时抛 `subprocess.TimeoutExpired`
  - 解析成功后 `read_text(缓存路径)` 返回,`metadata={"source": path.name, "mineru_cache": str(缓存路径相对项目根)}`
- [ ] 1.2 在 `_load_one` 的 switch 里加分支:`if Config.MINERU_ENABLED and suffix in {".pdf", ".docx", ".pptx"}: return _load_via_mineru(path)`
- [ ] 1.3 把 `_load_via_mineru` 的 stdout 摘要用 `print` 打一行(`[loader] mineru parsed {path.name} → {len(text)} chars`),便于调试

## 2. Update `app/api/upload.py` comments

- [ ] 2.1 在 `upload_files` 端点的 docstring 末尾加一行:"当 MinerU 启用时,`{UPLOAD_DIR}/<name>` 与 `MINERU_OUTDIR/<stem>.md` 共同构成入库源,清空任一目录都会触发重新解析"
- [ ] 2.2 `list_files` 端点的 docstring 加一行:"返回的 chunk 数包含 MinerU 缓存命中与新解析的混合"

## 3. Tests(本仓库无测试套件,此段为手动验证清单)

- [ ] 3.1 **基本路径**:`MINERU_ENABLED=false`,上传 `data/sample_kb.md` → 行为与本次 change 之前完全一致(`GET /upload/files` 返回 chunks > 0)
- [ ] 3.2 **MinerU 启用**:`MINERU_ENABLED=true` + 配 `MINERU_BIN` → 上传一个测试 PDF → 检查 `MINERU_OUTDIR/<stem>.md` 存在 + Milvus 里有 chunks
- [ ] 3.3 **缓存命中**:再次上传同名 PDF → 检查没有新的 minerU 子进程产生(macOS: `pgrep -lf mineru` 在上传前后不变)
- [ ] 3.4 **二进制缺失**:`MINERU_ENABLED=true` + `MINERU_BIN` 指向不存在路径 → 上传 PDF 应返回 500 + 明确 `FileNotFoundError`
- [ ] 3.5 **解析超时**:`MINERU_TIMEOUT_S=1` 上传大 PDF → 应抛 `subprocess.TimeoutExpired` 包成 HTTP 500

## 4. Spec update(本 change archive 时合入 `specs/document-indexing/spec.md`)

- [ ] 4.1 在 `openspec/changes/wire-mineru-pipeline/specs/document-indexing/spec.md` 写 `## ADDED Requirements`,新增 4 条 Requirement:
  - `Requirement: Optional MinerU-backed parsing`
  - `Requirement: MinerU output caching`
  - `Requirement: MinerU failure surfaces as error`
  - `Requirement: MinerU images preserved but not indexed`
- [ ] 4.2 archive 时(后续步骤):把上述 ADDED Requirements 合并进 `openspec/specs/document-indexing/spec.md`,并在 `tasks.md` 末尾打 `[x]`

## Verification

实施完成后跑:
- `python -c "from app.rag.loader import _load_via_mineru; print(_load_via_mineru.__doc__)"` 验证导入
- 手测 1.1 / 3.1 / 3.2 / 3.3 / 3.4 / 3.5
- `git diff app/rag/loader.py` 确认改动只在 `_load_via_mineru` + `_load_one` 的新分支,不动 `_read_text` / `load` 等已有路径