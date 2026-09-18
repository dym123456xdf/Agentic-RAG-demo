# Tasks

## 1. CLI 调用语法切换

- [x] 1.1 `app/rag/loader.py::convert_to_markdown` 改为 `mineru parse <path> --tier flash --wait <secs> --pages 1-1000 --limit 200000`,产物从 stdout 写到 `converted/<原文件名>.md`。验证:`grep "MINERU_BIN" loader.py` 看不到旧版 `-p path -o dir` 形态
- [x] 1.2 失败语义保持:非零退出 / 超时 / 空 stdout 抛 RuntimeError,带 `returncode` 与最近 500 字符 stderr。验证:故意改名让 mineru 报错,看 traceback 含文件名 + 摘要

## 2. 运行时依赖

- [x] 2.1 `mineru server start` 后台跑起来(PID 记录到 `/tmp` 或系统进程列表)。验证:`mineru server status` 显示服务在 listening
- [x] 2.2 服务监听端口因 8000 被 Docker Desktop 反向代理占用,FastAPI 改起 8011(仅启动参数,无代码变更)。验证:`curl http://127.0.0.1:8011/docs` 返回 200

## 3. 端到端验证

- [x] 3.1 PDF 上传 → MinerU 转换 → Milvus 入库全链路。验证:`POST /upload/files` 上传一份 PDF,响应含 `chunks_ingested>0` 与 `converted` 路径,`converted/<原文件名>.md` 落盘且文件非空
- [x] 3.2 管理页文件列表 `has_converted=true` + 转换产物只读接口返回全文。验证:`GET /upload/files` 中该 PDF 项 `has_converted=true`;`GET /upload/converted/<url-encoded-name>` 返回 JSON 含 `content` 且非空
- [x] 3.3 真实问答基于入库 PDF 出答案。验证:`POST /chat` 提交一个 PDF 内容相关问题,响应 `sources` 非空、`answer` 含具体事实

## 4. 配置恢复

- [x] 4.1 `.env` 中 `LLM_PROVIDER=glm` 改回 `minimax`(CLAUDE.md 默认)。验证:`grep LLM_PROVIDER .env` 显示 `minimax`