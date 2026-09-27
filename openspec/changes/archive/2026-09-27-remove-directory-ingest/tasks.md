# Tasks

## 1. 删除后端路由

- [x] 1.1 删除 `app/api/upload.py` 中 `@router.post("/dir")` 整段(原 97-116,含 docstring 与 `Path` 路径处理),并把文件头 docstring 里的 `- POST /upload/dir ...` 一行删掉(标题"四个端点"保持 —— 代码里原本就 4 个端点,删 `/dir` 后剩 4 行 + 标题才一致;tasks.md 原本写的"四个→三个"是字面误差)。验证:在 conda 环境 `rag` 中执行 `grep -c "@router\." app/api/upload.py` 结果为 4(其他四个端点保留);`python -c "from app.api.upload import router; paths=[r.path for r in router.routes]; assert '/upload/dir' not in paths, paths; print('ok')"` 输出 `ok`。

## 2. 删除前端 UI 区块

- [x] 2.1 删除 `static/manage.html` 中「索引服务器目录」HTML 区块:从 `<h3>索引服务器目录</h3>` 到包含输入框与「扫描并入库」按钮的 `</div>` 结束(原 36-40)。验证:`grep -n "索引服务器目录\|dir-row" static/manage.html` 无输出。
- [x] 2.2 删除 `static/manage.html` 中 `$("btnDir").onclick = async () => { ... };` 整段(原 214-235,约 22 行),含 `data.ingested_from` / `data.skipped_files` 的 toast 提示分支;`showLoading` / `hideLoading` / `refreshFiles` 等共享工具函数定义**保留**(「上传文件入库」还在用)。验证:`grep -n "btnDir\|/upload/dir\|ingested_from\|skipped_files" static/manage.html` 无输出;`grep -n "showLoading\|hideLoading\|refreshFiles" static/manage.html` 仍有定义引用。

## 3. 清理孤儿 CSS

- [x] 3.1 删除 `static/style.css` 中 `.dir-row` 与 `#dirpath` 两条 CSS 规则(design Decision 4:仅在「索引服务器目录」区块引用,删除后变孤儿)。验证:`grep -n "dir-row\|#dirpath" static/style.css` 无输出;`.drop` / `.btn` / `.file-list` 等其他类规则不动。注:实测 `style.css` 中并没有 `#dirpath` 专属规则,只有 `.dir-row input[type=text] { flex: 1; }` 通过属性选择器影响该 input —— 删 `.dir-row` 与 `.dir-row input[type=text]` 两条即可完全清理。

## 4. 集成验证

- [ ] 4.1 路由表确认。在 conda 环境 `rag` 中执行 `python -c "from app.api.upload import router; print(sorted(r.path for r in router.routes))"`,确认输出不含 `/upload/dir`、保留 `/upload/files` / `/upload/clear` / `/upload/files/{name}` / `/upload/converted/{name}`。
- [ ] 4.2 服务冒烟(可选,按需)。`conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8011`,浏览器访问 `http://127.0.0.1:8011/static/manage.html`,确认「索引服务器目录」区块消失、「上传文件入库」+「已入库文件」区块仍正常显示;手动拖一个 PDF 测试上传链路未受影响。
- [ ] 4.3 端点 404 确认(可选,按需)。`curl -i -X POST http://127.0.0.1:8011/upload/dir -H "Content-Type: application/json" -d '{"path":"data/"}'`,确认响应为 404 / 405(Method Not Allowed),不再是 200。
- [ ] 4.4 OpenSpec 校验。`openspec validate --change remove-directory-ingest --strict`(或项目对应命令),确认 proposal / specs delta / design / tasks 均通过校验。