# Tasks

## 1. 设计令牌与共享骨架(style.css)

- [x] 1.1 重写 `static/style.css`:建立 `:root` 令牌区(配色/圆角/阴影/字体,取值见 design.md D1)+ reset/body 基础层;浏览器打开两页确认米白底生效、正文无衬线/标题衬线
- [x] 1.2 重做侧边栏(浅暖灰 `--bg-sidebar`)与通用按钮体系(primary 暖棕实底 / ghost 细边 / danger),两页侧边栏与按钮观感一致
- [x] 1.3 重做 toast(深暖底白字圆角阴影)与滚动区基础样式,触发一次 toast 目测确认

## 2. 聊天页(index.html)

- [x] 2.1 对话流限宽居中(≤760px)+ 消息样式:用户消息右对齐暖色气泡白字、AI 回答白底卡片;带来源/meta/图片的回答完整渲染目测
- [x] 2.2 新增空状态问候节点(serif 大字 + 提示语,`#chat` 兄弟节点),首页脚本在会话无消息时显示、有消息时隐藏;新建/切换/清空/删除会话四种路径目测
- [x] 2.3 输入栏重做:通栏容器内限宽,大圆角输入框 + 圆形暖棕发送按钮(内联 SVG ↑);Enter 与点击发送均正常
- [x] 2.4 会话列表项新样式(白/透明底、active 暖色高亮、删除按钮 hover 变红),切换/删除交互不受影响

## 3. 管理页(manage.html)

- [x] 3.1 tab 改胶囊分段控件(浅底容器 + 白色浮起 active 胶囊),面板卡片化;两 tab 切换正常
- [x] 3.2 删除 `dirpath` 输入框的 `color:#fff` 内联补丁,目录入库输入行按浅色令牌重做,扫描入库流程可用
- [x] 3.3 文件列表改白底卡片行:文件名超长省略、chunk 数徽标、"查看转换MD"入口右对齐;统计行与 MinerU notice 暖色重做;上传区虚线圆角卡片带 hover/drag 高亮,拖拽与点击上传均可用
- [x] 3.4 问答历史面板(会话列表复用 2.4 样式、hist-item 问答卡片、来源 details 折叠)与转换产物弹层(md-overlay 遮罩 + md-box 白卡片)重做,展开来源/查看转换 MD 可用

## 4. 标记清理(app.js + 两页 HTML)

- [x] 4.1 `app.js` 的 `messageHtml()`/`metaHtml()`:内联 `color:#888`/`#555` 改为 `.src-score`/`.src-snippet` class 并在样式表定义;manage.html 历史回溯处同款内联样式同步清理;grep 确认无颜色类内联样式残留(功能性 display 类除外)
- [x] 4.2 结构性 emoji(📚 ⚙️ 📂 🕘 ⚙ 发送等)替换为内联 SVG(`stroke="currentColor"`),运行时拼接标记中的 ⚠️/❓/📎 一并清理;两页目测图标风格统一

## 5. 整体验证

- [x] 5.1 启动服务(`conda run -n rag uvicorn main:app --port 8011`),浏览器过全流程:两页视觉一致 → 上传入库 → 提问(来源/meta/图片渲染)→ 会话新建/切换/清空/删除 → 管理页历史回溯 → 转换 MD 弹层 → toast 正常
- [x] 5.2 对比度抽查:关键文字组合(正文/次要文字在白卡片与米白底、气泡白字、notice 文字)按 WCAG 公式计算 ≥4.5:1;JS 动态生成 class 清单(`msg/user/bot/sources/src/meta/chat-img/src-score/src-snippet/hist-item/q/a/session-list*`)逐一目测有新样式
