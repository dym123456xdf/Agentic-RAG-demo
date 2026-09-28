# manage-page

> 从 OpenSpec 变更 `add-manage-page-mysql-history` 同步而来。
> 2026-09-28 从 OpenSpec 变更 `enterprise-rag-upgrade` 同步而来。

## Purpose

提供独立于聊天首页的管理页面,集中承载文件入库管理(上传、目录入库、列表、统计)、MinerU 转换产物的人工核对查看,以及按会话分组的问答历史回溯,让首页保持纯聊天体验。

## Requirements

### Requirement: 管理页入口与首页职责分离

首页 SHALL 保留纯聊天界面(回答照常显示来源与 meta),侧边栏提供进入管理页的入口;上传、文件列表、统计等管理功能必须只出现在管理页。

#### Scenario: 从首页进入管理页
- **WHEN** 用户点击首页侧边栏的管理页入口
- **THEN** 浏览器打开管理页,文件管理与问答历史两个功能区块可见

#### Scenario: 首页不再显示管理功能
- **WHEN** 用户查看首页侧边栏
- **THEN** 不再出现上传框、目录入库、已入库文件列表与统计信息

### Requirement: 管理页文件管理

管理页 SHALL 提供与现有上传接口等价的文件管理功能:拖拽/点击上传文件、按服务器目录入库、展示已入库文件列表(文件名与 chunk 数)及向量总量统计。

#### Scenario: 上传文件并入库
- **WHEN** 用户在管理页拖拽或选择文件上传
- **THEN** 系统调用上传接口完成入库,展示本次入库片段数与跳过的重复文件

#### Scenario: 按目录入库
- **WHEN** 用户输入服务器目录路径并触发扫描
- **THEN** 系统调用目录入库接口,展示入库结果

#### Scenario: 查看已入库文件与统计
- **WHEN** 用户打开管理页或刷新列表
- **THEN** 展示全部已入库文件的名称与 chunk 数,以及向量总量与文件总数

### Requirement: 删除已入库文件

管理页文件列表 SHALL 对每个已入库文件提供删除入口;删除接口 `DELETE /upload/files/{name}` SHALL 联动清除三处:① Milvus 中 `doc_name == <name>` 的全部 chunk;② MinIO `uploads/<name>` 对象;③ MinIO `converted/<stem>/` 前缀下全部对象(含 md、`images/`、`assets/`,由 `remove_objects` 批量删除)。本地磁盘 SHALL 不再被读写;删除前 SHALL 有不可恢复确认,成功后刷新列表并提示。

#### Scenario: 删除后三处全部清除
- **WHEN** 用户在管理页删除一个已入库且含转换产物的文件
- **THEN** Milvus 中该 source 的 chunk 计数归零,MinIO `uploads/<name>` 与 `converted/<stem>/` 前缀下对象全部清空,`GET /upload/files` 列表与统计同步更新

#### Scenario: 删除前确认
- **WHEN** 用户点击某文件的删除按钮
- **THEN** 弹出不可恢复确认,取消则不删除,确认后执行

#### Scenario: 删除后重传生效
- **WHEN** 某文件被删除后,用户重新上传同名文件
- **THEN** 新文件内容被重新入库(不被幂等跳过),chunk 数按新内容计算

#### Scenario: 脏数据可清理
- **WHEN** MinIO 源文件已丢失但 Milvus 仍有该 source 的 chunk(历史残留)
- **THEN** 删除接口仍返回成功并清掉 Milvus 侧 chunk,MinIO 不存在的对象不报错

#### Scenario: 非法文件名拒绝
- **WHEN** 删除接口收到含路径分隔符、`..` 或不在允许后缀白名单内的名称
- **THEN** 返回 404,不发生任何删除

### Requirement: 转换产物人工核对

管理页的文件列表 SHALL 对存在 MinerU 转换产物的文件(PDF/DOCX/PPTX)提供"查看转换结果"入口,点击后展示 MinIO `converted/<stem>/<stem>.md` 对象的完整内容,供人工核对转换准确性;内容中的图片相对引用 SHALL 被改写为 `/converted/<stem>/images/<file>.<ext>` 绝对 URL 并渲染为真实图片(URL 仍走 `minio-storage` 规格定义的后端代理路由,前端零改动)。

#### Scenario: 查看转换产物
- **WHEN** 用户点击某 PDF 文件的"查看转换结果"
- **THEN** 页面展示该文件对应的转换 Markdown 全文,内容来源为 MinIO `converted/<stem>/<stem>.md` 对象

#### Scenario: 弹层内图片显示
- **WHEN** 转换产物 md 含 `![image](images/xxx.png)` 相对引用
- **THEN** 弹层渲染时该引用变为 `<img src="/converted/<name>/images/xxx.png">`,浏览器能拉到并显示真实图片,而非 `![...]` 语法原文或裂图

#### Scenario: 文本内容仍可读
- **WHEN** 弹层渲染含图片的 md
- **THEN** 标题、段落、表格、代码块都正常显示,文本不会被图片破坏排版

#### Scenario: 原生文本文件无入口
- **WHEN** 已入库文件为 `.md`/`.markdown`/`.txt` 等原生文本
- **THEN** 该文件不显示"查看转换结果"入口

#### Scenario: 未启用 MinerU 时无入口
- **WHEN** 服务配置未启用 MinerU(`MINERU_ENABLED=false`)
- **THEN** 文件列表中任何文件都不显示"查看转换结果"入口

### Requirement: 转换产物接口的访问安全

转换产物读取接口 SHALL 只允许访问 MinIO 桶内 `converted/` 前缀的 `.md` 对象;任何路径穿越尝试必须被拒绝(不构造跨桶路径、不响应对象内容)。

#### Scenario: 拒绝路径穿越
- **WHEN** 请求的文件名包含 `..`、绝对路径或目录分隔符
- **THEN** 接口返回 400/404 错误,不返回任何文件内容

#### Scenario: 请求不存在的产物
- **WHEN** 请求的文件名在 MinIO 桶 `converted/` 前缀下不存在对应对象
- **THEN** 接口返回 404 错误

### Requirement: 问答历史回溯

管理页 SHALL 按会话分组展示问答历史:每个会话可展开查看其全部问答记录,每条记录必须展示答案、参考来源(文件名、相关性分数、片段内容)与调试 meta(意图、改写、召回、精排数量)。

#### Scenario: 按会话浏览历史
- **WHEN** 用户在问答历史 tab 选择某会话
- **THEN** 按时间正序展示该会话全部问答记录,单条可展开来源与 meta 详情

#### Scenario: 无历史的空态
- **WHEN** 当前没有任何会话或所选会话无消息
- **THEN** 展示明确的空态提示,不报错

### Requirement: 上传进度与结果反馈

管理页 SHALL 在用户触发文件上传(点击/拖拽)后,提供入库过程与结果的可见反馈:① 入口先调用 `GET /upload/files` 做前端预检,任一文件名命中已入库列表即弹模态告知并不发任何入库请求(预检失败时回退到 err toast 提示用户刷新);② 全部新增才走正常上传流程,期间显示 Loading 遮罩(含正在处理的文件名列表);③ 成功展示短 toast `✓ 入库 N 个片段,共 M 条`(N = `chunks_ingested`,M = `total_entities`),持续 2.2s;④ 失败展示 err toast,文案透传后端 `detail` 或网络错误信息,持续 6s;⑤ 重复上传场景独立走模态弹窗(标题 + 副标题 + 文件名 chip + 「我知道了」按钮 + 多种关闭方式),不进 toast 体系。

#### Scenario: 入库期间显示 Loading 遮罩

- **WHEN** 用户在管理页上传区点击或拖拽文件并触发入库请求
- **THEN** 页面 SHALL 立即显示一个半透明 Loading 遮罩,中央展示:① 旋转图标(`.loading-spinner`)、② 「正在入库,请稍候…」文字(`.loading-text`)、③ 本次提交的文件名列表(`.loading-files`,独立 `<ul>`)。三块内容垂直堆叠在 `.loading-card` 白底卡片内;遮罩在入库 fetch 响应到达或异常抛出时立即关闭

#### Scenario: 选择含已上传文件时前端拦截

- **WHEN** 用户选择文件并触发上传(点击或拖拽),且选择中至少有一个文件名命中已入库文件列表(`GET /upload/files` 的响应)
- **THEN** 管理页 SHALL **不发任何入库请求**(避免无意义的后端处理与 Loading 遮罩闪现),而是 SHALL 弹出重复上传提示模态:标题为「以下文件已上传,请勿重复上传」,副标题「请从选择中移除这些文件后重新上传。」,body 列出**全部**已存在的文件名 chip(不做截断,不做折叠),footer 提供「我知道了」按钮,点击后仅关闭弹窗,不会触发任何入库;在用户主动关闭前,弹窗 SHALL 持续显示且 SHALL 阻断下层操作

#### Scenario: 选择全新文件时正常上传

- **WHEN** 用户选择文件并触发上传,且所有文件名都不在已入库文件列表中
- **THEN** 管理页 SHALL 正常提交入库请求,期间显示 Loading 遮罩,响应到达后展示成功 toast,文案 SHALL 形如 `✓ 入库 N 个片段,共 M 条`(N = `chunks_ingested`,M = `total_entities`)

#### Scenario: 失败提示

- **WHEN** 入库 fetch 抛出网络异常或 HTTP 状态非 2xx
- **THEN** SHALL 展示错误 toast(`.toast.err`),文案直接显示后端 `detail` 字段或网络错误信息,且 toast SHALL 持续至少 6 秒以确保用户看清错误原因

#### Scenario: 文件名过多时模态 body 内部滚动

- **WHEN** 模态展示的已存在文件名 chip 数量超过可视区域(`.dup-body` `max-height: 50vh` 容纳不下)
- **THEN** `.dup-body` SHALL 出现竖向滚动条供用户滚动查看完整列表,模态外框 SHALL **不被撑高**(保留原 max-height 居中视觉),且**任何文件名都不被截断、不被折叠、不被 `等 N 个文件` 占位**(模态的核心信息就是「全部已存在文件名」,必须保留完整)

#### Scenario: Loading 遮罩与 fetch 生命周期一致

- **WHEN** `fetch` 已发出但响应未到达时(用户在等待)
- **THEN** Loading 遮罩 SHALL 保持显示且不接受用户再次点击上传区(避免重复入库)
- **WHEN** `fetch` 响应到达(无论成功或失败)
- **THEN** Loading 遮罩 SHALL 立即消失,允许用户继续操作
