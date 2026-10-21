"""Shared helpers for rendering compiled LangGraph graphs as PNG files."""

from pathlib import Path
from typing import Any


def save_graph_png(compiled_graph: Any, output_path: Path) -> bytes:
    """Render a compiled graph, save its PNG, and return the image bytes."""
    image = compiled_graph.get_graph().draw_mermaid_png()
    output_path.write_bytes(image)
    return image
