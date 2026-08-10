from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware

from agent_shell.contracts import PromptCachingBlock


class _DisabledAnthropicPromptCachingMiddleware(AgentMiddleware):
    @property
    def name(self) -> str:
        return "AnthropicPromptCachingMiddleware"


def materialize_prompt_caching_middleware(
    block: PromptCachingBlock,
) -> AgentMiddleware:
    """Build the explicit Anthropic prompt-caching override for one profile."""

    if not block.enabled:
        return _DisabledAnthropicPromptCachingMiddleware()

    from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

    return AnthropicPromptCachingMiddleware(
        type=block.type,
        ttl=block.ttl,
        min_messages_to_cache=block.min_messages_to_cache,
        unsupported_model_behavior="ignore",
    )


__all__ = ["materialize_prompt_caching_middleware"]
