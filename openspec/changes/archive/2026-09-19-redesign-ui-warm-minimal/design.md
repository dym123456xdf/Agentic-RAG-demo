# Design

## Context

现状:`static/style.css` 约 125 行,侧边栏为深藏青 `#2c3e50`,部分组件样式(`input[type=text]` 深底、`.file-list li` 深底)是按"深色侧边栏"上下文书写的,却被管理页浅色内容区复用,产生深底深字不可读缺陷与 `style="color:#fff"` 内联补丁(manage.html:40)。两页 DOM 骨架(`#sidebar` / `#main` / `#chat` / `#input-bar` / 管理页 tabs)已被 inline script 与 `app.js` 以 id/class 钩子引用,不能随意改名。用户已选定方向:Claude 风暖色极简(米白底 `#FAF9F5`、暖棕主色 `#B45309`)。

## Goals / Non-Goals

**Goals:**

- 一份令牌驱动的 `style.css`,两页组件视觉统一,修复对比度缺陷
- 保持全部 JS 钩子(id 与被 JS 选中的 class)不变,交互逻辑零回归
- 零外部依赖:不引字体/图标库/构建工具,系统字体 + 内联 SVG

**Non-Goals:**

- 暗色模式、移动端响应式、动画体系(proposal 已声明)
- 后端任何改动;`renderChatImages` 的放行规则不动(chat-image-rendering 契约)

## Decisions

### D1:令牌先行,CSS 自定义属性集中在 `:root`

```
--bg:#FAF9F5; --bg-sidebar:#F0EEE6; --surface:#FFF; --surface-hover:#F5F3EE;
--text:#29261C; --text-secondary:#6B675C;
--accent:#B45309; --accent-hover:#92400E; --accent-soft:#F6E8D8;
--border:#E7E3D9; --danger:#B3261E;
--radius-sm:8px; --radius-md:12px; --radius-lg:16px; --radius-full:999px;
--shadow-sm/md; --font-serif/--font-sans
```

- 备选:Tailwind CDN / 引入组件库 —— 否决:违背零依赖与项目极简脚手架定位
- `--text-secondary:#6B675C` 在 `--surface` 与 `--bg` 上对比度 ≈5:1,满足 spec 的 AA 底线;原 `#888`/`#555` 内联色全部废弃
- 用户气泡 `#B45309` 实底白字(≈4.6:1)达标

### D2:DOM 骨架不动,样式按"上下文"拆分作用域

根因修复:样式不再"按侧边栏上下文书写、全页复用",而是 (a) 令牌区、(b) 两页共享组件区、(c) 聊天页区、(d) 管理页区 分段组织。管理页的输入框/文件行直接用浅色令牌,删除 manage.html:40 的 `color:#fff` 补丁。侧边栏由深藏青改为 `--bg-sidebar` 浅暖灰。

### D3:对话流限宽居中 + 空状态问候

`#chat` 内部包一层限宽容器(max-width 760px,margin auto)由 CSS 对 `#chat > *` 或新增 wrapper 实现;采用给 `#chat` 设 `display:flex; flex-direction:column; align-items:center` + 消息行 `width:100%; max-width:760px` 的方案,不改 HTML 结构。空状态问候(#empty-hero)作为 `#main` 下 `#chat` 的兄弟节点,由首页脚本在会话无消息时显示 —— 不能放进 `#chat` 内部,因为 `switchSession()` 会 `chatEl.innerHTML = ""` 清空它。

### D4:字体策略

标题(品牌名、问候语、区块标题)用 `--font-serif: Georgia, "Songti SC", "Noto Serif SC", serif`,正文维持系统无衬线栈。不加载 web font(macOS/Linux/Windows 均有衬线回退,离线可用)。

### D5:emoji 图标换内联 SVG

仅替换结构性图标(品牌 📚、管理 ⚙️、tab 📂/🕘、发送按钮),`msg` 内的 ⚠️/❓/📎 等运行时拼接标记一并清理为文字或 SVG。SVG 用 `stroke="currentColor"` 跟随文字色。备选:保留 emoji —— 否决:渲染不一致且与新风格气质冲突。

### D6:app.js 仅动标记,不动逻辑

`messageHtml()` 中 `style="float:right;color:#888"`、`style="color:#555"` 改为 `.src-score` / `.src-snippet` class;manage.html 历史回溯处的同款内联样式同步替换。API 封装、`renderChatImages`、`escapeHtml` 逻辑不动。

### D7:tab 改胶囊分段控件

`.tabs` 容器变浅底圆角容器(`--bg-sidebar`),`.tab.active` 为白色浮起胶囊 + `--shadow-sm`,替换现在的"圆角顶部 + 下边框拼接"老式 tab。

## Risks / Trade-offs

- [JS 动态生成的标记遗漏新样式] → tasks 中列出全部动态 class 清单(`msg/user/bot/sources/src/meta/chat-img/toast/hist-item/q/a/session-list*`)逐一核对
- [限宽方案与绝对定位元素冲突] → 空状态用兄弟节点而非 `#chat` 内定位(见 D3)
- [衬线字体在 Windows 回退到 SimSun 观感一般] → 可接受的系统字体权衡,不引 web font
- [两页共用一份 css,改 A 页波及 B 页] → 按 D2 分段注释组织,验证步骤两页各过一遍

## Migration Plan

纯静态文件替换(style.css 重写 + 两个 HTML 结构微调 + app.js 标记调整),刷新浏览器即生效;回滚 = `git checkout` 这 4 个文件。无数据、接口、依赖迁移。
