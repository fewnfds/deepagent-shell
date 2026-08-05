from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class HookAutomationOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["inherit", "replace", "disabled"] = "inherit"
    plugins: list[AutomationPluginBinding] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_selection(self) -> "HookAutomationOverride":
        if self.mode == "replace":
            if not self.plugins:
                raise ValueError("replace mode requires at least one plugin")
            return self
        if self.plugins:
            raise ValueError("only replace mode may contain plugins")
        return self


class PeriodicAutomationOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["inherit", "replace", "disabled"] = "inherit"
    plugins: list[PeriodicAutomationPluginBinding] = Field(
        default_factory=list,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_selection(self) -> "PeriodicAutomationOverride":
        if self.mode == "replace":
            if not self.plugins:
                raise ValueError("replace mode requires at least one plugin")
            return self
        if self.plugins:
            raise ValueError("only replace mode may contain plugins")
        return self


class SubagentAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hooks: HookAutomationOverride = Field(default_factory=HookAutomationOverride)
    periodic: PeriodicAutomationOverride = Field(
        default_factory=PeriodicAutomationOverride
    )
