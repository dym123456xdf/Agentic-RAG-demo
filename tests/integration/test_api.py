"""API 集成测试 —— 用 httpx TestClient 验证 FastAPI 路由。

注意:这些测试 mock 掉 pipeline 层,不依赖真实 Milvus / LLM。
"""
from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("httpx", reason="httpx is required for API integration tests")
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture()
def client() -> Generator:
    """创建 FastAPI TestClient,跳过 startup 时连 Milvus。"""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def mock_pipeline() -> MagicMock:
    m = MagicMock()
    m.query.return_value = {
        "answer": "mock answer",
        "sources": [{"index": 1, "content": "chunk", "score": 0.9, "source": "doc.md"}],
        "meta": {"intent": "factual"},
    }
    m.ingest.return_value = {"files": 1, "chunks_ingested": 3}
    return m


class TestChatEndpoint:
    def test_chat_returns_answer(self, client: TestClient, mock_pipeline: MagicMock) -> None:
        with patch("app.api.chat.get_pipeline", return_value=mock_pipeline):
            resp = client.post("/chat", json={"question": "test", "history": []})
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "mock answer"
        assert len(body["sources"]) == 1

    def test_chat_requires_question(self, client: TestClient) -> None:
        resp = client.post("/chat", json={"history": []})
        assert resp.status_code == 422


class TestUploadEndpoints:
    def test_list_files_empty(self, client: TestClient) -> None:
        with patch("app.api.upload.get_store") as mock_store:
            mock_store.return_value.list_sources.return_value = {}
            resp = client.get("/upload/files")
        assert resp.status_code == 200
        body = resp.json()
        assert body["file_count"] == 0

    def test_list_files_with_data(self, client: TestClient) -> None:
        with patch("app.api.upload.get_store") as mock_store:
            mock_store.return_value.list_sources.return_value = {"doc.md": 5}
            resp = client.get("/upload/files")
        body = resp.json()
        assert body["file_count"] == 1
        assert body["total_chunks"] == 5

    def test_upload_dir_requires_path(self, client: TestClient) -> None:
        resp = client.post("/upload/dir", json={})
        assert resp.status_code == 400
