# Agentic Data Intelligence Platform

A Python-based, agent-driven data intelligence platform for turning natural-language questions into actionable results across SQL analytics, ETL, and document-grounded RAG workflows. The system combines LLM-based reasoning, LangGraph orchestration, deterministic SQL safety validation, PostgreSQL schema introspection, API/file-based ETL tools, a persistent Chroma knowledge base, centralized logging, and a Streamlit chat interface.

## Overview

This project is designed to help users interact with transportation and payments data using natural language instead of writing SQL or manually coordinating ETL steps.

The platform currently provides three specialist workflows:

- **SQL Analyst** — interprets a business question, uses PostgreSQL schema metadata and sample data to generate SQL, validates that the query is safe and read-only, executes the approved query, and produces a final answer.
- **ETL Analyst** — selects extraction and transformation tools for API/file workflows and returns the result to the agent.
- **RAG Analyst** — retrieves relevant chunks from the persistent document knowledge base and uses the retrieved context to produce a grounded answer.
- **Data Agent / Parent Router** — classifies an incoming request as `sql`, `etl`, or `rag` and routes it to the appropriate specialist workflow.
- **Streamlit UI** — provides a ChatGPT-style interface for interacting with the Data Agent, including chat history, suggested questions, analyst/model metadata, model health checks, and user-friendly error handling.
- **Centralized logging** — application activity is written to both the console and a rotating `logs/app.log` file.

## Key Features

- Natural-language-to-SQL workflow
- Parent agent that routes requests to SQL, ETL, or RAG specialists
- Deterministic read-only SQL safety validation before execution
- Structured LLM judge for an additional SQL safety review
- PostgreSQL schema introspection and sample-data context
- CSV-driven PostgreSQL database population
- API extraction and Pandas transformation tools for ETL workflows
- Markdown, TXT, and PDF ingestion with persistent Chroma retrieval for RAG
- Free-first Groq → OpenRouter → Gemini chat-provider priority
- LOW, MEDIUM, and HIGH model tiers with per-provider model overrides
- Bounded transient-error fallback across configured providers
- Retry handling for temporary service/server failures
- Streamlit chat interface with conversation history
- Suggested business questions from the welcome screen
- Explicit live provider health checks and selected-provider diagnostics
- Response metadata showing analyst, model tier, and execution time
- Safe frontend error messages while detailed errors are retained in logs
- Centralized rotating file logging for application diagnostics
- Structured Pydantic agent state models

The platform currently supports three specialist paths:

- **SQL Analyst** — uses PostgreSQL schema and sample-data context to generate a query, apply deterministic read-only safety checks and an LLM safety review, execute an approved query, and interpret the results.
- **ETL Analyst** — selects extraction and transformation tools for API- and file-based workflows.
- **RAG Analyst** — retrieves relevant chunks from a local Chroma vector store and uses the retrieved context to generate an answer grounded in the configured knowledge base.

```mermaid
flowchart LR
    U["User"] --> UI["Streamlit Chat UI"]
    UI --> P["Parent Data Agent"]
    P --> R{"Request Router"}
    R -->|SQL| S["SQL Analyst"]
    R -->|ETL| E["ETL Analyst"]
    R -->|RAG| G["RAG Analyst"]
    S --> DB["PostgreSQL"]
    S --> Q["SQL Safety Validation"]
    Q --> J["LLM Safety Judge"]
    J --> DB
    E --> API["External APIs"]
    E --> FILE["Files / Pandas"]
    G --> CHROMA["Persistent Chroma Store"]
    P --> LLM["Free-First LLM Provider Factory"]
    S --> LLM
    E --> LLM
    G --> LLM
    P --> LOG["Centralized Logging"]
    S --> LOG
    E --> LOG
    UI --> LOG
```

### LangGraph Orchestration

The parent diagram represents the compiled graph in `agents/data_agent.py`: its conditional edges select one specialist node and then end the run. The RAG workflow is a separate compiled graph with one node; query-time retrieval and response generation happen inside that node.

```mermaid
flowchart TD
    P_START(["START"]) --> router_node["router_node"]
    router_node -->|sql| sql_agent["sql_agent"]
    router_node -->|etl| etl_agent["etl_agent"]
    router_node -->|rag| rag_agent["rag_agent"]
    sql_agent --> P_END(["END"])
    etl_agent --> P_END
    rag_agent --> P_END
```

```mermaid
flowchart TD
    R_START(["START"]) --> rag_llm_node["rag_llm_node"]
    rag_llm_node --> R_END(["END"])
```

### End-to-end platform architecture

```mermaid
flowchart TB
    USER([User]) --> UI[Streamlit Chat UI]
    UI --> PARENT[Parent Data Agent - LangGraph]
    PARENT --> ROUTER{Structured Request Router}

    ROUTER -->|SQL question| SQL[SQL Analyst]
    ROUTER -->|ETL task| ETL[ETL Analyst]
    ROUTER -->|Document knowledge question| RAG[RAG Analyst]

    SQL --> GUARD[Deterministic SQL Safety Checks]
    GUARD --> JUDGE[LLM Safety Review]
    JUDGE -->|Approved| PG[(PostgreSQL)]
    PG --> SQLANSWER[Query Result Interpretation]

    ETL --> TOOLS[API / File / Pandas Tools]
    TOOLS --> ETLANSWER[ETL Result]

    RAG --> RETRIEVE[Similarity Retriever]
    RETRIEVE --> CHROMA[(Persistent Chroma Vector Store)]
    CHROMA --> CONTEXT[Retrieved Document Chunks]
    CONTEXT --> LLM[Configured Chat Provider]

    SQLANSWER --> RESPONSE[Final Response]
    ETLANSWER --> RESPONSE
    GEMINI --> RESPONSE
    RESPONSE --> UI

    PARENT -.-> LOGS[Centralized Logging]
    SQL -.-> LOGS
    ETL -.-> LOGS
    RAG -.-> LOGS
```

### Request-routing workflow

```mermaid
flowchart TD
    A[Incoming Natural-Language Message] --> B[Parent Agent]
    B --> C[Structured Classification]
    C --> D{Route}
    D -->|sql| E[SQL Analyst Graph]
    D -->|etl| F[ETL Analyst Graph]
    D -->|rag| G[RAG Analyst Graph]
    E --> H[Specialist Answer]
    F --> H
    G --> H
    H --> I[Parent Response State]
    I --> J[Streamlit Chat UI]
```

### RAG Data Flow

Ingestion and query-time retrieval are implemented in Python functions called by the RAG workflow; they are not separate LangGraph nodes.

```mermaid
flowchart LR
    subgraph Ingestion["Document ingestion (rag/ingest.py)"]
        DOCS["Markdown / TXT / PDF documents"]
        LOAD["Document loaders"]
        SPLIT["Recursive text splitting<br/>chunk size: 1,000 characters<br/>overlap: 150 characters"]
        EMBED["Gemini embeddings"]
        CHROMA["Persistent Chroma vector store"]
        DOCS --> LOAD --> SPLIT --> EMBED --> CHROMA
    end

    subgraph Query["Query time (inside rag_llm_node)"]
        QUESTION["User question"]
        SEARCH["Similarity search<br/>default top-k: 4"]
        CONTEXT["Retrieved context"]
        RESPONSE["Configured chat-provider response generation"]
        ANSWER["Final answer"]
        QUESTION --> SEARCH --> CONTEXT --> RESPONSE --> ANSWER
    end

    CHROMA --> SEARCH
```

### Observability Flow

```mermaid
flowchart LR
    UI["Streamlit UI"] --> APP["Application"]
    APP --> AGENTS["Agent Workflows"]
    AGENTS --> MODEL["Groq / OpenRouter / Gemini chat models"]
    AGENTS --> DB["PostgreSQL"]
    AGENTS --> ETL["ETL Tools"]
    AGENTS --> RAG["RAG Retrieval"]
    RAG --> CHROMA["Persistent Chroma Store"]
    APP --> LOG["Rotating logs/app.log"]
    AGENTS --> LOG
    MODEL --> LOG
    DB --> LOG
    ETL --> LOG
    LOG --> OPS["Diagnostics / Troubleshooting"]
```

### Architecture Notes

- **Streamlit** is the user-facing interaction layer.
- **Data Agent** provides top-level routing and orchestration.
- **SQL Analyst** handles schema-aware analytical requests.
- **ETL Analyst** handles extraction and transformation requests.
- **RAG Analyst** retrieves indexed document chunks and generates grounded responses.
- **LangGraph** manages the stateful specialist workflows.
- **Groq and OpenRouter** are preferred for chat generation, with **Gemini** as a supported fallback. Gemini remains the RAG embedding provider.
- **PostgreSQL** provides structured source data and schema metadata.
- **Chroma** persists document embeddings and supports similarity retrieval. Ingestion uses 1,000-character chunks with 150-character overlap; query-time retrieval defaults to the top 4 chunks.
- **Gemini embeddings** are separate from chat generation and remain unchanged for both Chroma indexing and retrieval.
- **RAG ingestion and retrieval** are operations inside the ingestion workflow and `rag_llm_node`, not separate nodes in the RAG LangGraph.
- **Deterministic SQL validation** is the first safety boundary before database execution.
- **LLM safety judging** provides a second review layer for generated SQL.
- **Centralized logging** captures operational events without exposing API credentials.

### Graph Visualizations

The repository includes PNGs rendered from the compiled LangGraph definitions:

- [Parent Data Agent graph](data_agent_graph.png)
- [SQL Analyst graph](sql_analyst_graph.png)
- [ETL Analyst graph](etl_analyst_graph.png)
- [RAG Analyst graph](rag_agent_graph.png)

Regenerate all four images from the repository root with:

```bash
uv run python scripts/generate_graphs.py
```

The renderer uses LangChain's installed Mermaid PNG API; no additional Python package is required. Rendering requires network access to the Mermaid rendering service. Graph generation imports and compiles the agents but does not invoke LLMs, connect to PostgreSQL, run ETL tools, or ingest documents.

## Streamlit User Interface

The Streamlit application in [app.py](app.py) provides:

- ChatGPT-style conversation flow
- New Chat and session-based history
- Suggested business questions
- Access to SQL, ETL, and RAG workflows through the Data Agent
- Groq, OpenRouter, and Gemini model status
- Explicit Test All Providers functionality
- Analyst/model/execution-time response metadata
- Direct API-to-processed-file workflow with CSV, JSON, or Parquet downloads
- User-friendly error handling
- Custom responsive application styling

Run the UI with:

```bash
uv run streamlit run app.py
```

### Fetch API data, transform it, and download the result

Use the main chat input to describe the API task in natural language. For example:

```text
Fetch data from https://jsonplaceholder.typicode.com/posts.
Keep only records where userId = 1, return id, title, and body,
remove duplicate IDs, and prepare a CSV file named processed_posts.csv.
```

The parent agent should route the request to the ETL workflow, which fetches JSON data, applies your filtering/cleaning instructions with the configured chat model, and prepares a download. When processing succeeds, a **Download** button appears in the chat interface. Supported output formats are CSV, JSON, and Parquet; Excel is not currently supported.

The API processor accepts HTTP(S) URLs and supports optional query parameters, request headers, and bearer/basic authentication through its programmatic interface. Requests use bounded timeouts. Responses are limited to 2 MiB and 2,000 records, and the generated output is capped at 10 MiB. The AI transforms records in batches of up to 50.

Raw API data and intermediate files are written only inside a unique temporary directory for each job. After the final output is serialized into memory, that temporary directory is removed before Streamlit presents the download button. Streamlit serves the prepared bytes from session state; it cannot confirm whether the browser saved the file locally. A later successful API-processing request replaces the previously prepared download. Temporary files are cleaned up on processing errors as well.

API credentials and request headers are not logged. Avoid sending confidential or regulated data to an AI provider unless your provider and account are approved for that data. Note that the legacy `ETLTools.extract_load` helper, when called directly, saves the processed output to a project-local destination; the chat-based API download workflow uses temporary storage.


### Existing graph visualizations

The repository includes generated visualizations for the existing parent and specialist graphs:

| Graph | Preview |
|---|---|
| Parent Data Agent | [`data_agent_graph.png`](data_agent_graph.png) |
| SQL Analyst | [`sql_analyst_graph.png`](sql_analyst_graph.png) |
| ETL Analyst | [`etl_analyst_graph.png`](etl_analyst_graph.png) |

The Mermaid diagrams above document the high-level platform and RAG flow. The RAG workflow is implemented in code; a generated RAG graph image is not currently listed among the repository's graph PNGs.

## Technology Stack

- **Language:** Python 3.12+
- **Agent orchestration:** LangGraph
- **Chat LLMs:** Groq, OpenRouter (OpenAI-compatible API), and Google Gemini through LangChain integrations
- **Embeddings:** Google Gemini through LangChain integrations
- **Agent framework:** LangChain
- **Structured database:** PostgreSQL, `psycopg2`
- **Vector database:** Chroma with persistent local storage
- **Document ingestion:** LangChain Community loaders, PyPDF, text splitters
- **ETL and data processing:** Requests, Pandas
- **UI:** Streamlit
- **State and validation:** Pydantic / typed graph state
- **Configuration:** python-dotenv
- **Logging:** Python logging with rotating file output

## Repository Layout

```text
.
├── agents/
│   ├── __init__.py
│   ├── data_agent.py
│   ├── etl_analyst.py
│   ├── rag_agent.py
│   ├── scratch.py
│   └── sql_analyst.py
├── rag/
│   ├── __init__.py
│   ├── ingest.py
│   ├── retriever.py
│   └── vector_store.py
├── scripts/
│   └── generate_graphs.py
├── data/
│   └── load/                 # Seed CSV files for PostgreSQL
├── knowledge_base/
│   ├── documents/            # Add .md, .txt, and .pdf source documents here
│   └── chroma_db/            # Persistent local Chroma index
├── models/
│   └── schema.py             # Pydantic and routing schemas
├── rag/
│   ├── ingest.py             # Load, split, and index documents
│   ├── retriever.py          # Similarity retrieval helpers
│   └── vector_store.py       # Gemini embedding and Chroma configuration
├── utils/
│   ├── api_processing.py    # Temporary API processing and download artifacts
│   ├── database.py
│   ├── etl_tools.py
│   ├── feed_db.py
│   ├── graph_visualization.py
│   ├── llm_pick.py          # Multi-provider LLM selection and fallback
│   └── ui_errors.py
├── tests/
│   ├── conftest.py
│   ├── test_api_processing.py
│   ├── test_application_regressions.py
│   └── test_llm_pick.py
├── logs/                    # Runtime logs (generated locally)
├── app.py
├── logging_config.py
├── main.py
├── pyproject.toml
├── README.md
├── schema_info.txt
├── data_agent_graph.png
├── etl_analyst_graph.png
├── rag_agent_graph.png
├── sql_analyst_graph.png
└── uv.lock
```

## Getting Started

### Prerequisites

- Python 3.12 or later
- PostgreSQL instance and credentials for SQL/ETL features that use the database
- API keys for one or more chat providers (Groq, OpenRouter, or Gemini)
- `GOOGLE_API_KEY` for Gemini embeddings used by RAG
- Git

### 1. Clone the repository

```bash
git clone https://github.com/swapniltake1/agentic-data-intelligence-platform.git
cd agentic-data-intelligence-platform
```

### 2. Create and configure environment variables

Copy `.env.example` to `.env` in the project root and add credentials locally. Keep real credentials out of source control.

```env
# Preferred free-first chat providers
GROQ_API_KEY=your_groq_api_key
OPENROUTER_KEY=your_openrouter_api_key
LLM_PROVIDER_PRIORITY=groq,openrouter,gemini
LLM_FREE_ONLY=true

# PostgreSQL — required for database-backed workflows
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database_name
DB_USER=your_postgres_user
DB_PASSWORD=your_postgres_password

# Gemini chat fallback
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_API_KEY=your_google_api_key

# RAG embeddings are independent from the chat provider
GOOGLE_EMBEDDING_MODEL=gemini-embedding-001
RAG_COLLECTION_NAME=ola_knowledge
```

`OPENROUTER_KEY` is preferred; `OPENROUTER_API_KEY` is accepted as an alias. `GROQ_KEY` remains accepted as a Groq alias. The embedding factory continues to read `GOOGLE_API_KEY` and is not affected by chat-provider selection. Never commit a real key.

### 3. Install dependencies

Using `uv` (recommended when available):

```bash
uv sync
```

Install development dependencies, including pytest and coverage, with:

```bash
uv sync --group dev
```

Or install the project dependencies with pip:

```bash
python -m pip install -e .
```

### 4. Prepare the PostgreSQL data (SQL workflows)

Review the database configuration and CSV inputs, then run:

```bash
uv run python utils/feed_db.py
```

Use your configured environment and database permissions. Skip this step if you only intend to experiment with the document RAG path.

### 5. Add and index knowledge-base documents (RAG)

Place your source files under `knowledge_base/documents/`. Supported extensions are:

- `.md` — Markdown
- `.txt` — UTF-8 text
- `.pdf` — PDF documents

Build or rebuild the local vector index:

```bash
uv run python -m rag.ingest
```

The ingestion script loads the supported files, splits content into chunks (1,000 characters with 150 characters of overlap), creates deterministic chunk IDs, and indexes the chunks in the persistent Chroma collection at `knowledge_base/chroma_db/`.

**Note:** Re-running ingestion rebuilds the configured collection by deleting its existing entries before indexing the current document set. Back up the directory or use a separate collection if you need to preserve an existing index.

### 6. Launch the application

```bash
uv run streamlit run app.py
```

Then open the local URL printed by Streamlit. You can ask for SQL-backed analysis, ETL operations, or questions about the indexed documents.

## How to Use the RAG Feature

1. Add relevant business or domain documents to `knowledge_base/documents/`.
2. Set `GOOGLE_API_KEY` for Gemini embeddings and configure at least one chat provider.
3. Run the ingestion command to build the Chroma index.
4. Launch the Streamlit application.
5. Ask a natural-language question about the indexed material. The parent agent should route document-knowledge questions to the RAG specialist.

The RAG agent uses similarity retrieval with a default `top_k` of 4. Retrieved text is passed as evidence to the response model; the prompt instructs the model to avoid unsupported claims and to state when the available context is insufficient. This does not replace testing retrieval quality or verifying important answers.

## Configuration Notes

- Chat provider priority defaults to Groq, OpenRouter, then Gemini. Override it with `LLM_PROVIDER_PRIORITY`.
- Chat model tiers are configured centrally in `utils/llm_pick.py`. Override models with `GROQ_MODEL_LOW/MEDIUM/HIGH`, `OPENROUTER_MODEL_LOW/MEDIUM/HIGH`, or `GEMINI_MODEL_LOW/MEDIUM/HIGH`.
- Groq defaults to `openai/gpt-oss-20b` for LOW and `openai/gpt-oss-120b` for MEDIUM/HIGH. These are Groq's documented replacements for the deprecated Llama 3.1/3.3 models ([supported models](https://console.groq.com/docs/models), [deprecations](https://console.groq.com/docs/deprecations)); Groq documents tool use for hosted models ([tool use](https://console.groq.com/docs/tool-use)). Override models as the supported-model list changes. OpenRouter defaults to its [`openrouter/free` router](https://openrouter.ai/openrouter/free), which advertises structured output and tool calling.
- `LLM_FREE_ONLY=true` is the default. Paid OpenRouter model IDs are refused; use `openrouter/free` or a verified model ID ending in `:free`.
- Gemini is not used as an automatic free-only fallback unless `GEMINI_FREE_TIER_CONFIRMED=true` is set after checking that the configured model and account have free-tier access. Set `LLM_FREE_ONLY=false` only if paid usage is acceptable.
- Requests retry transient failures a bounded number of times and then try the next configured provider at the same tier. Authentication and invalid-request failures are not treated as quota fallback.
- The sidebar shows each provider's configured model, priority, and explicit health-check results. Health requests run only after selecting **Test All Providers**.
- Provider model availability, free-tier access, quotas, and rate limits are controlled by the providers and can change. A configured free-model route does not guarantee a particular model, quota, availability, or zero cost under every provider account.
- Chat generation and RAG embeddings use separate integrations: the chat provider may be Groq/OpenRouter/Gemini, while Chroma indexing and retrieval continue to use Gemini embeddings.
- The RAG embedding model defaults to `gemini-embedding-001`; override with `GOOGLE_EMBEDDING_MODEL` if needed.
- The Chroma collection defaults to `ola_knowledge`; override with `RAG_COLLECTION_NAME`.
- The Chroma index is stored locally under `knowledge_base/chroma_db/`.

## Logging and Observability

Logging is configured through `logging_config.py` and is used across the application's agent workflows. The existing configuration supports console output and a rotating `logs/app.log` file, helping with troubleshooting without displaying detailed internal exceptions directly in the chat UI.

Do not log secrets, API keys, passwords, or confidential document content.

## Automated tests

Tests mock provider, API, database, and vector-store boundaries; they do not require real credentials, live API requests, or a database. Install development dependencies with `uv sync --group dev`, then run from the repository root:

```bash
python -m pytest -v
python -m pytest --cov=. --cov-report=term-missing -v
```

If the project virtual environment is not active, run the same commands through `uv run`:

```bash
uv run python -m pytest -v
uv run python -m pytest --cov=. --cov-report=term-missing -v
```

### Provider troubleshooting

- **429 / quota exhausted:** the request falls through the configured provider order after bounded retries. Check the provider's usage dashboard and limits.
- **401 / 403:** verify the key for that provider; authentication failures are surfaced rather than silently masked by another key.
- **Model unavailable / 404:** update the relevant per-tier model override to a currently supported model. Groq's supported model list is provider-controlled.
- **OpenRouter free-only rejection:** check that the configured model is `openrouter/free` or an explicitly free model ID ending in `:free`.
- **No provider configured:** set at least one of `GROQ_API_KEY`, `OPENROUTER_KEY`, or `GEMINI_API_KEY` / `GOOGLE_API_KEY`.
- **RAG embedding or index errors:** configure `GOOGLE_API_KEY` and keep `GOOGLE_EMBEDDING_MODEL` consistent with the existing Chroma index. Changing embedding models requires re-indexing; this change does not change that integration.

## Security and Operational Considerations

- **SQL access:** generated SQL passes deterministic checks intended to allow only a single read-only `SELECT` or `WITH` query, followed by an LLM safety review before execution. Use a least-privilege PostgreSQL account as an additional control.
- **ETL execution:** the ETL transformation utility uses Python `exec()`. Do not run untrusted or model-generated code in a production process without a restrictive sandbox and explicit controls.
- **Credentials:** keep `.env` out of version control and rotate any credentials accidentally exposed.
- **RAG quality:** retrieved content can be incomplete, outdated, or irrelevant. Keep knowledge documents curated and re-index after updates.
- **Local vector data:** treat the Chroma directory as application data; protect it according to the sensitivity of the indexed documents.
- **Production readiness:** authentication, authorization, isolation, automated evaluation, and comprehensive tests should be added before exposing the platform to untrusted users.

## Project Status

### Implemented

- [x] Parent LangGraph router for SQL, ETL, and RAG requests
- [x] SQL Analyst workflow with deterministic checks and LLM safety review
- [x] ETL Analyst workflow with API/file transformation tools
- [x] Temporary API-to-download workflow with CSV, JSON, and Parquet outputs
- [x] Temporary-workspace cleanup on success and processing failures
- [x] RAG ingestion for Markdown, text, and PDF sources
- [x] Text chunking and persistent Chroma indexing
- [x] Similarity retrieval and context-grounded responses using the configured chat provider
- [x] Free-first multi-provider chat selection and explicit provider health checks
- [x] Streamlit conversational interface and downloadable processed artifacts
- [x] Automated pytest suite for API processing, LLM selection, and application regressions
- [x] Centralized LLM configuration and application logging

### Potential next steps

- Expand automated coverage for additional routing, ingestion, retrieval, and SQL-validation edge cases
- Add evaluation datasets for retrieval relevance and answer faithfulness
- Add source/page citations to RAG responses where appropriate
- Add a sandbox for ETL code execution
- Introduce authentication, authorization, and deployment configuration
- Add monitoring, traces, and stakeholder-facing reporting

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0-only)**. See the [`LICENSE`](LICENSE) file for the complete license text.

**Copyright © 2026 Swapnil Take.**

