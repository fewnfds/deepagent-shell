from __future__ import annotations

from agent_shell.storage.file_config import FileConfigRepository


class ProviderCredentialError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(code)


class ProviderSecretResolver:
    """The only service allowed to return provider credential plaintext."""

    def __init__(self, repository: FileConfigRepository) -> None:
        self._repository = repository

    def _stored_model(self, block_id: str) -> dict:
        for item in self._repository.config().get("components", {}).get("model", []):
            if item.get("id") == block_id:
                return item
        raise ProviderCredentialError("model_not_found", "The model configuration does not exist.")

    def resolve_model(self, block_id: str) -> str | None:
        payload = self._stored_model(block_id)
        credential = payload.get("credential")
        if credential is None:
            return None
        if not isinstance(credential, dict) or set(credential) != {"reference"}:
            raise ProviderCredentialError("provider_credential_invalid", "The model credential metadata is invalid.")
        reference = credential.get("reference")
        if not isinstance(reference, str) or not reference:
            raise ProviderCredentialError("provider_credential_invalid", "The model credential reference is invalid.")
        value = self._repository.secret(reference)
        if not value:
            raise ProviderCredentialError("provider_secret_reference_missing", "The model credential reference is missing.")
        return value

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
        payload = self._stored_model(block_id)
        if payload.get("provider") != provider or str(payload.get("base_url", "")).rstrip("/") != base_url.rstrip("/"):
            raise ProviderCredentialError(
                "provider_credential_connection_changed",
                "A saved credential cannot be reused for a different model connection.",
            )
        return self.resolve_model(block_id)
