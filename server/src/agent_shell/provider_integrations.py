from __future__ import annotations

import importlib.metadata
import re
from dataclasses import dataclass

_PACKAGE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_BUNDLED_PROVIDER_IDS = frozenset(
    {
        "anthropic",
        "deepseek",
        "google_genai",
        "google_vertexai",
        "openai",
        "xai",
    }
)

_DEEPAGENT_HARNESS_PROFILES_CONFIGURED = False


@dataclass(frozen=True, slots=True)
class ProviderIntegration:
    provider: str
    package: str
    module: str
    class_name: str


def official_provider_integrations() -> tuple[ProviderIntegration, ...]:
    """Read the Provider registry owned by the pinned LangChain version."""

    from langchain.chat_models import base as chat_models_base

    registry = getattr(chat_models_base, "_BUILTIN_PROVIDERS", None)
    if not isinstance(registry, dict):
        raise RuntimeError("The installed LangChain Provider registry is unavailable.")
    integrations = []
    for provider, entry in registry.items():
        if (
            not isinstance(provider, str)
            or not isinstance(entry, tuple)
            or len(entry) != 3
        ):
            continue
        module, class_name, _creator = entry
        if not isinstance(module, str) or not isinstance(class_name, str):
            continue
        package = module.partition(".")[0].replace("_", "-")
        if not _PACKAGE_RE.fullmatch(package):
            continue
        integrations.append(
            ProviderIntegration(
                provider=provider,
                package=package,
                module=module,
                class_name=class_name,
            )
        )
    return tuple(sorted(integrations, key=lambda item: item.provider))


def bundled_provider_integrations() -> tuple[ProviderIntegration, ...]:
    integrations = {
        item.provider: item for item in official_provider_integrations()
    }
    missing = _BUNDLED_PROVIDER_IDS - integrations.keys()
    if missing:
        raise RuntimeError(
            "Bundled Providers are absent from the installed LangChain registry: "
            + ", ".join(sorted(missing))
        )
    return tuple(integrations[provider] for provider in sorted(_BUNDLED_PROVIDER_IDS))


def bundled_provider_ids() -> frozenset[str]:
    return frozenset(item.provider for item in bundled_provider_integrations())


def configure_deepagent_harness_profiles() -> None:
    """Disable Deep Agents' implicit general-purpose Subagent for this product.

    The management contract enables synchronous delegation only when a Primary
    explicitly binds it. Deep Agents 0.7 otherwise adds a ``task`` tool even
    when ``subagents=[]``. Provider-wide registration is process configuration,
    not request state, and preserves any upstream profile fields by using the
    official additive registry.
    """

    global _DEEPAGENT_HARNESS_PROFILES_CONFIGURED
    if _DEEPAGENT_HARNESS_PROFILES_CONFIGURED:
        return
    from deepagents import (
        GeneralPurposeSubagentProfile,
        HarnessProfile,
        register_harness_profile,
    )

    profile = HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)
    )
    for provider in sorted(_BUNDLED_PROVIDER_IDS):
        register_harness_profile(provider, profile)
    _DEEPAGENT_HARNESS_PROFILES_CONFIGURED = True


def _distribution_snapshot() -> dict[str, str]:
    installed = {}
    for distribution in importlib.metadata.distributions():
        name = str(distribution.metadata.get("Name") or "").lower()
        if name and _PACKAGE_RE.fullmatch(name):
            installed[name] = distribution.version
    return installed


def provider_catalog() -> dict[str, object]:
    installed = _distribution_snapshot()
    providers = []
    for integration in bundled_provider_integrations():
        version = installed.get(integration.package.lower())
        providers.append(
            {
                "provider": integration.provider,
                "package": integration.package,
                "class_name": integration.class_name,
                "installed": version is not None,
                "version": version,
                "documentation_url": (
                    "https://docs.langchain.com/oss/python/integrations/providers/overview"
                ),
            }
        )
    return {
        "langchain_version": installed.get("langchain", ""),
        "providers": providers,
    }
