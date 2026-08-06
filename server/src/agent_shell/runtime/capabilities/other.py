from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware

from agent_shell.contracts import OtherBlock, SummarizationThreshold


class _DisabledSummarizationMiddleware(AgentMiddleware):
    @property
    def name(self) -> str:
        return "SummarizationMiddleware"


class _DisabledAnthropicPromptCachingMiddleware(AgentMiddleware):
    @property
    def name(self) -> str:
        return "AnthropicPromptCachingMiddleware"


def _threshold(
    value: SummarizationThreshold,
    fallback: tuple[str, int | float],
) -> tuple[str, int | float]:
    if value.type == "auto":
        return fallback
    assert value.value is not None
    return (value.type, value.value)


def materialize_other_middlewares(
    block: OtherBlock,
    *,
    model: Any,
    backend: Any,
) -> tuple[AgentMiddleware, ...]:
    """Replace Deep Agents' implicit middleware with the configured instances."""

    middleware: list[AgentMiddleware] = []
    summarization = block.summarization
    if not summarization.enabled:
        middleware.append(_DisabledSummarizationMiddleware())
    else:
        from deepagents.middleware.summarization import (
            SummarizationMiddleware,
            compute_summarization_defaults,
        )

        defaults = compute_summarization_defaults(model)
        truncate_defaults = defaults["truncate_args_settings"]
        truncate_args_settings = None
        if summarization.truncate_args_enabled:
            truncate_args_settings = {
                "trigger": _threshold(
                    summarization.truncate_args_trigger,
                    truncate_defaults["trigger"],
                ),
                "keep": _threshold(
                    summarization.truncate_args_keep,
                    truncate_defaults["keep"],
                ),
                "max_length": summarization.truncate_args_max_length,
                "truncation_text": summarization.truncate_args_text,
            }
        summarization_kwargs: dict[str, Any] = {
            "model": model,
            "backend": backend,
            "trigger": _threshold(summarization.trigger, defaults["trigger"]),
            "keep": _threshold(summarization.keep, defaults["keep"]),
            "trim_tokens_to_summarize": summarization.trim_tokens_to_summarize,
            "truncate_args_settings": truncate_args_settings,
        }
        if summarization.summary_prompt_override is not None:
            summarization_kwargs["summary_prompt"] = (
                summarization.summary_prompt_override
            )
        middleware.append(SummarizationMiddleware(**summarization_kwargs))

    prompt_caching = block.prompt_caching
    if not prompt_caching.enabled:
        middleware.append(_DisabledAnthropicPromptCachingMiddleware())
    else:
        from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

        middleware.append(
            AnthropicPromptCachingMiddleware(
                type=prompt_caching.type,
                ttl=prompt_caching.ttl,
                min_messages_to_cache=prompt_caching.min_messages_to_cache,
                unsupported_model_behavior="ignore",
            )
        )
    return tuple(middleware)


__all__ = ["materialize_other_middlewares"]
