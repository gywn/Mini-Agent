"""Session management for resumption with prefix caching.

This module provides functionality to save and load agent sessions,
enabling seamless continuation after restarts while preserving
message history for prefix caching.
"""

from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema.schema import Message, SessionHistory
from .tools import Tool


def get_session_history_dir(workspace_dir: Path) -> Path:
    """Get the session directory for a workspace."""
    return workspace_dir / ".mini-agent" / "session"


def get_new_session_history(workspace_dir: Path) -> Path:
    """Generate a new session file path with unique timestamp."""
    session_history_dir = get_session_history_dir(workspace_dir)
    session_history_dir.mkdir(parents=True, exist_ok=True)

    return session_history_dir / f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}_UTC.yaml"


def load_session_history(workspace_dir: Path) -> SessionHistory | None:
    """Load the latest session from the session directory."""
    if not (
        (session_history_dir := get_session_history_dir(workspace_dir)).exists()
        and (session_histories := list(session_history_dir.glob("session_*.yaml")))
    ):  # fmt: skip
        return None

    # Sort by filename (contains datetime suffix), largest first
    session_history = max(session_histories, key=lambda f: f.name)

    try:
        data = yaml.safe_load(session_history.read_text(encoding="utf-8"))
        if data is None:
            return None
        return SessionHistory.model_validate(data)
    except (ValidationError, yaml.YAMLError):
        return None


def save_session_history(session_history: Path, tools: list[Tool], messages: list[Message]) -> None:
    """Save the current session to the session file."""
    session_history.write_text(
        yaml.dump(
            SessionHistory(
                tool_schemas=[tool.to_schema() for tool in tools],
                messages=messages,
            ).model_dump(mode="python"),
            default_style="|",  # Dump to YAML with block style for multiline strings
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
