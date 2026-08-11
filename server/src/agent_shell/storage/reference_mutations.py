from __future__ import annotations


def detach_agent_block_references(
    config: dict,
    block_type: str,
    block_ids: set[str],
) -> None:
    for key in ("main_agents", "subagents"):
        records = config.get(key, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            if key == "main_agents":
                references = record.get("capability_refs")
                if isinstance(references, list):
                    record["capability_refs"] = [
                        item
                        for item in references
                        if not (
                            isinstance(item, dict)
                            and item.get("type") == block_type
                            and item.get("block_id") in block_ids
                        )
                    ]
                continue

            settings = record.get("settings")
            overrides = (
                settings.get("capability_overrides")
                if isinstance(settings, dict)
                else None
            )
            if isinstance(overrides, list) and isinstance(settings, dict):
                settings["capability_overrides"] = [
                    item
                    for item in overrides
                    if not (
                        isinstance(item, dict)
                        and item.get("type") == block_type
                        and item.get("block_id") in block_ids
                    )
                ]


def detach_subagent_references(config: dict, target_ids: set[str]) -> None:
    for record in config.get("main_agents", []):
        references = record.get("subagents") if isinstance(record, dict) else None
        if isinstance(references, list):
            record["subagents"] = [
                item
                for item in references
                if not (
                    isinstance(item, dict)
                    and item.get("subagent_id") in target_ids
                )
            ]


__all__ = ["detach_agent_block_references", "detach_subagent_references"]
