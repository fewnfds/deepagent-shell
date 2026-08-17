from __future__ import annotations

from typing import Any


def _required_task_id(kind: str, item: dict[str, Any]) -> str:
    value = item.get("id") or item.get("code")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{kind} item requires a non-empty id or code")
    return f"{kind}:{value.strip()}"


def _items(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"shared_vars.{name} must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"shared_vars.{name} items must be objects")
    return value


def create_dispatcher():
    # This factory is called once when the Workflow request is assembled.
    async def dispatch(state, runtime):
        # Customize this section to select work from Workflow State or the
        # official Runtime Context. This example expects an upstream node to
        # write cities and towns into shared_vars.
        shared_vars = state.get("shared_vars", {})
        if not isinstance(shared_vars, dict):
            raise ValueError("state.shared_vars must be an object")
        cities = _items(shared_vars.get("cities", []), "cities")
        towns = _items(shared_vars.get("towns", []), "towns")

        tasks = [
            {
                "task_id": _required_task_id("city", city),
                "dispatch_key": "city",
                "payload": {"kind": "city", "record": city},
            }
            for city in cities
        ]
        tasks.extend(
            {
                "task_id": _required_task_id("town", town),
                "dispatch_key": "town",
                "payload": {"kind": "town", "record": town},
            }
            for town in towns
        )
        if not tasks:
            raise ValueError("at least one city or town task is required")

        # Keys must match Dispatch Edge keys on the canvas. Agent Shell owns
        # target Node IDs and converts every validated task into LangGraph Send.
        return {
            "tasks": tasks,
            "update": {
                "shared_vars": {
                    "rainfall_dispatch_counts": {
                        "cities": len(cities),
                        "towns": len(towns),
                    }
                }
            },
        }

    return dispatch
