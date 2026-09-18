# Tasks

## 1. 产物目录重构(loader / upload / 管理页)

- [x] 1.1 `app/rag/loader.py::converted_md_path` 返回值改为 `converted/<stem>/<stem>.md`(`stem` = 原文件名去后缀),`convert_to_markdown` 的落盘与 `images_dir` 相应改为 `converted/<stem>/images/`;同步更新 loader.py 头部 docstring 的产物路径描述。验证:转换一份新 PDF,产物为 `converted/<stem>/<stem>.md` + `converted/<stem>/images/`,`converted/` 顶层无散落文件
- [x] 1.2 `app/api/upload.py` 产物定位适配:确认 `has_converted` 与 `GET /upload/converted/{name}` 经由新 `converted_md_path` 正常工作(接口入参仍为原文件名,防路径穿越校验不变)。验证:管理页"查看转换MD"能按新布局读到内容
- [x] 1.3 `static/manage.html::renderMdWithImages` 图片 URL 前缀改用 stem(`dataset.name` 去后缀,当前只去 `.md`)。验证:弹层内图片按 `/converted/<stem>/images/...` 加载成功
- [x] 1.4 存量产物一次性迁移脚本(纯 mv):旧 `converted/<原文件名>.md` + `converted/<原文件名>/` → `converted/<stem>/`。验证:两个尚硅谷 PDF 的产物在新位置、旧位置无残留,弹层与静态路由仍可访问

## 2. 入库文本规范化(loader)

- [x] 2.1 `app/rag/loader.py::_load_one` 的 MinerU 分支:读入 converted md 后,在内存把 `![alt](images/<file>)` 改写为 `![alt](/converted/<stem>/images/<file>)` 再构造 Document(落盘文件不动;`.md` 直传分支不改写)。验证:临时脚本调 `loader.load()` 打印 Document 文本,含 `/converted/<stem>/images/` 引用,落盘 md 内容未变
- [x] 2.2 验证产物复用路径同样生效:`converted/<stem>/` 下已有产物的文件再次 load,Document 文本仍为绝对 URL(改写在读盘后,与产物新旧无关)

## 3. 生成保真(generator)

- [x] 3.1 `app/rag/generator.py` SYSTEM prompt 增加图片规则:参考资料中的图片引用逐字保留,不得改写/缩写/编造;资料无图不得添加图片引用
- [x] 3.2 snippet 构建防截断:拼 context 前,把每条 node 全文中的图片引用整条抽出,200 字符截断后完整追加到该条 snippet 末尾。验证:构造一条图片引用横跨 200 字符边界的 node,确认进入 LLM 上下文的引用完整

## 4. 前端渲染(app.js / manage.html)

- [x] 4.1 `static/app.js` 新增共用渲染函数:输入已 escapeHtml 的文本,把 `![alt](/converted/...)` 替换为 `<img class="chat-img" ...>`;仅放行 `/converted/` 前缀,alt/src 中 `"` 先转 `&quot;`。验证:控制台单测函数 —— `/converted/` 引用成 `<img>`、`images/x` 与 `http://` 引用保持原文、含 `<script>` 与引号的输入全部按文本显示
- [x] 4.2 `messageHtml()` 接入该函数(首页实时回答 + 会话回溯同一渲染路径)。验证:首页提问含图文档,气泡内显示图片本体
- [x] 4.3 `static/manage.html` 历史回溯的答案渲染接入同一函数。验证:管理页历史里含 `/converted/` 引用的旧答案显示图片,来源/meta 折叠不受影响
- [x] 4.4 `static/style.css` 加 `.chat-img` 样式(max-width: 100%,圆角),验证图片不撑破气泡

## 5. 数据迁移 + 端到端验证

- [x] 5.1 重启服务;清空 Milvus `personal_kb` collection(drop 或全删 entities)
- [x] 5.2 构造一份专门的测试 PDF:内含数学公式、真实图片(≥2 张)、表格、多级标题,上传入库。验证:响应 chunks_ingested>0,产物落在新布局 `converted/<stem>/<stem>.md` 且 `images/` 下有图片文件
- [x] 5.3 端到端验证(用测试 PDF,不依赖尚硅谷样本):提问"这份文档里有哪些图?展示出来" → 答案渲染出图片;答案中的引用与库内 chunk 逐字一致(未被 LLM 改写);`/converted/<stem>/images/<hash>.<ext>` 直接 GET 返回 200
- [x] 5.4 回归验证:尚硅谷 PDF 重传入库(走迁移后的产物复用);管理页"查看转换MD"弹层图片仍正常;公式/表格内容在弹层与聊天答案中以文本呈现不乱码
- [x] 5.5 负路径验证:直传一份图片引用为 `./assets/a.png` 的 `.md` 入库,提问后答案中该引用按原文文本显示、浏览器 network 面板无对应图片请求
