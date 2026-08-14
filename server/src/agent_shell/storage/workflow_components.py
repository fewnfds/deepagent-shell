from __future__ import annotations

from copy import deepcopy

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.storage.file_config import FileConfigRepository


class WorkflowComponentStore:
    def __init__(
        self,
        repository: FileConfigRepository,
        event_logger: SecurityEventLogger | None = None,
    ) -> None:
        self._repository = repository
        self._events = event_logger

    @staticmethod
    def _public(record: dict) -> dict:
        return deepcopy(record)

    def list_definitions(self) -> list[dict]:
        records = self._repository.config().get(
            "workflow_component_definitions", []
        )
        return sorted(
            (self._public(item) for item in records),
            key=lambda item: (str(item["name"]).casefold(), str(item["id"])),
        )

    def get_definition(self, definition_id: str) -> dict | None:
        for item in self._repository.config().get(
            "workflow_component_definitions", []
        ):
            if item.get("id") == definition_id:
                return self._public(item)
        return None

    def save_definition(self, definition_id: str, data: dict) -> None:
        existing = self.get_definition(definition_id)

        def mutate(config: dict) -> None:
            records = config.setdefault("workflow_component_definitions", [])
            if any(
                item.get("name") == data["name"]
                and item.get("id") != definition_id
                for item in records
            ):
                raise ValueError("workflow component definition name already exists")
            stored = {**deepcopy(data), "id": definition_id}
            for index, item in enumerate(records):
                if item.get("id") == definition_id:
                    records[index] = stored
                    break
            else:
                records.append(stored)

        self._repository.update_config(mutate)
        emit_configuration_events(
            self._events,
            action="updated" if existing else "created",
            entity="workflow_component_definition",
            entity_id=definition_id,
        )

    def delete_definition(self, definition_id: str) -> bool:
        removed = False

        def mutate(config: dict) -> None:
            nonlocal removed
            records = config.setdefault("workflow_component_definitions", [])
            retained = [item for item in records if item.get("id") != definition_id]
            removed = len(retained) != len(records)
            config["workflow_component_definitions"] = retained

        self._repository.update_config(mutate)
        if removed:
            emit_configuration_events(
                self._events,
                action="deleted",
                entity="workflow_component_definition",
                entity_id=definition_id,
            )
        return removed

    def list_instances(self, *, definition_id: str | None = None) -> list[dict]:
        records = self._repository.config().get("workflow_component_instances", [])
        if definition_id is not None:
            records = [
                item for item in records if item.get("definition_id") == definition_id
            ]
        return sorted(
            (self._public(item) for item in records),
            key=lambda item: (str(item["name"]).casefold(), str(item["id"])),
        )

    def get_instance(self, instance_id: str) -> dict | None:
        for item in self._repository.config().get(
            "workflow_component_instances", []
        ):
            if item.get("id") == instance_id:
                return self._public(item)
        return None

    def get_instance_by_definition(self, definition_id: str) -> dict | None:
        return next(iter(self.list_instances(definition_id=definition_id)), None)

    def save_instance(self, instance_id: str, data: dict) -> None:
        existing = self.get_instance(instance_id)

        def mutate(config: dict) -> None:
            records = config.setdefault("workflow_component_instances", [])
            if any(
                item.get("definition_id") == data["definition_id"]
                and item.get("name") == data["name"]
                and item.get("id") != instance_id
                for item in records
            ):
                raise ValueError("workflow component instance name already exists")
            stored = {**deepcopy(data), "id": instance_id}
            for index, item in enumerate(records):
                if item.get("id") == instance_id:
                    records[index] = stored
                    break
            else:
                records.append(stored)

        self._repository.update_config(mutate)
        emit_configuration_events(
            self._events,
            action="updated" if existing else "created",
            entity="workflow_component_instance",
            entity_id=instance_id,
        )

    def delete_instance(self, instance_id: str) -> bool:
        removed = False

        def mutate(config: dict) -> None:
            nonlocal removed
            records = config.setdefault("workflow_component_instances", [])
            retained = [item for item in records if item.get("id") != instance_id]
            removed = len(retained) != len(records)
            config["workflow_component_instances"] = retained

        self._repository.update_config(mutate)
        if removed:
            emit_configuration_events(
                self._events,
                action="deleted",
                entity="workflow_component_instance",
                entity_id=instance_id,
            )
        return removed


__all__ = ["WorkflowComponentStore"]
