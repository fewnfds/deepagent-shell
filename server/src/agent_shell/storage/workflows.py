from __future__ import annotations

from copy import deepcopy

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.storage.file_config import FileConfigRepository
from agent_shell.workflow.contracts import (
    WorkflowGraphDefinitionV1,
    WorkflowGraphDocumentV1,
    WorkflowLayoutV1,
)


class WorkflowStore:
    def __init__(self, repository: FileConfigRepository, event_logger: SecurityEventLogger | None = None) -> None:
        self._repository = repository
        self._events = event_logger

    @staticmethod
    def _public(record: dict) -> dict:
        return {
            "id": str(record["id"]),
            "name": str(record["name"]),
            "description": str(record["description"]),
            "filesystem_id": str(record["filesystem_id"]),
            "workflow_prepare_id": record.get("workflow_prepare_id"),
            "enabled": bool(record["enabled"]),
        }

    def list_items(self, *, enabled_only: bool = False) -> list[dict]:
        records = [self._public(item) for item in self._repository.config().get("workflows", [])]
        if enabled_only:
            records = [item for item in records if item["enabled"]]
        return sorted(records, key=lambda value: (value["name"].casefold(), value["id"]))

    def get_item(self, item_id: str) -> dict | None:
        for item in self._repository.config().get("workflows", []):
            if item.get("id") == item_id:
                return self._public(item)
        return None

    def get_item_by_name(self, name: str) -> dict | None:
        for item in self._repository.config().get("workflows", []):
            if item.get("name") == name:
                return self._public(item)
        return None

    def get_item_by_filesystem(self, filesystem_id: str) -> dict | None:
        for item in self._repository.config().get("workflows", []):
            if item.get("filesystem_id") == filesystem_id:
                return self._public(item)
        return None

    def get_item_by_prepare(self, component_id: str) -> dict | None:
        for item in self._repository.config().get("workflows", []):
            if item.get("workflow_prepare_id") == component_id:
                return self._public(item)
        return None

    def save_item(self, item_id: str, data: dict) -> None:
        existing = self.get_item(item_id)
        empty_definition = WorkflowGraphDefinitionV1().model_dump(mode="json")
        empty_layout = WorkflowLayoutV1().model_dump(mode="json")

        def mutate(config: dict) -> None:
            records = config.setdefault("workflows", [])
            if any(item.get("name") == data["name"] and item.get("id") != item_id for item in records):
                raise ValueError("workflow name already exists")
            stored = deepcopy(data)
            stored["id"] = item_id
            stored.setdefault("definition", deepcopy(empty_definition))
            stored.setdefault("layout", deepcopy(empty_layout))
            for index, item in enumerate(records):
                if item.get("id") == item_id:
                    stored["definition"] = deepcopy(item.get("definition", empty_definition))
                    stored["layout"] = deepcopy(item.get("layout", empty_layout))
                    records[index] = stored
                    break
            else:
                records.append(stored)

        self._repository.update_config(mutate)
        emit_configuration_events(self._events, action="updated" if existing else "created", entity="workflow", entity_id=item_id)

    def get_graph(self, item_id: str) -> WorkflowGraphDocumentV1 | None:
        for item in self._repository.config().get("workflows", []):
            if item.get("id") == item_id:
                return WorkflowGraphDocumentV1.model_validate({"definition": item.get("definition", {}), "layout": item.get("layout", {})})
        return None

    def save_graph(self, item_id: str, document: WorkflowGraphDocumentV1) -> bool:
        changed = False

        def mutate(config: dict) -> None:
            nonlocal changed
            for item in config.setdefault("workflows", []):
                if item.get("id") == item_id:
                    item["definition"] = document.definition.model_dump(mode="json")
                    item["layout"] = document.layout.model_dump(mode="json")
                    changed = True
                    break

        self._repository.update_config(mutate)
        if changed:
            emit_configuration_events(self._events, action="updated", entity="workflow", entity_id=item_id)
        return changed

    def delete_items(self, item_ids: list[str]) -> int:
        unique_ids = set(item_ids)
        removed: list[str] = []

        def mutate(config: dict) -> None:
            records = config.setdefault("workflows", [])
            retained = []
            for item in records:
                if item.get("id") in unique_ids:
                    removed.append(str(item.get("id")))
                else:
                    retained.append(item)
            config["workflows"] = retained

        self._repository.update_config(mutate)
        for item_id in removed:
            emit_configuration_events(self._events, action="deleted", entity="workflow", entity_id=item_id)
        return len(removed)

    def delete_item(self, item_id: str) -> bool:
        return self.delete_items([item_id]) == 1
