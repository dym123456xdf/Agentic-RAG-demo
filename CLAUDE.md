# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

个人知识库 RAG 服务:FastAPI + llama-index + Milvus,单页前端在 `static/index.html`。注释与 docstring 一律用中文。

## 运行与验证

```bash
conda run -n rag uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

- 依赖装在 Python 3.11 conda 环境 `rag`;仓库没有 requirements.txt / pyproject.toml / tests —— 不存在,不要找。
- 验证手段就是启动服务、手动调 API(上传 → 提问)。
- 服务起不来先查 `.env`:`app/core/config.py` 在 import 时读配置并快速失败。

## IMPORTANT — 硬约束

- 切换 `EMBEDDING_PROVIDER` = 更换向量空间,必须清空 Milvus collection 全量重新入库。
- Milvus COSINE distance 越小越相关,与相似度语义相反。
- 入库按文件名幂等跳过:同名文件重传不入库,改内容不会更新索引。
- 各模块的坑(切分、metadata、重排语义等)写在各自文件的 docstring 里 —— 动哪个模块,先读哪个文件的头部注释。

## 工作流

变更走 OpenSpec 规范驱动:`/opsx:*` 命令(propose / apply / archive),产物在 `openspec/`。
