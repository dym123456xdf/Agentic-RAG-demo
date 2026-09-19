# Design

## Context

现状:

- 入库幂等:`indexer.build_from_path()` 入库前用 `MilvusStore.list_sources()` 拿 `{source: chunk_count}`,同名文件整体跳过(`indexer.py:46-55`)——删除后重传能绕过跳过的前提是 Milvus 里该 source 的 chunk 被删干净。
- 磁盘侧:`uploads/<name>` 是入库源文件;`converted/<stem>/` 是 MinerU 产物(md + images/),本次 md 图片规范化后多了 `assets/` 子目录。三者当前无删除入口。
- `MilvusStore` 只封装了 query/list_sources,无删除能力;`MilvusClient.delete(collection_name, filter=...)` 可用(pymilvus 2.6.17,`filter` 为表达式字符串)。
- 管理页 `refreshFiles()` 已有行级事件委托(`fileList.onclick` 里的 `.view-md` 先例),删除按钮可复用同一模式;原生 `confirm()` 与会话删除的交互先例一致(index.html:94)。
- 已知脏数据:01-LangChain概述.pdf 磁盘文件已删、Milvus 残留 87 chunk——新删除接口可直接清掉(Milvus 侧 delete 对"磁盘无文件"不敏感,磁盘侧删不存在的文件需容忍)。

## Goals / Non-Goals

**Goals:**

- 一次 API 调用完成 Milvus + uploads + converted 三处联动删除,原子序:先 Milvus 后磁盘(向量库是真相源,删了向量却留着文件,用户还能重传恢复;反过来留脏 chunk 最坏)
- 管理页一行一个删除按钮,交互与会话删除同构(confirm → toast → 刷新)
- 删除后重传同名文件内容更新生效(幂等约束自然缓解)

**Non-Goals:**

- 批量删除、回收站/软删
- 删除历史问答里引用该文件的来源标注(历史消息里的 source 文件名只是文本,不联动)
- 权限控制(单用户 demo 定位)

## Decisions

### D1. 删除粒度:按 source(文件名)整文件删

`MilvusClient.delete(filter=f'source == "{name}"')` 一次清光该文件全部 chunk,与 `list_sources()` 的幂等键对齐。备选:按 doc_id 逐个删(需要两次往返且 doc_id 是 md5 截断,不可靠,弃)。name 中的 `"` 转义为 `\"` 防表达式注入。

### D2. 联动顺序与失败语义:Milvus 先行,磁盘容错

1. 校验 name(`Path(name).name == name`、无 `/`、后缀在 `ALLOWED_EXTS`,与转换产物接口的白名单惯例一致)→ 否则 404
2. `store.delete_source(name)` 删 Milvus chunk;返回 0 且 `list_sources()` 无该 source 且磁盘也无该文件 → 404 "不在库中"
3. 磁盘删除容错:`uploads/<name>` 不存在则跳过(01 脏数据场景:Milvus 有、磁盘无);`converted/<stem>/` 整目录 `shutil.rmtree` 不存在则跳过
4. 返回 `{"deleted": name, "chunks_removed": N}`(N = Milvus 删除数;磁盘删除情况不细分,接口保持简单)

风险:Milvus 删除成功后磁盘删除抛异常(权限)——响应 500,但 chunk 已删。可接受:同名重传即可重建全部(产物会重新转换),且 demo 单机场景磁盘权限异常概率极低。

### D3. 后端落点:`MilvusStore.delete_source` + `upload.py` 路由

- `milvus_client.py` 加 `delete_source(name) -> int`:内部 `self._client.delete(collection_name, filter=f'source == "{escaped}"')`,结果取 `result["delete_count"]`;collection 不存在时返回 0
- `upload.py` 加 `@router.delete("/files/{name}")`:校验 → `get_store().delete_source(name)` → 磁盘 `uploads/name.unlink(missing_ok=True)` + `shutil.rmtree(MINERU_OUTDIR/stem, ignore_errors=True)`(stem = `Path(name).stem`,与 `converted_md_path()` 契约一致)
- 顺序与容错细节见 D2

### D4. 前端:行级 `.del-file` 按钮,复用 `fileList` 事件委托

- `refreshFiles()` 行内追加 `<span class="del-file" data-name="..." title="删除该文件">trash SVG</span>`,放 `.view-md` 之后(最右)
- `fileList.onclick` 里先判 `.del-file`(与 `.view-md` 同层级,互斥):原生 `confirm("删除「<name>」?将移除其全部向量与转换产物,不可恢复")` → `DELETE /upload/files/<encodeURIComponent(name)>` → 成功 `showToast("已删除 ...")` + `refreshFiles()`,失败 `showToast(err, true)`
- SVG 用 trash 图标(`stroke="currentColor"`),与 UI 体系统一

### D5. 样式:`.file-list .del-file` 对齐 `.session-list .del` 先例

默认 `--text-secondary`,`hover` 变 `--danger`,纯 CSS 不引新令牌。

## Risks / Trade-offs

- [Milvus delete 表达式注入] → name 先过 basename 白名单 + 双引号转义(D2/D1)
- [半程失败:Milvus 删了、磁盘没删] → 磁盘删除是尽力而为(D2 第 4 点),重传可自愈;日志打印磁盘删除结果
- [01 脏数据(Milvus 有磁盘无)] → 删除接口天然支持(D2 第 3 点容错)
- [删除不可逆] → confirm 文案明确"不可恢复",无回收站(Non-Goals)

## Migration Plan

无数据迁移:纯新增 API + UI。旧会话历史里对该文件的来源引用不受影响(文本保留)。
