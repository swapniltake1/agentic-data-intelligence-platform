from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import requests

from utils import api_processing
from utils.api_processing import (
    APIProcessingError,
    process_api_to_download,
    validate_api_url,
)


class FakeResponse:
    def __init__(
        self,
        data: bytes = b'[{"name":"Ada","score":7}]',
        *,
        content_type: str = "application/json",
        status_code: int = 200,
        content_length: str | None = None,
        chunk_size: int = 64 * 1024,
    ) -> None:
        self.data = data
        self.headers = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.status_code = status_code
        self.chunk_size = chunk_size
        self.closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        assert chunk_size == 64 * 1024
        for start in range(0, len(self.data), min(self.chunk_size, chunk_size)):
            yield self.data[start : start + min(self.chunk_size, chunk_size)]

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def temp_root(tmp_path: Path) -> Path:
    root = tmp_path / "api-work"
    root.mkdir()
    return root


@pytest.fixture
def mock_response(monkeypatch: pytest.MonkeyPatch):
    responses: list[FakeResponse] = []
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        response = responses.pop(0)
        return response

    monkeypatch.setattr(api_processing.requests, "get", fake_get)
    return responses, calls


def test_validate_api_url_rejects_unsupported_and_credential_urls() -> None:
    for url in ("", "file:///etc/passwd", "ftp://example.com/data", "https://user:pass@example.com"):
        with pytest.raises(APIProcessingError, match="HTTP|valid"):
            validate_api_url(url)


def test_validate_api_url_accepts_http_urls_and_query_strings() -> None:
    assert (
        validate_api_url("https://example.com/data?limit=5")
        == "https://example.com/data?limit=5"
    )


def test_success_writes_download_bytes_then_cleans_job_files(
    temp_root: Path,
    mock_response: Any,
) -> None:
    responses, calls = mock_response
    response = FakeResponse()
    responses.append(response)
    raw_seen_during_processing: list[bytes] = []

    def transform(records: list[dict[str, Any]], _instructions: str):
        job_dirs = list(temp_root.iterdir())
        assert len(job_dirs) == 1 and job_dirs[0].is_dir()
        raw_path = job_dirs[0] / "raw-response.json"
        raw_seen_during_processing.append(raw_path.read_bytes())
        return [
            {"name": record["name"].upper(), "score": record["score"] + 1}
            for record in records
        ]

    artifact = process_api_to_download(
        "https://example.com/data",
        params={"page": 2},
        headers={"X-Client": "test"},
        output_format="json",
        filename="../../safe result.json",
        transformer=transform,
        temp_root=temp_root,
    )

    assert artifact.filename == "safe_result.json"
    assert json.loads(artifact.data) == [{"name": "ADA", "score": 8}]
    assert artifact.record_count == 1
    assert artifact.mime_type == "application/json"
    assert calls[0]["params"] == {"page": 2}
    assert calls[0]["headers"] == {"X-Client": "test"}
    assert calls[0]["timeout"] == api_processing.REQUEST_TIMEOUT
    assert response.closed
    assert raw_seen_during_processing == [response.data]
    assert list(temp_root.iterdir()) == []


@pytest.mark.parametrize("output_format", ["csv", "json", "parquet"])
def test_supported_output_formats(
    temp_root: Path,
    mock_response: Any,
    output_format: str,
) -> None:
    responses, _ = mock_response
    responses.append(FakeResponse())

    artifact = process_api_to_download(
        "https://example.com/data",
        output_format=output_format,
        transformer=lambda records, _instructions: records,
        temp_root=temp_root,
    )

    assert artifact.filename == f"processed_data.{output_format}"
    assert artifact.data
    assert artifact.record_count == 1
    assert list(temp_root.iterdir()) == []
    if output_format == "csv":
        assert b"Ada" in artifact.data
    elif output_format == "json":
        assert json.loads(artifact.data)[0]["name"] == "Ada"
    else:
        output_path = temp_root / "check.parquet"
        output_path.write_bytes(artifact.data)
        assert pd.read_parquet(output_path).iloc[0]["name"] == "Ada"


def test_request_passes_basic_auth_without_logging_credentials(
    mock_response: Any,
) -> None:
    responses, calls = mock_response
    responses.append(FakeResponse())
    process_api_to_download(
        "https://example.com/data",
        auth=("test-user", "private-password"),
        transformer=lambda records, _instructions: records,
    )

    assert calls[0]["auth"] == ("test-user", "private-password")


@pytest.mark.parametrize(
    ("headers", "params"),
    [
        ({"Bad Header": "x"}, None),
        ({"X-Test": "value\r\nInjected: yes"}, None),
        (None, {"filters": {"nested": "not supported"}}),
    ],
)
def test_invalid_request_mappings_are_rejected(
    headers: dict[str, str] | None,
    params: dict[str, Any] | None,
) -> None:
    with pytest.raises(APIProcessingError):
        process_api_to_download(
            "https://example.com/data",
            headers=headers,
            params=params,
            transformer=lambda records, _instructions: records,
        )


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse(data=b"", content_type="application/json"), "empty"),
        (FakeResponse(data=b"{invalid", content_type="application/json"), "invalid JSON"),
        (FakeResponse(data=b"<html>", content_type="text/html"), "content type"),
        (FakeResponse(data=b"[]", content_type="application/json"), "no records"),
        (FakeResponse(data=b"{}", content_type="application/json"), "no records"),
        (
            FakeResponse(data=b'[1,2]', content_type="application/json"),
            "JSON objects",
        ),
    ],
)
def test_invalid_or_empty_api_data_fails_without_workspace_residue(
    monkeypatch: pytest.MonkeyPatch,
    temp_root: Path,
    response: FakeResponse,
    message: str,
) -> None:
    monkeypatch.setattr(api_processing.requests, "get", lambda *_args, **_kwargs: response)
    with pytest.raises(APIProcessingError, match=message):
        process_api_to_download(
            "https://example.com/data",
            transformer=lambda records, _instructions: records,
            temp_root=temp_root,
        )
    assert response.closed
    assert list(temp_root.iterdir()) == []


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 429, 500, 503])
def test_http_error_is_reported_and_response_is_closed(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    response = FakeResponse(status_code=status_code)
    monkeypatch.setattr(api_processing.requests, "get", lambda *_args, **_kwargs: response)

    with pytest.raises(APIProcessingError, match=f"HTTP {status_code}"):
        process_api_to_download("https://example.com/data")
    assert response.closed


def test_network_error_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_request(*_args: Any, **_kwargs: Any):
        raise requests.Timeout("Authorization: secret-token")

    monkeypatch.setattr(api_processing.requests, "get", fail_request)

    with pytest.raises(APIProcessingError, match="request failed"):
        process_api_to_download("https://example.com/data")
    assert "secret-token" not in caplog.text


def test_response_size_limit_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(content_length="100")
    monkeypatch.setattr(api_processing.requests, "get", lambda *_args, **_kwargs: response)

    with pytest.raises(APIProcessingError, match="size limit"):
        process_api_to_download(
            "https://example.com/data",
            max_response_bytes=10,
            transformer=lambda records, _instructions: records,
        )
    assert response.closed


def test_nonpositive_response_limit_is_rejected_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(*_args: Any, **_kwargs: Any):
        nonlocal called
        called = True
        raise AssertionError("Network should not be called")

    monkeypatch.setattr(api_processing.requests, "get", fail_if_called)
    with pytest.raises(APIProcessingError, match="must be positive"):
        process_api_to_download(
            "https://example.com/data",
            max_response_bytes=0,
        )
    assert not called


def test_streamed_response_limit_catches_missing_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(content_length=None)
    monkeypatch.setattr(api_processing.requests, "get", lambda *_args, **_kwargs: response)

    with pytest.raises(APIProcessingError, match="size limit"):
        process_api_to_download(
            "https://example.com/data",
            max_response_bytes=10,
            transformer=lambda records, _instructions: records,
        )
    assert response.closed


def test_unsupported_format_and_filename_extension_are_rejected() -> None:
    with pytest.raises(APIProcessingError, match="Unsupported output format"):
        process_api_to_download(
            "https://example.com/data",
            output_format="xlsx",
        )
    with pytest.raises(APIProcessingError, match="extension"):
        process_api_to_download(
            "https://example.com/data",
            output_format="csv",
            filename="report.xlsx",
        )


def test_ai_transform_is_called_in_batches_and_output_can_be_empty(
    monkeypatch: pytest.MonkeyPatch,
    temp_root: Path,
) -> None:
    records = [{"value": index} for index in range(api_processing.TRANSFORM_BATCH_SIZE + 1)]
    response = FakeResponse(data=json.dumps(records).encode())
    monkeypatch.setattr(api_processing.requests, "get", lambda *_args, **_kwargs: response)
    seen: list[int] = []

    class FakeLLM:
        def invoke(self, prompt: str):
            batch_json = prompt.split("Input records:\n", 1)[1]
            seen.append(len(json.loads(batch_json)))
            return api_processing._ProcessedRecords(records=[])

    monkeypatch.setattr(
        api_processing,
        "pick_llm",
        lambda *_args, **_kwargs: FakeLLM(),
    )
    artifact = process_api_to_download(
        "https://example.com/data",
        instructions="filter",
        temp_root=temp_root,
    )

    assert seen == [
        api_processing.TRANSFORM_BATCH_SIZE,
        1,
    ]
    assert artifact.record_count == 0
    assert list(temp_root.iterdir()) == []


def test_ai_provider_error_cleans_temp_workspace(
    monkeypatch: pytest.MonkeyPatch,
    temp_root: Path,
) -> None:
    response = FakeResponse()
    monkeypatch.setattr(api_processing.requests, "get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(
        api_processing,
        "pick_llm",
        lambda *_args, **_kwargs: _FailingLLM(),
    )

    with pytest.raises(APIProcessingError, match="AI processing failed"):
        process_api_to_download(
            "https://example.com/data",
            temp_root=temp_root,
        )
    assert list(temp_root.iterdir()) == []


class _FailingLLM:
    def invoke(self, _prompt: str):
        raise RuntimeError("provider failure")


def test_malformed_ai_output_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MalformedLLM:
        def invoke(self, _prompt: str):
            return {"unexpected": "shape"}

    monkeypatch.setattr(
        api_processing,
        "pick_llm",
        lambda *_args, **_kwargs: MalformedLLM(),
    )

    with pytest.raises(APIProcessingError, match="invalid records format"):
        api_processing._ai_transform([{"name": "Ada"}], "keep", llm=MalformedLLM())


def test_transform_failure_cleans_workspace_and_preserves_sibling_file(
    temp_root: Path,
    mock_response: Any,
) -> None:
    responses, _ = mock_response
    responses.append(FakeResponse())
    unrelated = temp_root / "user-owned.txt"
    unrelated.write_text("preserve", encoding="utf-8")

    with pytest.raises(APIProcessingError, match="processing or output"):
        process_api_to_download(
            "https://example.com/data",
            temp_root=temp_root,
            transformer=lambda _records, _instructions: (_ for _ in ()).throw(
                RuntimeError("failed")
            ),
        )

    assert unrelated.read_text(encoding="utf-8") == "preserve"
    assert list(temp_root.iterdir()) == [unrelated]


def test_output_failure_cleans_workspace(
    monkeypatch: pytest.MonkeyPatch,
    temp_root: Path,
    mock_response: Any,
) -> None:
    responses, _ = mock_response
    responses.append(FakeResponse())
    monkeypatch.setattr(
        pd.DataFrame,
        "to_csv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(APIProcessingError, match="output generation"):
        process_api_to_download(
            "https://example.com/data",
            temp_root=temp_root,
            transformer=lambda records, _instructions: records,
        )
    assert list(temp_root.iterdir()) == []


def test_processed_file_size_limit_cleans_workspace(
    monkeypatch: pytest.MonkeyPatch,
    temp_root: Path,
    mock_response: Any,
) -> None:
    responses, _ = mock_response
    responses.append(FakeResponse())
    monkeypatch.setattr(api_processing, "MAX_OUTPUT_BYTES", 1)

    with pytest.raises(APIProcessingError, match="processed file exceeds"):
        process_api_to_download(
            "https://example.com/data",
            temp_root=temp_root,
            transformer=lambda records, _instructions: records,
        )
    assert list(temp_root.iterdir()) == []


def test_concurrent_jobs_use_distinct_workspaces(
    monkeypatch: pytest.MonkeyPatch,
    temp_root: Path,
) -> None:
    class ConcurrentResponse(FakeResponse):
        def __init__(self, value: str) -> None:
            super().__init__(data=json.dumps([{"value": value}]).encode())

    monkeypatch.setattr(
        api_processing.requests,
        "get",
        lambda url, **_kwargs: ConcurrentResponse(url.rsplit("/", 1)[-1]),
    )

    def process(value: str):
        return process_api_to_download(
            f"https://example.com/{value}",
            output_format="json",
            temp_root=temp_root,
            transformer=lambda records, _instructions: records,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(process, ("first", "second"))

    assert json.loads(first.data)[0]["value"] == "first"
    assert json.loads(second.data)[0]["value"] == "second"
    assert list(temp_root.iterdir()) == []
