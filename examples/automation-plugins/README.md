# Automation plugin examples

Each child folder is a complete `api_version: 3` automation plugin. Copy one child
folder into the instance `data/resources/automation_scripts/` directory, or upload it
with the management file tool, then bind it to an Agent.

- `primary-message-injection` injects transformed client messages into each Primary
  request during `prepare`.
- `subagent-message-injection` injects transformed client messages at the start of
  every real Subagent invocation through `AgentMiddleware.abefore_agent`.

Both plugins expose one Schema-driven Python field. The default function returns the
complete normalized client `messages[]` unchanged. Its input is a fresh mutable copy,
so nested multimodal blocks can be edited without mutating `ctx.request.messages`.
Images, audio, video, and files remain in their original content blocks; Agent Shell
does not unload them into `ctx.vars` and does not rehydrate resource references.

The configured Python runs in the Agent Shell process with the same host permissions
as the plugin. It is not sandboxed. Import standard-library or declared plugin
requirements inside the function as needed. Coordinate writes outside the provided
invocation scratch directory yourself.

The Subagent function can obtain the current invocation identity from
`runtime.context["agent_shell_invocation"]`. Its binding-specific scratch directory is
available in that mapping's `workspaces` entry under
`f"hook:{ctx.plugin['binding_index']}"`. Primary `prepare` runs before the root graph
invocation exists, so its `state` and `runtime` arguments are `None`.

Returning `[]` skips client-message injection for that startup. For Subagents, the
parent-delegated task remains. After the function returns, leading contiguous system
messages remain system messages and any later system message is converted in place to
the user role for broader Provider compatibility. Other roles, floors, content blocks,
and scalar media values are preserved.
