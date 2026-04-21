"""Pipeline state management for composable DW workflows.

Provides persistent JSON state across pipeline phases via
agents/{dw_id}/dw_state.json. Each phase reads and updates
the shared state, enabling composable pipelines.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field


class PhaseResult(BaseModel):
    """Result from a single pipeline phase."""

    status: Literal["pending", "running", "success", "failed"] = "pending"
    agent_name: str = ""
    output: str = ""
    session_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class DWState(BaseModel):
    """Persistent state for an DW pipeline run."""

    dw_id: str
    prompt: str = ""
    plan_file: Optional[str] = None
    model: Optional[str] = None
    working_dir: str = ""
    phases: Dict[str, PhaseResult] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _get_project_root() -> str:
    """Get the project root directory (two levels up from dw_modules/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_state_path(dw_id: str) -> str:
    """Get path to state file for an DW run."""
    return os.path.join(_get_project_root(), "agents", dw_id, "dw_state.json")


def create_state(
    dw_id: str,
    prompt: str = "",
    working_dir: str = "",
    model: Optional[str] = None,
) -> DWState:
    """Create and persist a new DW state."""
    state = DWState(
        dw_id=dw_id,
        prompt=prompt,
        working_dir=working_dir or os.getcwd(),
        model=model,
    )
    save_state(state)
    return state


def load_state(dw_id: str) -> Optional[DWState]:
    """Load state from disk. Returns None if not found."""
    path = get_state_path(dw_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return DWState(**data)
    except Exception:
        return None


def save_state(state: DWState) -> None:
    """Persist state to disk."""
    state.updated_at = datetime.now(timezone.utc).isoformat()
    path = get_state_path(state.dw_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state.model_dump(), f, indent=2)


def update_phase(
    state: DWState,
    phase_name: str,
    status: Literal["pending", "running", "success", "failed"],
    agent_name: str = "",
    output: str = "",
    session_id: Optional[str] = None,
) -> DWState:
    """Update a phase result and persist."""
    now = datetime.now(timezone.utc).isoformat()

    if phase_name not in state.phases:
        state.phases[phase_name] = PhaseResult(
            agent_name=agent_name,
            started_at=now,
        )

    phase = state.phases[phase_name]
    phase.status = status
    if agent_name:
        phase.agent_name = agent_name
    if output:
        phase.output = output
    if session_id:
        phase.session_id = session_id
    if status in ("success", "failed"):
        phase.completed_at = now

    save_state(state)
    return state
