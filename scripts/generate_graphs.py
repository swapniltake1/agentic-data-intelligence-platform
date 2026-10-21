"""Generate PNG visualizations for the platform's compiled LangGraph agents."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.data_agent import data_agent_graph
from agents.etl_analyst import etl_analyst
from agents.rag_agent import rag_analyst
from agents.sql_analyst import sql_analyst
from utils.graph_visualization import save_graph_png


GRAPHS = (
    ("data_agent_graph.png", data_agent_graph),
    ("sql_analyst_graph.png", sql_analyst),
    ("etl_analyst_graph.png", etl_analyst),
    ("rag_agent_graph.png", rag_analyst),
)


def main() -> int:
    """Render all compiled graphs to the repository root."""
    failures = []

    for filename, graph in GRAPHS:
        output_path = PROJECT_ROOT / filename
        try:
            image = save_graph_png(graph, output_path)
            if not image:
                raise RuntimeError("renderer returned an empty PNG")
            print(f"Generated {output_path.name} ({len(image)} bytes)")
        except Exception as exc:
            failures.append(filename)
            print(f"Failed to generate {filename}: {exc}", file=sys.stderr)

    if failures:
        print(
            "Graph generation failed for: " + ", ".join(failures),
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
