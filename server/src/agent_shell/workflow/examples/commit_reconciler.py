"""A deliberately small Commit + Commit Reconciler example.

The platform only supplies ArtifactCommitter events.  This example shows how
a user can collect validated commits in an order they choose; it is not used
by GraphRunService and is not a second scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OrderedCommitReconciler:
    required_paths: tuple[str, ...]
    accepted: dict[str, dict[str, Any]] = field(default_factory=dict)

    def accept(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        path = event.get("path")
        if event.get("status") not in {"committed", "committed_metadata"} or not isinstance(path, str):
            return []
        self.accepted[path] = dict(event)
        ready: list[dict[str, Any]] = []
        for expected in self.required_paths:
            item = self.accepted.get(expected)
            if item is None:
                break
            ready.append(item)
        return ready

    def complete(self) -> bool:
        return all(path in self.accepted for path in self.required_paths)
