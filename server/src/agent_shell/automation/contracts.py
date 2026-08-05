from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


PluginId = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$"),
]


class AutomationPluginBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    plugin_id: PluginId
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class PeriodicAutomationPluginBinding(AutomationPluginBinding):
    interval_seconds: float = Field(ge=0.1, le=86_400)


class PrimaryAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hooks: list[AutomationPluginBinding] = Field(default_factory=list, max_length=100)
    periodic: list[PeriodicAutomationPluginBinding] = Field(
        default_factory=list,
        max_length=100,
    )


class SubagentAutomation(PrimaryAutomation):
    pass
