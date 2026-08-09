from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from agent_shell.automation.runtime import AutomationRuntime


class AgentRequestContext(TypedDict):
    """Request-only Shell services shared with compiled Agent graphs."""

    automation_runtime: AutomationRuntime
    agent_shell_invocation: Mapping[str, Any]
