# Understand-Anything 小白使用教程

> 插件地址:https://github.com/Egonex-AI/Understand-Anything
> v2.9.7,安装在用户级,所有项目都能用

## 一、这是干什么的?

一句话:**把一个陌生代码库变成一张可以点、可以搜、可以提问的「地图」**。

你是不是有过这种经历——接手一个项目,面对几十上百个文件完全不知道从哪看起?这个插件就是解决这个问题的:

1. 它让 AI 把整个项目读一遍,搞清楚每个文件是干嘛的、谁调用谁;
2. 生成一张**交互式知识图谱**:每个文件/函数/类是图上的一个点,点与点之间连线表示依赖关系;
3. 自动在浏览器里打开一个可视化页面,你可以像逛地图一样浏览项目;
4. 还能直接向 AI 提问,比如「上传文件之后数据是怎么流转的?」,它会基于图谱回答,比裸问准确得多。

## 二、第一次使用:三步走

### 第 0 步:重启 Claude Code(必做!)

插件是刚装好的,**当前已经打开的会话看不到它**。退出 Claude Code,在项目目录下重新运行 `claude` 进入,新插件才会加载。

### 第 1 步:分析项目,生成知识图谱

在 Claude Code 里输入:

```
/understand --language zh
```

- `--language zh` 表示图谱里的所有说明文字(文件摘要、描述等)都用**中文**生成。不加这个参数默认是英文,别忘了写。
- 之后 AI 会分 7 个阶段干活:扫描文件 → 逐个分析 → 提取关系 → 组装图谱 → 质量检查……过程中会不断打印进度,耐心等就行。
- **耗时与费用**:小项目几分钟;大项目(几百个文件)可能要十几分钟,并且会消耗较多 token(因为每个文件都要 AI 读一遍)。建议在网络空闲、不赶时间的时候跑。

跑完后项目里会多出一个 `.ua/` 目录,里面的 `knowledge-graph.json` 就是图谱数据(已经加入 `.gitignore`,不会被误提交)。

### 第 2 步:打开可视化仪表盘

```
/understand-dashboard
```

浏览器会自动打开一个页面,你就能看到整张知识图谱了。常见玩法:

- **看整体**:缩放、拖动,先对项目结构有个全局印象;
- **搜节点**:搜索框里输入文件名或函数名,直接定位;
- **点节点**:点开任何一个文件/函数,能看到 AI 写的中文摘要和它的上下游依赖;
- **顺藤摸瓜**:沿着连线点下去,就是一条真实的调用链路,比自己翻代码快得多。

### 第 3 步:向图谱提问

回到 Claude Code:

```
/understand-chat 用户上传的文件是怎么一步步被切分和入库的?
```

它会基于刚生成的图谱回答,并附上相关文件的位置,回答末尾一般会给出可点击的 `文件:行号` 引用,直接跳转看代码。

## 三、常用命令速查表

| 命令 | 干什么用 | 什么时候用 |
|---|---|---|
| `/understand` | 分析项目,生成/更新知识图谱 | 第一次用,或代码改动较多之后 |
| `/understand-dashboard` | 打开浏览器可视化页面 | 想看图、逛项目的时候 |
| `/understand-chat <问题>` | 基于图谱向 AI 提问 | 想知道「某功能是怎么实现的」 |
| `/understand-explain <文件/函数>` | 深入讲解某一个文件、函数、模块 | 看图不够,想精读某处代码 |
| `/understand-onboard` | 生成一份新人上手指南 | 接手新项目、或带新人入门 |
| `/understand-diff` | 分析 git 改动:改了什么、影响哪些模块、有什么风险 | 写完代码自查,或看别人的 PR |

另外三个偏进阶,小白阶段可以先不管:

- `/understand-domain` — 从代码里提取**业务流程图」(不关心代码细节,只关心业务怎么流转);
- `/understand-knowledge` — 分析 Markdown 写成的知识库/wiki,而不是代码;
- `/understand-figma` — 分析 Figma 设计稿(需要额外配置 Figma token)。

## 四、`/understand` 的常用参数

```
/understand --language zh            ← 图谱文字用中文(推荐每次都带)
/understand --full                   ← 强制从头重建图谱(默认是增量更新,只分析变过的文件)
/understand --exclude "tests/*,docs/*"  ← 排除不想分析的目录
/understand --auto-update            ← 每次 git 提交后自动更新图谱
```

参数可以组合,例如:

```
/understand --language zh --exclude "static/*,blobs/*"
```

## 五、推荐的日常使用习惯

1. **新项目第一次打开**:`/understand --language zh` → `/understand-dashboard` 逛一圈 → 有疑问就 `/understand-chat`;
2. **日常改代码**:改完想让图谱跟上,再跑一次 `/understand`(只分析改动过的文件,很快);写完一个功能可以用 `/understand-diff` 自查影响面;
3. **精读某段代码**:先用 `/understand-chat` 定位到相关文件,再用 `/understand-explain` 深挖;
4. **交给同事/新人**:跑一次 `/understand-onboard` 生成上手文档。

## 六、常见问题

**Q1:命令没反应/提示找不到?**
说明会话是在装插件之前开的。退出 Claude Code 重新进一次就好。

**Q2:分析到一半可以中断吗?**
可以(Ctrl+C 或 Esc),但图谱可能不完整。下次重跑 `/understand` 会自动补全;实在乱了就 `/understand --full` 全量重建。

**Q3:会一直消耗 token 吗?**
不会。这个插件平时完全不占上下文(常驻成本约 0),只有你主动敲上面那些命令时才开始干活、才开始消耗。

**Q4:`.ua/` 目录是什么?要提交到 git 吗?**
是图谱数据,不用提交——已经帮你加进 `.gitignore` 了,放着不管即可。

**Q5:怎么更新/卸载?**

```bash
claude plugin update understand-anything     # 更新
claude plugin uninstall understand-anything  # 卸载
```

## 七、拿当前项目练手

这个 RAG 项目就是很好的第一个实验对象。重启 Claude Code 后依次输入:

```
/understand --language zh --exclude "static/*,blobs/*,openspec/*"
/understand-dashboard
/understand-chat 上传的文档从入库到被检索重排,完整经过了哪些模块?
```

跑通这一套,你就已经会用了。
