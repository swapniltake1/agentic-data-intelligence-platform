import logging
import time
import uuid
from datetime import datetime

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from logging_config import setup_logging
from agents.data_agent import data_agent

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

    logger.error(
        "Agent request failed [%s]: %s",
        error_type,
        exception,
    )

    return (
        "I couldn't complete your request right now. "
        "Please try again."
    )

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
                result = data_agent.invoke(
                    {
                        "messages": [HumanMessage(content=user_input)],
                        "route_response": "",
                    },
                    config={"recursion_limit": AGENT_RECURSION_LIMIT},
                )
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
