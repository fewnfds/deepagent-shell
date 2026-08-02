from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from agent_shell.provider_integrations import bundled_provider_ids

_registered_keys: set[str] = set()


def ensure_agent_shell_harness_profiles(model: object) -> None:
    """Disable the implicit general-purpose Subagent for supported Providers."""
    from deepagents import (
        GeneralPurposeSubagentProfile,
        HarnessProfile,
        register_harness_profile,
    )
    from deepagents._models import get_model_identifier, get_model_provider

    profile = HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)
    )
    keys = set(bundled_provider_ids())
    if isinstance(model, BaseChatModel):
        provider = get_model_provider(model)
        if provider:
            keys.add(provider)
            identifier = get_model_identifier(model)
            if identifier and ":" not in identifier:
                keys.add(f"{provider}:{identifier}")

    for key in keys - _registered_keys:
        register_harness_profile(key, profile)
        _registered_keys.add(key)
