"""最小 Anthropic → OpenAI 协议代理。

设计目标:
- Claude Code 配 ANTHROPIC_BASE_URL=http://127.0.0.1:8082,本代理转给 OpenAI 兼容 provider。
- 通过环境变量 CCP_PROVIDER 切换 provider(minimax / agnes / glm)。
- 只支持 non-stream + 单轮消息(够 Claude Code 主对话用)。
- 不做 tool_use / extended_thinking / cache_control —— 砍掉,够用即可。

启动:
    /opt/anaconda3/envs/rag/bin/python -m uvicorn app.proxy:app --host 127.0.0.1 --port 8082

环境变量(必填):
    CCP_PROVIDER     minimax | agnes | glm
    CCP_API_KEY      OpenAI 兼容 provider 的 key
    CCP_BASE_URL     OpenAI 兼容 provider 的 base_url(完整 /v1 端点)
    CCP_BIG_MODEL    主对话模型名(如 MiniMax-M3[1m] / agnes-2.5-flash / GLM-5.3)
    CCP_SMALL_MODEL  快速档模型名(预处理任务,fallback 主模型)
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

app = FastAPI()

PROVIDER = os.getenv("CCP_PROVIDER", "").lower()
API_KEY = os.getenv("CCP_API_KEY", "")
BASE_URL = os.getenv("CCP_BASE_URL", "")
BIG_MODEL = os.getenv("CCP_BIG_MODEL", "")
SMALL_MODEL = os.getenv("CCP_SMALL_MODEL", BIG_MODEL)


def _check_env() -> None:
    missing = [
        k
        for k, v in {
            "CCP_PROVIDER": PROVIDER,
            "CCP_API_KEY": API_KEY,
            "CCP_BASE_URL": BASE_URL,
            "CCP_BIG_MODEL": BIG_MODEL,
        }.items()
        if not v
    ]
    if missing:
        raise RuntimeError(f"代理环境变量缺失: {', '.join(missing)}")


@app.get("/")
async def root() -> dict[str, str]:
    """健康检查 + 当前 provider 状态。"""
    return {
        "provider": PROVIDER,
        "base_url": BASE_URL,
        "big_model": BIG_MODEL,
        "small_model": SMALL_MODEL,
        "status": "ok",
    }


def _to_openai_messages(anthropic_messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Anthropic messages → OpenAI messages。

    Claude Code 发的 content 通常是 str(简单文本),不做 tool_use / image 兼容。
    多轮 system 单独提取,合并到第一条 system 消息。
    """
    out: list[dict[str, str]] = []
    for m in anthropic_messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            # 提取 text 块(Claude Code 现在基本不发 content blocks)
            content = "".join(
                blk.get("text", "") for blk in content if blk.get("type") == "text"
            )
        out.append({"role": role, "content": content})
    return out


@app.post("/v1/messages")
async def messages(req: Request) -> JSONResponse:
    """Anthropic messages 端点 → OpenAI chat/completions → Anthropic 响应格式。

    只实现 non-stream;stream=False 直接返回完整 JSON。
    """
    _check_env()
    body = await req.json()
    model_in = body.get("model", BIG_MODEL)
    # haiku → small,其他 → big(proxy 不存角色映射,按模型名简单分)
    if "haiku" in model_in.lower():
        target_model = SMALL_MODEL
    else:
        target_model = BIG_MODEL
    # 如果请求里直接写明模型名(比如 agnes-2.5-flash),用请求里的
    if model_in and model_in not in ("MiniMax-M3[1m]", "GLM-5.3", "agnes-2.5-flash"):
        target_model = model_in

    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    try:
        oai_resp = await client.chat.completions.create(
            model=target_model,
            messages=_to_openai_messages(body.get("messages", [])),
            max_tokens=body.get("max_tokens", 1024),
            temperature=body.get("temperature", 1.0),
            stream=False,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e!s}") from e

    choice = oai_resp.choices[0]
    text = choice.message.content or ""

    # Anthropic 响应壳(只填 Claude Code 实际读的字段)
    return JSONResponse(
        {
            "id": oai_resp.id or "msg_proxy",
            "type": "message",
            "role": "assistant",
            "model": target_model,
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": getattr(oai_resp.usage, "prompt_tokens", 0) if oai_resp.usage else 0,
                "output_tokens": getattr(oai_resp.usage, "completion_tokens", 0) if oai_resp.usage else 0,
            },
        }
    )