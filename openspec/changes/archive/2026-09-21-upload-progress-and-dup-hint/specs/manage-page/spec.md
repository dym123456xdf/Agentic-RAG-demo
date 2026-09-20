# Spec Delta

## ADDED Requirements

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