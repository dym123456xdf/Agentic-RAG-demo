# Proposal

## Why

前端两页(聊天首页 / 管理页)视觉停留在 2015 年代饱和平铺色风格,且存在实际可用性缺陷:管理页文件列表深底(`#34495e`)配深色文字几乎不可读、输入框样式按深色侧边栏书写却被浅色区域误用(只能靠内联 `color:#fff` 打补丁)、按钮/圆角/间距没有统一体系。用户明确要求整体重做为 Claude 风暖色极简设计。

## What Changes

- `static/style.css` 整体重写:引入设计令牌(CSS 自定义属性:配色 / 圆角 / 阴影 / 间距 / 字体),米白底 `#FAF9F5`、暖棕主色 `#B45309`、浅暖灰侧边栏、白底圆角卡片、衬线标题
- 聊天页(index.html):对话流限宽居中(约 760px),AI 回答改为卡片式排版,用户消息为暖色气泡;底部改为大圆角输入框;无消息时展示居中问候空状态
- 管理页(manage.html):文件列表改为白底卡片行(修复深底深字对比度 bug),tab 改为胶囊分段式,上传区/统计/历史面板按同一令牌重做
- 清理 HTML/JS 中的内联样式补丁:index.html、manage.html 的 `style="color:#fff"` 等,以及 `app.js` 里 `messageHtml()` 硬编码的 `color:#888`/`#555` 内联颜色改为 class
- 关键 emoji 图标(📚 ⚙️ 📂 🕘 等)替换为内联 SVG,保持极简气质

## Capabilities

### New Capabilities

- `ui-style`:前端统一视觉体系 —— 设计令牌与暖色极简风格规范,覆盖聊天页与管理页全部可见组件(布局、消息、输入框、列表、按钮、弹层、toast),含文本对比度可读性要求

### Modified Capabilities

(无 —— `chat-sessions`、`manage-page`、`chat-image-rendering`、`document-loading` 均为功能层需求,本次不改变任何功能契约,仅改视觉呈现)

## Impact

- **前端**:`static/style.css`(重写)、`static/index.html`(结构调整 + 去内联样式)、`static/manage.html`(同左)、`static/app.js`(仅 `messageHtml()`/`metaHtml()` 输出的标记与 class 调整,API 调用逻辑不动)
- **后端**:零改动 —— 不涉及任何路由、接口、数据
- **兼容**:两页 HTML 结构中 JS 依赖的 id 与 class 钩子(`#chat`、`#q`、`.session-list` 等)保持不变,交互逻辑不受影响;`chat-image-rendering` 的 `renderChatImages` 行为不变
- **非目标**:不做暗色模式切换、不做移动端响应式适配、不引入构建工具与外部字体/图标依赖
