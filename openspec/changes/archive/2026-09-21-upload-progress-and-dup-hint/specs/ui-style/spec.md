# Spec Delta

## ADDED Requirements

### Requirement: Toast 视觉与多行排版

共享样式表 SHALL 定义 toast 组件的语义状态 —— 成功(默认 `.toast`)与错误(`.toast.err`)—— 并支持多行文本(用于文件名列表等场景)。`.toast.warn`(暖橙底 + 深棕字)CSS 类 SHALL 保留备用但本变更不触发(预留后续"软警告"场景),对应的设计令牌 `--warn-bg` / `--warn-text` 也一并定义。toast 容器 SHALL 限制最大宽度并允许文本自然换行,保证长文件名列表不会溢出屏幕边缘。

#### Scenario: 两态样式区分明显

- **WHEN** 触发 toast 时分别传入成功、错误两种语义
- **THEN** 两种 toast SHALL 在背景色上明显区分(成功 = `var(--text)` 深色底 + `--bg` 米白字、错误 = `var(--danger)` 红底 + 白字),且与设计令牌系统的对比度要求(WCAG AA ≥ 4.5:1)保持一致

#### Scenario: Toast 文本自然换行

- **WHEN** toast 文本包含超过一行的内容(例如文件名列表)
- **THEN** 文本 SHALL 在 toast 容器内自然换行,不溢出屏幕右边缘

#### Scenario: Toast 最大宽度约束

- **WHEN** toast 文本非常长
- **THEN** toast 容器 SHALL 限制最大宽度(不超过桌面屏宽的 1/3,典型值约 380px),超过部分 SHALL 折行而非横向拉伸

### Requirement: Loading 遮罩样式

共享样式表 SHALL 定义 Loading 遮罩(`.loading-mask`)与旋转图标(`.loading-spinner`)的视觉外观,使管理页在执行耗时入库操作时给用户清晰的"正在处理"反馈;遮罩 SHALL 为全屏半透明遮罩,中心展示旋转图标与说明文字,且 SHALL 阻断用户对下层交互元素(尤其是上传区)的重复点击。

#### Scenario: 遮罩视觉一致

- **WHEN** Loading 遮罩显示
- **THEN** 遮罩背景为半透明暖灰(基于设计令牌系统),不与现有卡片/弹层风格冲突;旋转图标与文字位于视口中央,居中显示

#### Scenario: 遮罩阻断下层交互

- **WHEN** Loading 遮罩显示
- **THEN** 遮罩 SHALL 覆盖全屏并拦截下层元素的鼠标事件(`pointer-events: auto`),用户在遮罩消失前无法再次点击上传区触发重复入库