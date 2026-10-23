import os
import sys
import logging
from functools import lru_cache
from pathlib import Path

# Allow imports when running the project from the root directory
sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
)

from logging_config import setup_logging

setup_logging()

from typing import Any

from langchain_core.messages import (
    HumanMessage,
    ToolMessage,
)
from langgraph.graph import (
    StateGraph,
    START,
    END,
)
from langchain.tools import tool

from utils.api_processing import (
    process_api_to_download,
    publish_api_download,
)
from utils.etl_tools import ETLTools
from utils.graph_visualization import save_graph_png
from utils.llm_pick import (
    extract_content,
    get_tool_llm,
    pick_llm,
)
from models.schema import ETLAgentSchema


# ============================================================
# Logger
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# ETL Tools
# ============================================================

@tool
def extract_load_tool(
    url: str,
    output_format: str,
    instructions: str = "",
) -> str:
    """
    Fetch JSON data from an API, apply the requested processing, and prepare
    a downloadable file. API responses and intermediate files are temporary.

    Args:
        url: API endpoint from which to extract data.
        output_format: Output format such as csv, json, or parquet.
        instructions: Optional filtering or cleaning instructions.

    Returns:
        Message indicating the processed file is ready for download.
    """

    logger.info("Extract and load operation started")

    try:
        artifact = process_api_to_download(
            url,
            output_format=output_format,
            instructions=instructions,
        )
        publish_api_download(artifact)

        logger.info("Extract and load operation completed")
        return (
            f"Processed {artifact.record_count} record(s) into "
            f"{artifact.filename}; the file is ready for download."
        )

    except Exception as e:
        logger.error(
            "Extract and load operation failed (error_type=%s)",
            type(e).__name__,
        )
        raise


# ============================================================
# Transform & Load Tool
# ============================================================

@tool
def transform_load_tool(
    input_file_path: str,
    output_folder: str,
    output_format: str,
    user_question: str,
) -> str:
    """
    Transform data from the specified file and save it
    to the desired location.
    """

    logger.info("Transform and load operation started")

    try:

        etl_tools = ETLTools()

        # ----------------------------------------------------
        # Resolve input file
        # ----------------------------------------------------

        resolved_input_file = (
            etl_tools.resolve_input_file(
                input_file_path
            )
        )

        logger.info(
            "Input file resolved successfully"
        )

        # ----------------------------------------------------
        # Get transformation context
        # ----------------------------------------------------

        top_3_rows = etl_tools.transform_load_context(
            str(resolved_input_file),
            output_folder,
            output_format,
        )

        logger.debug(
            "Transformation context generated"
        )

        # ----------------------------------------------------
        # Generate Pandas code
        # ----------------------------------------------------

        logger.info(
            "Generating Pandas transformation code"
        )

        llm = pick_llm("medium")

        prompt = f"""
        You are a Python Data Analyst who uses Pandas to analyze data.
        You need to provide only the Pandas Code that will help to perform
        the right ETL operations as per the user's question.

        Do not provide any explanation or comments, only the code should
        be provided.

        The code should be in a format that can be executed in a Python
        environment with Pandas installed.

        Don't write anything else than Pandas Code.

        Create the Pandas Dataframe from the data stored in the file:
        {resolved_input_file}

        Then write the code to transform and save the data at:
        {output_folder}

        Here's the user's question:
        {user_question}

        Here's the context of the data:
        {top_3_rows}
        """

        response = llm.invoke(prompt)

        pandas_code = extract_content(
            response
        ).strip()

        # ----------------------------------------------------
        # Clean generated code
        # ----------------------------------------------------

        if pandas_code.startswith("```python"):

            pandas_code = pandas_code[
                len("```python"):
            ].strip()

        elif pandas_code.startswith("```"):

            pandas_code = pandas_code[
                len("```"):
            ].strip()

        if pandas_code.endswith("```"):

            pandas_code = pandas_code[
                :-3
            ].strip()

        logger.info(
            "Pandas transformation code generated"
        )

        # ----------------------------------------------------
        # Execute transformation
        # ----------------------------------------------------

        logger.info(
            "Executing Pandas transformation"
        )

        results = etl_tools.execute_code(
            pandas_code
        )

        logger.info(
            "Pandas transformation completed"
        )

        return (
            f"the data is transformed and saved in "
            f"{output_folder} in {output_format} format\n\n"
            f"Pandas code executed:\n"
            f"{pandas_code}\n\n"
            f"execution results:\n"
            f"{results}"
        )

    except Exception as e:

        logger.error(
            "Transform and load operation failed: %s",
            e,
        )

        raise


# ============================================================
# Tools
# ============================================================

tools = [
    extract_load_tool,
    transform_load_tool,
]


@lru_cache(maxsize=1)
def _get_etl_llm_bind():
    """Create the tool-calling model only when the ETL node runs."""
    logger.info("Initializing ETL agent tools")
    llm = get_tool_llm("medium", tools)
    logger.info("ETL agent tools initialized successfully")
    return llm


# ============================================================
# LLM Node
# ============================================================

def llm_node(
    state: ETLAgentSchema,
):

    logger.info(
        "ETL LLM node started"
    )

    try:

        messages = state.messages

        prompt = f"""
        You are a Python Data Analyst who has access to tools
        that can process API data for download and transform local files.

        You will be provided with a user's question, and you
        would need to perform the right ETL operations as per
        the user's question.

        API extraction processes the response in a temporary workspace and
        prepares a downloadable processed file. Do not ask for an output folder
        for API requests. After API extraction, tell the user that a
        filename-specific download button appears below the chat and that they
        must select it to start the download. Do not claim the download started
        automatically or refer to a separate download link.

        If the operation is performed then inform the user
        and end the conversation.

        Here's the chat history:
        {messages}
        """

        logger.debug(
            "Invoking ETL LLM"
        )

        final_answer = _get_etl_llm_bind().invoke(
            prompt
        )

        state.messages = messages + [
            final_answer
        ]

        logger.info(
            "ETL LLM node completed"
        )

        return state

    except Exception as e:

        logger.error(
            "ETL LLM node failed: %s",
            e,
        )

        raise


# ============================================================
# Tool Node
# ============================================================

def tool_node(
    state: ETLAgentSchema,
):
    """
    Invoke the appropriate ETL tool according
    to the LLM tool calls.
    """

    logger.info(
        "ETL tool node started"
    )

    try:

        tools_result = []

        tools_by_name = {
            tool.name: tool
            for tool in tools
        }

        tool_calls = (
            state.messages[-1].tool_calls
        )

        logger.info(
            "Executing %d ETL tool call(s)",
            len(tool_calls),
        )

        for tool_call in tool_calls:

            tool_name = tool_call["name"]

            logger.info(
                "Executing ETL tool: %s",
                tool_name,
            )

            selected_tool = tools_by_name[
                tool_name
            ]

            observation = selected_tool.invoke(
                tool_call["args"]
            )

            tools_result.append(
                ToolMessage(
                    content=observation,
                    tool_call_id=tool_call["id"],
                )
            )

            logger.info(
                "ETL tool completed: %s",
                tool_name,
            )

        state.messages = (
            state.messages + tools_result
        )

        logger.info(
            "ETL tool node completed"
        )

        return state

    except Exception as e:

        logger.error(
            "ETL tool node failed: %s",
            e,
        )

        raise


# ============================================================
# Tool Routing
# ============================================================

def is_tool_call(
    state: ETLAgentSchema,
):

    tool_calls = (
        state.messages[-1].tool_calls
    )

    if tool_calls:

        logger.info(
            "Tool call detected. Routing to tool node"
        )

        return "tool_node"

    logger.info(
        "No tool call detected. Ending ETL workflow"
    )

    return "end"


# ============================================================
# Build ETL Agent Graph
# ============================================================

logger.info(
    "Building ETL agent graph"
)

etl_analyst_graph = StateGraph(
    ETLAgentSchema
)

etl_analyst_graph.add_node(
    "llm_node",
    llm_node,
)

etl_analyst_graph.add_node(
    "tool_node",
    tool_node,
)


# ============================================================
# Graph Edges
# ============================================================

etl_analyst_graph.add_edge(
    START,
    "llm_node",
)

etl_analyst_graph.add_conditional_edges(
    "llm_node",
    is_tool_call,
    {
        "tool_node": "tool_node",
        "end": END,
    },
)

etl_analyst_graph.add_edge(
    "tool_node",
    "llm_node",
)


# ============================================================
# Compile
# ============================================================

etl_analyst = etl_analyst_graph.compile()

logger.info(
    "ETL agent graph compiled successfully"
)


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":

    logger.info(
        "Starting ETL agent standalone test"
    )

    try:

        # ----------------------------------------------------
        # Generate graph visualization
        # ----------------------------------------------------

        save_graph_png(
            etl_analyst,
            Path(__file__).resolve().parents[1]
            / "etl_analyst_graph.png",
        )

        logger.info(
            "ETL agent graph visualization generated"
        )

        # ----------------------------------------------------
        # Execute ETL agent
        # ----------------------------------------------------

        response = etl_analyst.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            "I want to transform the data "
                            "stored in the 'data/extract' "
                            "folder and save the transformed "
                            "data in the 'data/transform' "
                            "folder. The transformation "
                            "should filter the data to show "
                            "bulbasaur pokemon only."
                        )
                    )
                ]
            }
        )

        logger.info(
            "ETL agent standalone test completed"
        )

        print(response)

    except Exception as e:

        logger.error(
            "ETL agent standalone test failed: %s",
            e,
        )

        raise