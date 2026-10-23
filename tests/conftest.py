from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _disable_test_file_logging() -> None:
    """Keep pytest and Streamlit AppTest runs from rotating the tracked app log."""


def pytest_configure() -> None:
    import logging_config

    logging_config.setup_logging = _disable_test_file_logging
