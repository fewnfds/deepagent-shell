from __future__ import annotations

import json

from agent_shell.storage.database import SQLiteDatabase


class ProviderCredentialError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(code)


class ProviderSecretResolver:
    """The only service allowed to return provider credential plaintext."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def resolve_model(self, block_id: str) -> str | None:
        with self._database.transaction() as connection:
            payload = self._stored_model_payload(connection, block_id)
            credential = payload.get("credential")
            return self._resolve_stored(connection, credential)

    def resolve_request(
        self,
        credential: str | None,
        *,
        provider: str,
        block_id: str = "",
        base_url: str = "",
    ) -> str | None:
        if credential is not None:
            return credential
        if not block_id:
            return None
        with self._database.transaction() as connection:
            payload = self._stored_model_payload(connection, block_id)
            stored_provider = payload.get("provider")
            stored_base_url = payload.get("base_url")
            if (
                stored_provider != provider
                or not isinstance(stored_base_url, str)
                or stored_base_url.rstrip("/") != base_url.rstrip("/")
            ):
                raise ProviderCredentialError(
                    "provider_credential_connection_changed",
                    "A saved credential cannot be reused for a different model connection.",
                )
            return self._resolve_stored(connection, payload.get("credential"))

    @staticmethod
    def _stored_model_payload(connection, block_id: str) -> dict:
        row = connection.execute(
            "SELECT payload FROM blocks WHERE id = ? AND block_type = 'model'",
            (block_id,),
        ).fetchone()
        if row is None:
            raise ProviderCredentialError(
                "model_not_found", "The model configuration does not exist."
            )
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProviderCredentialError(
                "provider_credential_invalid",
                "The model credential metadata is invalid.",
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderCredentialError(
                "provider_credential_invalid",
                "The model credential metadata is invalid.",
            )
        return payload

    @staticmethod
    def _resolve_stored(connection, credential: object) -> str | None:
        if credential is None:
            return None
        if not isinstance(credential, dict) or set(credential) != {"reference"}:
            raise ProviderCredentialError(
                "provider_credential_invalid",
                "The model credential metadata is invalid.",
            )
        reference = credential["reference"]
        if not isinstance(reference, str) or not reference:
            raise ProviderCredentialError(
                "provider_credential_invalid",
                "The model credential reference is invalid.",
            )
        row = connection.execute(
            "SELECT secret_value FROM provider_secrets WHERE id = ?", (reference,)
        ).fetchone()
        if row is None or not row["secret_value"]:
            raise ProviderCredentialError(
                "provider_secret_reference_missing",
                "The model credential reference is missing.",
            )
        return str(row["secret_value"])
