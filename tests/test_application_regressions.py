from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from agents import data_agent
from agents import etl_analyst
from agents.rag_agent import build_context, get_latest_user_question
from agents.sql_analyst import deterministic_sql_safety_check
from rag import retriever
from utils import api_processing, etl_tools
from utils.etl_tools import ETLTools


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([{"id": 1}, {"id": 2}], 2),
        ({"results": [{"id": 1}]}, 1),
        ({"data": [{"id": 1}]}, 1),
        ({"id": 1, "nested": {"x": 2}}, 1),
        (None, 0),
    ],
)
def test_etl_api_payload_record_normalization(payload: Any, expected: int) -> None:
    assert len(ETLTools._get_records(payload)) == expected


def test_etl_agent_api_tool_publishes_processed_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = api_processing.DownloadArtifact(
        data=b'[{"value":2}]',
        filename="processed.json",
        mime_type="application/json",
        record_count=1,
    )
    calls: list[dict[str, Any]] = []

    def fake_process(url: str, **kwargs: Any) -> api_processing.DownloadArtifact:
        calls.append({"url": url, **kwargs})
        return artifact

    monkeypatch.setattr(etl_analyst, "process_api_to_download", fake_process)
    with api_processing.capture_api_download() as captured:
        result = etl_analyst.extract_load_tool.invoke(
            {
                "url": "https://example.com/data",
                "output_format": "json",
                "instructions": "Keep active records.",
            }
        )

    assert captured["artifact"] == artifact
    assert "ready for download" in result
    assert calls == [
        {
            "url": "https://example.com/data",
            "output_format": "json",
            "instructions": "Keep active records.",
        }
    ]


def test_legacy_etl_api_helper_rejects_output_path_traversal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def unexpected_process(*_args: Any, **_kwargs: Any):
        nonlocal called
        called = True
        raise AssertionError("API processing must not start for an unsafe path")

    monkeypatch.setattr(api_processing, "process_api_to_download", unexpected_process)
    result = ETLTools().extract_load(
        "https://example.com/data",
        "../../outside",
        "json",
    )

    assert "must be inside the project" in result
    assert not called


def test_legacy_etl_api_helper_saves_only_processed_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    artifact = api_processing.DownloadArtifact(
        data=b'[{"processed":true}]',
        filename="processed.json",
        mime_type="application/json",
        record_count=1,
    )
    monkeypatch.setattr(
        etl_tools,
        "__file__",
        str(project_root / "utils" / "etl_tools.py"),
    )
    monkeypatch.setattr(api_processing, "process_api_to_download", lambda *_args, **_kwargs: artifact)

    result = ETLTools().extract_load(
        "https://example.com/data",
        "output",
        "json",
    )

    assert "Processed data successfully saved" in result
    assert (project_root / "output" / artifact.filename).read_bytes() == artifact.data
    assert sorted(path.name for path in (project_root / "output").iterdir()) == [
        artifact.filename
    ]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT id FROM users", True),
        ("WITH users AS (SELECT 1) SELECT * FROM users", True),
        ("", False),
        ("DELETE FROM users", False),
        ("SELECT 1; DROP TABLE users", False),
        ("SELECT pg_read_file('/etc/passwd')", False),
        ("SELECT 1 -- comment", False),
        ("BEGIN", False),
    ],
)
def test_deterministic_sql_safety_regressions(sql: str, expected: bool) -> None:
    safe, _reason = deterministic_sql_safety_check(sql)
    assert safe is expected


def test_rag_latest_question_skips_blank_and_non_user_messages() -> None:
    messages = [
        HumanMessage(content="old question"),
        AIMessage(content="answer"),
        HumanMessage(content=""),
    ]
    assert get_latest_user_question(messages) == "old question"


def test_rag_build_context_deduplicates_source_names() -> None:
    documents = [
        Document(page_content="fare details", metadata={"source": r"docs\fares.md"}),
        Document(page_content="payment details", metadata={"source": "other/fares.md"}),
    ]
    context, sources = build_context(documents)

    assert "fare details" in context
    assert "payment details" in context
    assert sources == ["fares.md"]


def test_retrieval_rejects_blank_questions_and_invalid_top_k() -> None:
    with pytest.raises(ValueError, match="Question cannot be empty"):
        retriever.retrieve_documents("  ")
    with pytest.raises(ValueError, match="k must be at least 1"):
        retriever.get_retriever(k=0)


def test_retrieval_formats_documents_without_live_vector_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRetriever:
        def invoke(self, question: str) -> list[Document]:
            assert question == "fare"
            return [
                Document(
                    page_content="Fare information.",
                    metadata={"source": "knowledge/fares.pdf", "page": 0},
                )
            ]

    class FakeVectorStore:
        def as_retriever(self, **kwargs: Any) -> FakeRetriever:
            assert kwargs == {
                "search_type": "similarity",
                "search_kwargs": {"k": 2},
            }
            return FakeRetriever()

    monkeypatch.setattr(retriever, "get_vector_store", FakeVectorStore)
    context = retriever.retrieve_context("  fare ", k=2)

    assert "[Source 1: fares.pdf, page 1]" in context
    assert "Fare information." in context


@pytest.mark.parametrize("route", ["sql", "etl", "rag"])
def test_parent_graph_routes_to_the_expected_child_agent(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    class FakeRouter:
        def invoke(self, _question: str) -> dict[str, str]:
            return {"answer": route, "comments": ""}

    class FakeChild:
        def invoke(self, _state: Any) -> dict[str, list[AIMessage]]:
            return {"messages": [AIMessage(content=f"{route} complete")]}

    monkeypatch.setattr(data_agent, "_get_agent_router", lambda: FakeRouter())
    monkeypatch.setattr(data_agent, "sql_analyst", FakeChild())
    monkeypatch.setattr(data_agent, "etl_analyst", FakeChild())
    monkeypatch.setattr(data_agent, "rag_node", lambda _state: {
        "messages": [AIMessage(content="rag complete")]
    })

    result = data_agent.data_agent.invoke(
        {
            "messages": [HumanMessage(content=f"test {route}")],
            "route_response": "",
        }
    )

    assert result["route_response"] == route
    assert result["messages"][-1].content == f"{route} complete"


def test_parent_router_rejects_invalid_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRouter:
        def invoke(self, _question: str) -> dict[str, str]:
            return {"answer": "unknown"}

    monkeypatch.setattr(data_agent, "_get_agent_router", lambda: FakeRouter())

    with pytest.raises(ValueError, match="Invalid route"):
        data_agent.router_node(
            {"messages": [HumanMessage(content="help")], "route_response": ""}
        )


def test_main_streamlit_app_renders_without_network_calls() -> None:
    from streamlit.testing.v1 import AppTest

    project_root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=20)

    assert not app.exception
    assert any(button.label == "Fetch and process API data" for button in app.button)
    assert any(button.label == "Test All Providers" for button in app.button)


def test_streamlit_api_form_exposes_processed_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    from utils import api_processing

    def fake_process(url: str, **kwargs: Any) -> api_processing.DownloadArtifact:
        assert url == "https://example.com/data"
        assert kwargs["output_format"] == "json"
        return api_processing.DownloadArtifact(
            data=b'[{"value":1}]',
            filename="result.json",
            mime_type="application/json",
            record_count=1,
        )

    monkeypatch.setattr(api_processing, "process_api_to_download", fake_process)
    project_root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=20)
    app.text_input(key="api_processing_url").set_value("https://example.com/data")
    app.selectbox(key="api_processing_format").select("json")
    app.button(
        key="FormSubmitter:api_processing_form-Fetch and process API data"
    ).click()
    app.run(timeout=20)

    assert not app.exception
    assert app.session_state["api_download"]["data"] == b'[{"value":1}]'
    download_buttons = app.get("download_button")
    assert any(button.label == "Download processed file" for button in download_buttons)
    assert any("Processed 1 record" in message.value for message in app.success)


def test_streamlit_api_errors_are_safe_and_keep_download_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    from utils import api_processing

    def fail_process(*_args: Any, **_kwargs: Any):
        raise api_processing.APIProcessingError(
            "The API response contains invalid JSON."
        )

    monkeypatch.setattr(api_processing, "process_api_to_download", fail_process)
    project_root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=20)
    app.text_input(key="api_processing_url").set_value("https://example.com/data")
    app.button(
        key="FormSubmitter:api_processing_form-Fetch and process API data"
    ).click()
    app.run(timeout=20)

    assert not app.exception
    assert any("invalid JSON" in message.value for message in app.error)
    assert not app.get("download_button")


def test_streamlit_etl_agent_exposes_processed_api_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    artifact = api_processing.DownloadArtifact(
        data=b'[{"value":2}]',
        filename="agent-result.json",
        mime_type="application/json",
        record_count=1,
    )
    monkeypatch.setattr(etl_analyst, "process_api_to_download", lambda *_args, **_kwargs: artifact)

    def invoke_agent(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        etl_analyst.extract_load_tool.invoke(
            {
                "url": "https://example.com/data",
                "output_format": "json",
                "instructions": "Keep active records.",
            }
        )
        return {
            "messages": [AIMessage(content="The processed file is ready.")],
            "route_response": "etl",
        }

    monkeypatch.setattr(data_agent.data_agent, "invoke", invoke_agent)
    project_root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=20)
    app.chat_input[0].set_value("Process the API data").run(timeout=20)

    assert not app.exception
    assert app.session_state["api_download"]["data"] == artifact.data
    assert any(
        button.label == "Download processed file"
        for button in app.get("download_button")
    )
