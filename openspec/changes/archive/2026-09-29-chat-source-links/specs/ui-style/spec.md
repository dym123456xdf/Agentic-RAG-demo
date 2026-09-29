# Spec Delta

## ADDED Requirements

### Requirement: 来源行跳转链接视觉

首页与管理页参考来源行的跳转链接 SHALL 由共享样式表的设计令牌驱动:链接文字色 = 暖棕主色令牌(`--accent`),hover 变深为 `--accent-hover` 令牌;外链图标 stroke 跟随 `currentColor`(与来源回形针图标同一风格)。HTML 与共享脚本中不得为该链接写硬编码颜色的内联样式(功能性属性除外,如 `target` / `rel`);两页渲染同一来源行时视觉必须一致。

#### Scenario: 链接颜色随令牌
- **WHEN** 在任一页面查看带跳转链接的来源行
- **THEN** 链接文字为主色令牌 `--accent`,鼠标悬停变为 `--accent-hover`,不出现硬编码色值

#### Scenario: 两页视觉一致
- **WHEN** 首页流式来源块与管理页历史展开的来源块渲染同一来源
- **THEN** 链接与图标的外观(颜色、字号、图标风格)一致,无风格割裂
