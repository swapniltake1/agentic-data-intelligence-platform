import logging
import json
import time
import uuid
from datetime import datetime

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from logging_config import setup_logging
from agents.data_agent import data_agent
from utils.api_processing import (
    APIProcessingError,
    SUPPORTED_OUTPUTS,
    capture_api_download,
    process_api_to_download,
)
from utils.llm_pick import (
    LLMConfigurationError,
    capture_llm_metadata,
    get_provider_status,
    test_provider,
)
from utils.ui_errors import safe_agent_error_message

setup_logging()
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Data Intelligence",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

AGENT_RECURSION_LIMIT = 20

st.markdown(
    """
    <style>
    .block-container {
        max-width: 900px;
        padding-top: 1.5rem;
        padding-bottom: 7rem;
    }
    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(128, 128, 128, 0.2);
    }
    section[data-testid="stSidebar"] .stButton > button {
        text-align: left;
        border-radius: 9px;
        border: 0;
    }
    div[data-testid="stChatInput"] {
        max-width: 900px;
        margin-left: auto;
        margin-right: auto;
    }
    div[data-testid="stToolbar"] {
        visibility: visible;
    }
    button[title="Deploy"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def extract_message_text(message) -> str:
    """
    Extract text content from a LangChain message.

    Handles:
    - String content
    - List-based structured content
    - Dictionary text blocks
    """

    if not hasattr(message, "content"):
        return ""

    content = message.content

    # Normal text response.
    if isinstance(content, str):
        return content.strip()

    # Structured content response.
    if isinstance(content, list):

        text_parts = []

        for part in content:

            if isinstance(part, str):
                text_parts.append(part)

            elif isinstance(part, dict):

                text = part.get("text")

                if text:
                    text_parts.append(str(text))

        return "".join(text_parts).strip()

    if content is None:
        return ""

    return str(content).strip()


def extract_final_answer(result, route: str) -> str | None:
    """
    Extract the final user-facing AI response from the Data Agent.

    AIMessage is preferred so that:
    - HumanMessage is never shown as an answer.
    - Tool-call messages are not shown.
    - Intermediate agent messages are not accidentally displayed.

    Args:
        result: Data Agent result.
        route: SQL or ETL.

    Returns:
        Final AI response or None.
    """

    if not isinstance(result, dict):

        logger.error(
            "Data Agent returned unexpected result type: %s",
            type(result).__name__,
        )

        return None

    messages = result.get(
        "messages",
        [],
    )

    if not messages:

        logger.warning(
            "Data Agent returned no messages"
        )

        return None

    logger.debug(
        "Data Agent returned %d message(s)",
        len(messages),
    )

    # --------------------------------------------------------
    # Primary: AIMessage
    # --------------------------------------------------------

    for message in reversed(messages):

        if not isinstance(message, AIMessage):
            continue

        # Ignore AI messages that only contain tool calls.
        if getattr(
            message,
            "tool_calls",
            None,
        ):
            continue

        content = extract_message_text(message)

        if content:

            logger.info(
                "Final AI response extracted successfully"
            )

            return content

    # --------------------------------------------------------
    # Secondary fallback
    # --------------------------------------------------------
    #
    # This handles unusual child-agent responses where the
    # response may not be represented exactly as AIMessage.
    # HumanMessage is explicitly excluded.
    # --------------------------------------------------------

    for message in reversed(messages):

        if isinstance(message, HumanMessage):
            continue

        if getattr(
            message,
            "tool_calls",
            None,
        ):
            continue

        content = extract_message_text(message)

        if content:

            logger.warning(
                "Final response extracted from non-AIMessage: %s",
                type(message).__name__,
            )

            return content

    logger.warning(
        "No valid final AI response found for route: %s",
        route,
    )

    return None


def get_safe_error_message(exception: Exception) -> str:
    """
    Convert internal exceptions into a safe frontend message.

    Detailed technical errors are logged but are not exposed
    directly to the user.
    """

    error_type = type(exception).__name__

    logger.error("Agent request failed [%s]", error_type)
    return safe_agent_error_message(exception)

# ============================================================
# Conversation State
# ============================================================

if "conversations" not in st.session_state:
    first_chat_id = str(uuid.uuid4())
    st.session_state.conversations = {
        first_chat_id: {
            "title": "New chat",
            "messages": [],
            "created_at": datetime.now().strftime("%d %b %Y"),
        }
    }
    st.session_state.active_chat_id = first_chat_id

if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = next(iter(st.session_state.conversations))

# Keep the active ID valid if a conversation was removed or state was reset.
if st.session_state.active_chat_id not in st.session_state.conversations:
    st.session_state.active_chat_id = next(iter(st.session_state.conversations))


def create_new_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.conversations[chat_id] = {
        "title": "New chat",
        "messages": [],
        "created_at": datetime.now().strftime("%d %b %Y"),
    }
    st.session_state.active_chat_id = chat_id


def active_messages():
    return st.session_state.conversations[
        st.session_state.active_chat_id
    ]["messages"]


# ============================================================
# Sidebar: conversation history only
# ============================================================

with st.sidebar:
    with st.expander("Process API data", expanded=False):
        st.caption(
            "Fetch JSON, apply AI processing instructions, and prepare a "
            "downloadable file. Temporary job files are removed before download."
        )
        with st.form("api_processing_form", clear_on_submit=False):
            api_url = st.text_input("API URL", key="api_processing_url")
            api_params_text = st.text_area(
                "Query parameters (JSON object)",
                value="{}",
                key="api_processing_params",
            )
            api_headers_text = st.text_area(
                "Request headers (JSON object)",
                value="{}",
                key="api_processing_headers",
            )
            auth_type = st.selectbox(
                "Authentication",
                ["None", "Bearer token", "Basic authentication"],
                key="api_processing_auth_type",
            )
            bearer_token = ""
            basic_username = ""
            basic_password = ""
            if auth_type == "Bearer token":
                bearer_token = st.text_input(
                    "Bearer token",
                    type="password",
                    key="api_processing_bearer",
                )
            elif auth_type == "Basic authentication":
                basic_username = st.text_input(
                    "Username",
                    key="api_processing_basic_username",
                )
                basic_password = st.text_input(
                    "Password",
                    type="password",
                    key="api_processing_basic_password",
                )
            api_instructions = st.text_area(
                "Filtering / cleaning instructions",
                key="api_processing_instructions",
            )
            api_format = st.selectbox(
                "Output format",
                list(SUPPORTED_OUTPUTS),
                key="api_processing_format",
            )
            api_filename = st.text_input(
                "Download filename",
                value="processed_data",
                key="api_processing_filename",
            )
            process_api = st.form_submit_button(
                "Fetch and process API data",
                use_container_width=True,
            )

        if process_api:
            st.session_state.pop("api_download", None)
            try:
                params = json.loads(api_params_text)
                headers = json.loads(api_headers_text)
                if not isinstance(params, dict) or not isinstance(headers, dict):
                    raise APIProcessingError(
                        "Query parameters and headers must be JSON objects."
                    )
                if auth_type == "Bearer token":
                    if not bearer_token.strip():
                        raise APIProcessingError("Enter a bearer token.")
                    headers["Authorization"] = f"Bearer {bearer_token.strip()}"
                    auth = None
                elif auth_type == "Basic authentication":
                    if not basic_username or not basic_password:
                        raise APIProcessingError(
                            "Enter both a username and password."
                        )
                    auth = (basic_username, basic_password)
                else:
                    auth = None

                with st.status("Preparing API request…", expanded=True) as status:
                    artifact = process_api_to_download(
                        api_url,
                        params=params,
                        headers=headers,
                        auth=auth,
                        output_format=api_format,
                        instructions=api_instructions,
                        filename=api_filename,
                        progress=lambda message: status.update(
                            label=message, state="running"
                        ),
                    )
                    status.update(label="Processed file is ready.", state="complete")
                st.session_state.api_download = {
                    "data": artifact.data,
                    "filename": artifact.filename,
                    "mime_type": artifact.mime_type,
                    "record_count": artifact.record_count,
                }
                st.success(
                    f"Processed {artifact.record_count} record(s). "
                    "Your download is ready."
                )
            except (json.JSONDecodeError, APIProcessingError) as exc:
                st.error(str(exc) if isinstance(exc, APIProcessingError) else
                         "Query parameters and headers must be valid JSON objects.")
            except Exception as exc:
                logger.error(
                    "API processing UI failed (error_type=%s)",
                    type(exc).__name__,
                )
                st.error(
                    "API processing failed. Check the endpoint, credentials, "
                    "and AI provider availability."
                )

        api_download = st.session_state.get("api_download")
        if api_download:
            st.download_button(
                "Download processed file",
                data=api_download["data"],
                file_name=api_download["filename"],
                mime=api_download["mime_type"],
                key="api_processed_download",
                use_container_width=True,
            )

    st.markdown("## AI Providers")
    try:
        provider_status = get_provider_status()
    except LLMConfigurationError:
        logger.error("Invalid LLM provider configuration in status panel")
        provider_status = []
        st.error(
            "Provider settings are invalid. Check LLM_PROVIDER_PRIORITY "
            "and free-model configuration."
        )
    priority = " → ".join(
        item["provider"]
        for item in provider_status
        if item["priority_enabled"]
    )
    if priority:
        st.caption(f"Request priority: {priority}")

    for provider in provider_status:
        configuration = "configured" if provider["configured"] else "API key missing"
        free_status = (
            "free-tier model configured"
            if provider["free_tier_configured"]
            else "free-tier use not confirmed"
        )
        priority_mark = "priority" if provider["priority_enabled"] else "not in priority"
        st.caption(
            f"**{provider['provider'].title()}** · {provider['model']} · "
            f"{configuration} · {free_status} · {priority_mark}"
        )
    st.caption(
        "Free-tier status reflects model configuration only; confirm account "
        "quotas and billing with the provider."
    )

    if st.button("Test All Providers", use_container_width=True):
        st.session_state.provider_health = [
            test_provider(provider["provider"])
            for provider in provider_status
        ]

    for result in st.session_state.get("provider_health", []):
        if result["healthy"]:
            st.caption(
                f"{result['provider'].title()}: healthy · "
                f"{result['latency_ms']} ms · {result['model']}"
            )
        else:
            st.caption(
                f"{result['provider'].title()}: unavailable · "
                f"{result['error']} · {result['model']}"
            )

    selected_provider = st.session_state.get("last_llm_metadata")
    if selected_provider:
        st.caption(
            "Last request: "
            f"{selected_provider['provider'].title()} / "
            f"{selected_provider['model']} "
            f"(tier {selected_provider['tier']})"
        )

    st.divider()
    st.markdown("## 💬 Chats")

    if st.button("＋  New chat", use_container_width=True, key="new_chat_button"):
        create_new_chat()
        st.rerun()

    st.divider()
    st.caption("HISTORY")

    chat_items = list(st.session_state.conversations.items())
    for chat_id, chat in reversed(chat_items):
        button_label = chat["title"] or "New chat"
        if st.button(
            f"💬  {button_label}",
            key=f"select_chat_{chat_id}",
            use_container_width=True,
            type="primary" if chat_id == st.session_state.active_chat_id else "secondary",
        ):
            st.session_state.active_chat_id = chat_id
            st.rerun()

# ============================================================
# Main chat area
# ============================================================

messages = active_messages()

if not messages:
    st.markdown(
        "<div style='text-align:center; padding-top:18vh;'>"
        "<h2>What can I help you with?</h2>"
        "<p style='color:gray;'>Ask a question about your data, documents, or workflows.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Message your data assistant...")


# ============================================================
# Process a new message
# ============================================================

if user_input and user_input.strip():
    user_input = user_input.strip()
    chat = st.session_state.conversations[st.session_state.active_chat_id]

    # Save the user message and create a useful title for the conversation.
    chat["messages"].append({"role": "user", "content": user_input})
    if chat["title"] == "New chat":
        chat["title"] = user_input[:35] + ("..." if len(user_input) > 35 else "")

    # Display the just-submitted message immediately.
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking..."):
                start_time = time.perf_counter()
                with capture_api_download() as api_download_result:
                    with capture_llm_metadata() as llm_metadata:
                        result = data_agent.invoke(
                            {
                                "messages": [HumanMessage(content=user_input)],
                                "route_response": "",
                            },
                            config={"recursion_limit": AGENT_RECURSION_LIMIT},
                        )
                if "artifact" in api_download_result:
                    artifact = api_download_result["artifact"]
                    st.session_state.api_download = {
                        "data": artifact.data,
                        "filename": artifact.filename,
                        "mime_type": artifact.mime_type,
                        "record_count": artifact.record_count,
                    }
                if llm_metadata:
                    st.session_state.last_llm_metadata = llm_metadata.copy()
                duration = time.perf_counter() - start_time

            if not isinstance(result, dict):
                raise RuntimeError("Data Agent returned an invalid response.")

            route = result.get("route_response", "")
            final_answer = extract_final_answer(result, route)

            if not final_answer:
                raise RuntimeError("The agent did not return a usable response.")

            st.markdown(final_answer)
            chat["messages"].append(
                {"role": "assistant", "content": final_answer}
            )
            logger.info(
                "Assistant response completed. route=%s duration=%.2fs",
                route or "unknown",
                duration,
            )

        except Exception as exc:
            error_message = get_safe_error_message(exc)
            st.error(error_message)
            chat["messages"].append(
                {"role": "assistant", "content": error_message}
            )

    # Rerun to render the complete updated conversation consistently.
    st.rerun()
