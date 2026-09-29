# Claude Code 插件打包与使用指南

> 以本项目为例:把 `.claude/` 里的 code-reviewer 子 agent、敏感文件保护钩子、OpenSpec 命令与技能,打包成插件 `my-review-kit`,发布到团队插件市场 `team-marketplace`。

## 概念速览

用 Java 生态类比,一句话就能理解三者关系:

| 概念 | 类比 | 说明 |
|---|---|---|
| **plugin** | 一个 jar 包 | 自包含的扩展:命令、子 agent、技能、钩子的目录 |
| **marketplace** | Maven 仓库 | 插件的目录清单,告诉 Claude Code 有哪些插件可装、去哪找 |
| `plugin install` | `mvn install` | 从某个 marketplace 安装一个 plugin |

`.claude/` 下的内容只能本项目用;打成 plugin 后,**任何项目、任何同事**装一次全都有。

## 打包产物结构

```
team-marketplace/                        # 市场根目录(可独立 git 仓库)
├── .claude-plugin/
│   └── marketplace.json                 # 市场清单(必须)
└── plugins/
    └── my-review-kit/                   # 插件根目录
        ├── .claude-plugin/
        │   └── plugin.json              # 插件清单(必须)
        ├── agents/
        │   └── code-reviewer.md         # 子 agent
        ├── commands/
        │   └── opsx/                    # 斜杠命令(6 个)
        ├── skills/
        │   └── openspec-*/              # 技能(6 个)
        └── hooks/
            ├── hooks.json               # 钩子注册
            └── protect.sh               # 钩子脚本(保留可执行位)
```

规则:市场清单固定放 `.claude-plugin/marketplace.json`;插件里的组件目录(`agents/`、`commands/`、`skills/`、`hooks/`)放插件根目录,不在 `.claude-plugin/` 里。

## 打包步骤

### 1. 拷贝组件

从项目 `.claude/` 原样拷贝 `agents/`、`commands/`、`skills/` 到插件根目录;钩子脚本拷到 `hooks/` 并保留可执行位:

```bash
SRC=~/PycharmProjects/Agentic-RAG-demo/.claude
PLUGIN=~/PycharmProjects/team-marketplace/plugins/my-review-kit
mkdir -p "$PLUGIN/.claude-plugin" "$PLUGIN/hooks"
cp -R "$SRC/agents" "$SRC/commands" "$SRC/skills" "$PLUGIN/"
cp "$SRC/hooks/protect.sh" "$PLUGIN/hooks/protect.sh"
chmod +x "$PLUGIN/hooks/protect.sh"
```

**不要打包** `settings.local.json` —— 它是个人权限白名单,含本机绝对路径,随插件分发会污染同事的配置。

### 2. 写插件清单 plugin.json

```json
{
  "name": "my-review-kit",
  "description": "团队代码审查工具包:code-reviewer 审查子 agent、敏感文件保护钩子、OpenSpec 工作流命令与技能",
  "version": "0.1.0",
  "author": { "name": "zhixi" },
  "keywords": ["code-review", "openspec", "hooks"]
}
```

只有 `name` 必填(kebab-case),但补全 `description`/`version`/`author` 能让 `/plugin` 列表里可读、可追溯版本。

### 3. 转换钩子配置(关键一步)

项目里钩子注册在 `.claude/settings.json`,插件里改用 `hooks/hooks.json`,**脚本路径必须换成 `${CLAUDE_PLUGIN_ROOT}`**:

```json
{
  "description": "敏感文件保护:拦截对 .env / secret 路径的 Edit/Write 修改",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/protect.sh\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

区别类比:项目里的 `$CLAUDE_PROJECT_DIR` 类似「相对当前项目找文件」,`${CLAUDE_PLUGIN_ROOT}` 是「相对插件安装目录找文件」—— 插件装到谁的机器上都能定位到自己带的脚本。注意占位符要放在双引号里(路径可能含空格),否则 `claude plugin validate` 会警告。

### 4. 写市场清单 marketplace.json

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "team-marketplace",
  "description": "团队内部 Claude Code 插件市场",
  "owner": { "name": "zhixi" },
  "plugins": [
    {
      "name": "my-review-kit",
      "description": "团队代码审查工具包:code-reviewer 审查子 agent、敏感文件保护钩子、OpenSpec 工作流命令与技能",
      "author": { "name": "zhixi" },
      "category": "workflow",
      "source": "./plugins/my-review-kit"
    }
  ]
}
```

要点:市场 `name` 就是安装命令里 `@` 后面那截(`my-review-kit@team-marketplace`);插件条目的 `name` 必须与 `plugin.json` 的 `name` 一致;`source` 是相对市场根目录的路径(以后加新插件 = 建新目录 + 在 `plugins` 数组加一条)。

### 5. 校验 + 打 zip

```bash
# 校验插件(清单格式、组件布局、钩子占位符都会查)
claude plugin validate ~/PycharmProjects/team-marketplace/plugins/my-review-kit

# 打包(zip 会保留脚本的可执行位)
cd ~/PycharmProjects
zip -r team-marketplace.zip team-marketplace
```

`validate` 通过再分发;报错信息会直接指出是哪个文件哪个字段的问题。

## 安装与使用

### 本机安装(目录方式)

```bash
# 1. 注册市场(指向本地目录即可,不一定要 git 仓库)
claude plugin marketplace add ~/PycharmProjects/team-marketplace
# 2. 安装插件
claude plugin install my-review-kit@team-marketplace
```

或者在 Claude Code 会话里用斜杠命令,效果相同:

```
/plugin marketplace add ~/PycharmProjects/team-marketplace
/plugin install my-review-kit@team-marketplace
```

**重启会话后生效**。装好后所有组件带插件命名空间,例如:

- 子 agent:`my-review-kit:code-reviewer`(派发审查任务时用全名)
- 命令:`/my-review-kit:opsx:propose`
- 钩子:自动生效,改 `.env` 会被拦截

### 分发给团队(git 方式)

把 `team-marketplace/` 推到团队 git 仓库,同事两条命令:

```
/plugin marketplace add <git仓库地址>
/plugin install my-review-kit@team-marketplace
```

直接发 zip 也行:解压后按上面「目录方式」安装。

### 更新版本

改完插件内容后:`plugin.json` 里把 `version` 加一位 → 同事执行 `/plugin marketplace update team-marketplace` + `/plugin` 里更新插件(或重装)即可拿到新版。

## 注意事项(本项目踩过的点)

1. **钩子会重复拦截**:项目 `.claude/settings.json` 里原有的 PreToolUse 钩子与插件钩子是两份注册,装了插件后可以删掉 settings.json 里那段 `hooks` 配置,避免每次 Edit/Write 跑两遍脚本。
2. **`settings.local.json` 永远不打包**:个人权限白名单,含本机绝对路径。
3. **code-reviewer 的审查规则是本项目定制的**(硬约束、验证方式都指向本 RAG 仓库),跨项目团队使用需改 `agents/code-reviewer.md` 的内容。
4. **组件内容原样拷贝、不做改写**:打包只解决「分发」,agent/命令/技能内部引用的是 OpenSpec CLI(`openspec` 命令),使用者机器上需自行安装。
