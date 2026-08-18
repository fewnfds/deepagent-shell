from typing import Any


DISPATCH_KEY = "item"


def _task_id(item: dict[str, Any]) -> str:
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError("each shared_vars.items entry requires a non-empty string id")
    return f"item:{item_id.strip()}"


def create_dispatcher():
    async def dispatch(state, runtime):
        # Example only: tasks may be derived from any relevant Workflow State,
        # Runtime Context, or Store data. Replace this source for the Workflow.
        shared_vars = state.get("shared_vars", {})
        items = shared_vars.get("items") if isinstance(shared_vars, dict) else None
        if not isinstance(items, list) or not items:
            raise ValueError("shared_vars.items must be a non-empty list")
        if not all(isinstance(item, dict) for item in items):
            raise ValueError("each shared_vars.items entry must be an object")

        tasks = [
            {
                "task_id": _task_id(item),
                "dispatch_key": DISPATCH_KEY,
                "payload": {"item": item},
            }
            for item in items
        ]
        return {
            "tasks": tasks,
            # Parent-State updates are independent of each task payload.
            "update": {"shared_vars": {"dispatched_count": len(tasks)}},
        }

    return dispatch
