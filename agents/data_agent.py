"""Parent LangGraph agent that routes requests to SQL, ETL, or RAG agents."""

from __future__ import annotations

import logging
import os
import sys
from typing import Annotated, Any, TypedDict

# Ensure the project root is importable when this module is run directly.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agents.etl_analyst import etl_analyst
from agents.rag_agent import rag_node
from agents.sql_analyst import sql_analyst
from logging_config import setup_logging
from models.schema import RouterSchema
from utils.llm_pick import get_base_llm

setup_logging()
logger = logging.getLogger(__name__)


class DataAgentSchema(TypedDict):
    """State shared by the parent agent's graph nodes."""

    messages: Annotated[list[BaseMessage], add_messages]
    route_response: str


logger.info("Initializing Data Agent")
llm = get_base_llm("medium")
agent_router = llm.with_structured_output(RouterSchema)
logger.info("Data Agent router initialized")


def _last_user_text(state: DataAgentSchema) -> str:
    """Return the latest message's text, validating the input state."""
    messages = state.get("messages", [])
    if not messages:
        raise ValueError("Data Agent received no messages.")

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)

    last_message = messages[-1]
    content = last_message.content
    return content if isinstance(content, str) else str(content)


def _structured_value(result: Any, key: str):
    """Read a field from either a Pydantic result or a dictionary."""
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


def _as_text(value: Any) -> str:
    """Flatten a LangChain message payload into simple text."""
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        parts = []
        for item in value:
            text = _as_text(item)
            if text:
                parts.append(text)
        return "".join(parts).strip()

    if isinstance(value, dict):
        text = value.get("text") or value.get("content")
        if text:
            return _as_text(text)
        return ""

    if value is None:
        return ""

    return str(value).strip()


def _final_child_message(response: Any, agent_name: str) -> str:
    """Extract the last useful non-tool message from an agent response."""
    if hasattr(response, "model_dump"):
        response = response.model_dump()

    messages: list[Any] = []
    if isinstance(response, dict):
        messages = response.get("messages", [])
    elif isinstance(response, list):
        messages = response
    elif hasattr(response, "messages"):
        messages = getattr(response, "messages")

    for message in reversed(messages):
        if isinstance(message, dict):
            if message.get("type") in {"tool", "tool_call"}:
                continue
            text = _as_text(message.get("content") or message.get("text"))
            if text:
                return text
            continue

        if hasattr(message, "tool_calls") and getattr(message, "tool_calls", None):
            continue

        if hasattr(message, "content"):
            text = _as_text(message.content)
            if text:
                return text

    return f"I couldn't generate a useful response from the {agent_name} agent."


def router_node(state: DataAgentSchema) -> dict:
    logger.info("Router started")
    try:
        user_message = _last_user_text(state)
        result = agent_router.invoke(user_message)
        route = _structured_value(result, "answer")

        if not isinstance(route, str):
            raise ValueError(
                "Router output did not contain a string 'answer' field. "
                "Check models/schema.py and RouterSchema."
            )

        route = route.strip().lower()
        if route not in {"sql", "etl", "rag"}:
            raise ValueError(
                f"Invalid route '{route}'. Expected 'sql', 'etl', or 'rag'."
            )

        logger.info("Request routed to: %s", route)
        return {"route_response": route}
    except Exception:
        logger.exception("Router failed")
        raise


def _invoke_child_agent(state: DataAgentSchema, route: str) -> dict:
    """Invoke the selected specialist agent and append its final answer."""
    messages = state.get("messages", [])
    user_question = _last_user_text(state)

    try:
        if route == "sql":
            result = sql_analyst.invoke(
                {
                    "messages": messages,
                    "user_question": user_question,
                    "curated_ques": user_question,
                    "prompt_query_context": "",
                    "is_safe": "No",
                    "comments": "",
                    "generated_sql_query": "",
                    "sql_query_execution_result": "",
                    "final_answer": "",
                }
            )
        elif route == "etl":
            result = etl_analyst.invoke({"messages": messages})
        else:
            result = rag_node({"messages": messages})
    except Exception:
        logger.exception("Child agent invocation failed for route: %s", route)
        answer = f"I couldn't process that {route} request right now."
        return {"messages": [AIMessage(content=answer)]}

    answer = _final_child_message(result, route)
    return {"messages": [AIMessage(content=answer)]}


def route_edge(state: DataAgentSchema) -> str:
    """Return the selected route for conditional graph routing."""
    return state.get("route_response", "").strip().lower()


# Build the parent graph.
data_agent_graph = StateGraph(DataAgentSchema)
data_agent_graph.add_node("router_node", router_node)
data_agent_graph.add_node("sql_agent", lambda state: _invoke_child_agent(state, "sql"))
data_agent_graph.add_node("etl_agent", lambda state: _invoke_child_agent(state, "etl"))
data_agent_graph.add_node("rag_agent", lambda state: _invoke_child_agent(state, "rag"))

data_agent_graph.add_edge(START, "router_node")
data_agent_graph.add_conditional_edges(
    "router_node",
    route_edge,
    {
        "sql": "sql_agent",
        "etl": "etl_agent",
        "rag": "rag_agent",
    },
)
data_agent_graph.add_edge("sql_agent", END)
data_agent_graph.add_edge("etl_agent", END)
data_agent_graph.add_edge("rag_agent", END)

data_agent = data_agent_graph.compile()
logger.info("Data Agent graph compiled successfully")