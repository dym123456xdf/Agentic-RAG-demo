# Proposal

## Why

聊天页(含首页会话回溯、管理页历史回溯)对含图文档提问时,答案里的图片引用全部以 `![...](...)` 原文显示,用户看不到图。排查确认是三层断链叠加:前端消息渲染只做 `escapeHtml` 从不渲染图片;入库 chunk 里是 `images/xxx` 相对路径,脱离来源文件后前端无法拼出可访问 URL;generator prompt 未约束图片引用,LLM 会按 MinerU 风格编造出磁盘上不存在的路径(实测 Milvus 180 个 chunk 中 0 条与答案中的 `output/images/...` 引用匹配)。上一变更(管理页"查看转换MD"弹层渲染图片)只覆盖了弹层,聊天链路从未打通。

## What Changes

- **产物目录重构**:MinerU 产物改为每文档一个无后缀文件夹 `converted/<stem>/`,md(`<stem>.md`)与 `images/` 同级放置(现状:md 在 `converted/` 顶层、文件夹名带原后缀)。上传接口的产物定位(`has_converted` / 转换产物读取)与管理页弹层的图片 URL 前缀同步适配;存量产物一次性迁移到新结构。
- **入库文本规范化**:`loader.py` 的 MinerU 通道读入 converted md 后,在内存把 `![alt](images/x)` 改写为 `![alt](/converted/<stem>/images/x)` 绝对 URL 再切分入库;落盘 md 保持相对路径不变(人工核对与管理页弹层行为不受影响)。
- **生成约束**:`generator.py` 的 SYSTEM prompt 增加图片引用规则——参考资料中的图片引用必须原样保留进答案,不得改写、缩写或编造路径;资料无图时不得自行添加图片引用。
- **前端渲染**:`app.js` 提供共用的图片渲染函数,`messageHtml()`(首页实时回答 + 会话回溯)与管理页历史回溯接入:escape 后把 `![alt](/converted/...)` 替换为 `<img>`;仅放行 `/converted/` 前缀的 src(防注入),其余图片语法按原文显示。
- **一次性数据迁移(非代码)**:清空 Milvus `personal_kb` collection 并重新上传入库(转换产物已存在直接复用),否则同名文件幂等跳过导致旧 chunk 仍带相对路径。

## Capabilities

### New Capabilities
- `chat-image-rendering`:聊天首页实时回答、首页会话回溯、管理页历史回溯三处把答案中的图片引用渲染为真实图片(仅 `/converted/` 前缀),以及答案生成对图片引用的保真约束。
- `document-loading`:入库文本中图片引用规范化为 `/converted/<name>/images/x` 绝对 URL 的契约。(该 capability 已由在途变更 `upgrade-mineru-cli` / `enable-mineru-basic-tier` / `integrate-mineru-with-image-extraction` 先后叠加声明,尚无 main spec,本变更为追加 delta,归档时按序合并。)

### Modified Capabilities

(无 —— `chat-sessions` 与 `manage-page` 的既有 requirement 文本均不变;历史回溯展示图片属于新增渲染能力,不改变既有行为承诺。)

## Impact

- **代码**:`app/rag/loader.py`(`converted_md_path` / `convert_to_markdown` 落盘布局 + `_load_one` 内存改写)、`app/api/upload.py`(`has_converted` / 转换产物读取接口随 `converted_md_path` 适配)、`app/rag/generator.py`(SYSTEM prompt)、`static/app.js`(`messageHtml` + 新共用渲染函数)、`static/manage.html`(历史回溯接入共用函数 + 弹层图片 URL 前缀改 stem)。
- **数据**:Milvus `personal_kb` collection 需清空重建;`converted/` 存量产物一次性挪移到新目录结构(纯 mv,不重转);MySQL 历史不动(旧答案中的编造路径按原文显示,属预期)。
- **不受影响**:`main.py` 路由挂载、`converted/` 落盘格式、`/upload` API 契约、检索/重排链路、管理页弹层现有渲染。
