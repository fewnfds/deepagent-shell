from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from agent_shell.workflow.context import WorkflowContext
from agent_shell.workflow.state import read_path


class WorkflowNodeContext:
    """Request-local ABI passed to a contributed Python workflow node.

    The graph scheduler remains LangGraph.  A node only receives a state
    snapshot and returns an ordinary state update (or an official Command).
    """

    def __init__(
        self,
        *,
        node_id: str,
        node_type: str,
        config: Mapping[str, Any],
        inputs: Mapping[str, Any],
        state: Mapping[str, Any],
        runtime: WorkflowContext,
    ) -> None:
        self.node = {"id": node_id, "type": node_type}
        self.config = deepcopy(dict(config))
        self.inputs = deepcopy(dict(inputs))
        self.state = state
        self.shared = deepcopy(dict(state.get("shared") or {}))
        self.runtime = runtime

    def read(self, path: str, default: Any = None) -> Any:
        return read_path(self.shared, path, default)

    def emit(self, event: Mapping[str, Any]) -> None:
        if self.runtime.emit is not None:
            self.runtime.emit({"event": "plugin_node", "node_id": self.node["id"], **dict(event)})


__all__ = ["WorkflowNodeContext"]
