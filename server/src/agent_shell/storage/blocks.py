from __future__ import annotations

from copy import deepcopy

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.storage.file_config import FileConfigRepository
from agent_shell.storage.reference_mutations import detach_agent_block_references


class BlockStore:
    def __init__(
        self,
        repository: FileConfigRepository,
        event_logger: SecurityEventLogger | None = None,
    ) -> None:
        self._repository = repository
        self._events = event_logger

    @staticmethod
    def _records(config: dict, block_type: str) -> list[dict]:
        components = config.setdefault("components", {})
        records = components.setdefault(block_type, [])
        if not isinstance(records, list):
            raise ValueError(f"component section must be a list: {block_type}")
        return records

    @staticmethod
    def _public_model(block: dict, repository: FileConfigRepository) -> dict:
        public = deepcopy(block)
        credential = block.get("credential")
        reference = (
            credential.get("reference")
            if isinstance(credential, dict)
            else None
        )
        public["credential"] = {
            "status": "masked"
            if isinstance(reference, str) and repository.secret(reference)
            else "missing"
        }
        return public

    def _public(self, block_type: str, block: dict) -> dict:
        return (
            self._public_model(block, self._repository)
            if block_type == "model"
            else deepcopy(block)
        )

    def list_blocks(self, block_type: str) -> list[dict]:
        config = self._repository.config()
        records = sorted(
            self._records(config, block_type),
            key=lambda value: (str(value.get("name", "")).casefold(), str(value.get("id", ""))),
        )
        return [self._public(block_type, record) for record in records]

    def list_blocks_internal(self, block_type: str) -> list[dict]:
        config = self._repository.config()
        return [deepcopy(record) for record in self._records(config, block_type)]

    def list_block_headers(self) -> list[dict[str, str]]:
        config = self._repository.config()
        headers: list[dict[str, str]] = []
        for block_type, records in config.get("components", {}).items():
            if not isinstance(records, list):
                continue
            for record in records:
                if isinstance(record, dict):
                    headers.append(
                        {
                            "id": str(record.get("id", "")),
                            "block_type": str(block_type),
                            "name": str(record.get("name", "")),
                        }
                    )
        return sorted(headers, key=lambda value: (value["block_type"], value["name"].casefold(), value["id"]))

    def get_block_header(self, block_id: str) -> dict[str, str] | None:
        for header in self.list_block_headers():
            if header["id"] == block_id:
                return header
        return None

    def get_block(self, block_type: str, block_id: str) -> dict | None:
        config = self._repository.config()
        for record in self._records(config, block_type):
            if record.get("id") == block_id:
                return self._public(block_type, record)
        return None

    def get_block_internal(self, block_type: str, block_id: str) -> dict | None:
        config = self._repository.config()
        for record in self._records(config, block_type):
            if record.get("id") == block_id:
                return deepcopy(record)
        return None

    @staticmethod
    def _credential_reference(payload: dict) -> str:
        credential = payload.get("credential")
        if isinstance(credential, dict) and isinstance(credential.get("reference"), str):
            return credential["reference"]
        return ""

    @staticmethod
    def _model_secret_name(block_id: str) -> str:
        return f"AGENT_SHELL_MODEL_{block_id.replace('-', '').upper()}_API_KEY"

    def save_block(self, block_type: str, block_id: str, data: dict) -> None:
        name = data["name"]
        existing: dict | None = None
        old_reference = ""
        new_secret: tuple[str, str] | None = None
        clear_secret: str | None = None

        def mutate(config: dict) -> None:
            nonlocal existing, old_reference, new_secret, clear_secret
            records = self._records(config, block_type)
            for record in records:
                if record.get("id") == block_id:
                    existing = deepcopy(record)
                if record.get("name") == name and record.get("id") != block_id:
                    raise ValueError(f"名称「{name}」已存在")
            stored = {key: deepcopy(value) for key, value in data.items() if key != "name"}
            if block_type == "model":
                old_reference = self._credential_reference(existing or {})
                credential_value = stored.pop("credential", None)
                reuse = bool(
                    existing
                    and existing.get("provider") == stored.get("provider")
                    and existing.get("base_url") == stored.get("base_url")
                    and stored.get("provider") != "google_vertexai"
                )
                if credential_value is None and reuse and old_reference:
                    stored["credential"] = {"reference": old_reference}
                elif credential_value is None:
                    stored["credential"] = None
                    if old_reference:
                        clear_secret = old_reference
                else:
                    reference = old_reference if reuse and old_reference else self._model_secret_name(block_id)
                    stored["credential"] = {"reference": reference}
                    new_secret = (reference, str(credential_value))
                    if old_reference and old_reference != reference:
                        clear_secret = old_reference
            stored["id"] = block_id
            stored["name"] = name
            replaced = False
            for index, record in enumerate(records):
                if record.get("id") == block_id:
                    records[index] = stored
                    replaced = True
                    break
            if not replaced:
                records.append(stored)

        self._repository.update_config(mutate)
        if new_secret is not None:
            self._repository.set_secret(*new_secret)
        if clear_secret and clear_secret != (new_secret[0] if new_secret else None):
            self._repository.set_secret(clear_secret, None)
        emit_configuration_events(
            self._events,
            action="updated" if existing is not None else "created",
            entity="block",
            entity_id=block_id,
            capability_type=block_type,
        )
        if self._events is not None and block_type == "model":
            if new_secret is not None:
                self._events.emit("provider_secret_rotated", {"block_id": block_id})
            if clear_secret:
                self._events.emit(
                    "provider_secret_cleared",
                    {"block_id": block_id, "reason": "replaced" if new_secret else "connection_changed"},
                )

    def copy_block(
        self,
        block_type: str,
        source_id: str,
        new_id: str,
        name: str,
        *,
        source: dict | None = None,
    ) -> dict | None:
        source_record = source or self.get_block_internal(block_type, source_id)
        if source_record is None:
            return None
        if any(item.get("name") == name for item in self.list_blocks_internal(block_type)):
            raise ValueError(f"名称「{name}」已存在")
        copied = deepcopy(source_record)
        copied["id"] = new_id
        copied["name"] = name

        def mutate(config: dict) -> None:
            self._records(config, block_type).append(copied)

        self._repository.update_config(mutate)
        emit_configuration_events(
            self._events,
            action="copied",
            entity="block",
            entity_id=new_id,
            capability_type=block_type,
        )
        return self.get_block(block_type, new_id)

    def delete_blocks(self, block_type: str, block_ids: list[str], *, detach_references: bool = False) -> int:
        unique_ids = list(dict.fromkeys(block_ids))
        if not unique_ids:
            return 0
        removed: list[dict] = []

        def mutate(config: dict) -> None:
            records = self._records(config, block_type)
            retained: list[dict] = []
            for record in records:
                if record.get("id") in unique_ids:
                    removed.append(deepcopy(record))
                else:
                    retained.append(record)
            config.setdefault("components", {})[block_type] = retained
            if detach_references:
                detach_agent_block_references(config, block_type, set(unique_ids))

        self._repository.update_config(mutate)
        active_refs = {
            self._credential_reference(record)
            for record in self.list_blocks_internal("model")
        }
        for record in removed:
            reference = self._credential_reference(record)
            if reference and reference not in active_refs:
                self._repository.set_secret(reference, None)
            emit_configuration_events(
                self._events,
                action="deleted",
                entity="block",
                entity_id=str(record.get("id", "")),
                capability_type=block_type,
            )
        return len(removed)

    def delete_block(self, block_type: str, block_id: str, *, detach_references: bool = False) -> bool:
        return self.delete_blocks(block_type, [block_id], detach_references=detach_references) == 1
