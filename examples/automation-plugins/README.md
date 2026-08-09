# Automation plugin examples

Each child folder is a complete `api_version: 3` automation plugin. Copy one child
folder into the instance `data/resources/automation_scripts/` directory, or upload it
with the management file tool, then bind it to an Agent.

- `main-agent-message-injection` injects transformed client messages at the start of each
  Main Agent invocation through `AgentMiddleware.abefore_agent`.
- `subagent-message-injection` edits the current Subagent message list at the start
  of every real invocation through `AgentMiddleware.abefore_agent`.
- `subagent-filesystem-prompt-injection` reads grouped files from the current
  Subagent filesystem and inserts rendered assistant/user/system messages directly
  before the delegated task.

The two message-transform examples expose one Schema-driven Python field. The Main Agent
function receives a fresh mutable copy of the normalized client `messages[]`. The
Subagent function receives a deep copy of the current LangGraph `state["messages"]`;
its final item is normally the delegated task. Insert a new message at index `-1` to
place it before that task. Each function must return the complete ordered message
list. Images, audio, video, and files remain in their original content blocks; Agent
Shell does not unload them into `state["shared_vars"]` and does not rehydrate resource references.

The configured Python runs in the Agent Shell process with the same host permissions
as the plugin. It is not sandboxed. Import standard-library or declared plugin
requirements inside the function as needed. Coordinate writes outside the provided
invocation scratch directory yourself.

Both functions receive the current LangGraph `state` and `runtime`. The Subagent
function can obtain the current invocation identity from
`runtime.context["agent_shell_invocation"]`. Its binding-specific scratch directory is
available in that mapping's `workspaces` entry under
`f"hook:{ctx.plugin['binding_index']}"`.

Returning `[]` from the Main Agent transform skips client-message injection. Returning
`[]` from the Subagent transform intentionally clears the current invocation input.
The Subagent example rebuilds only the in-memory LangGraph message order from the
current state, so sequential bindings that each insert at `-1` produce
`[A, B, C, delegated task]` with one delegated task.

The filesystem example exposes one plain-text textarea. Its strict format is:

```ini
[group: cot]
[assistant]
# cot
[/draft/cot.md][1000]

[group: parts]
[assistant]
# part 1
[/draft/draft-1.md][1000]
[/output/output-1.md][1000]

[assistant]
# part 2
[/draft/draft-2.md][1000]
[/output/output-2.md][1000]
```

Every entry in one group must declare the same number of file layers. Layer 1 is the
unconditional baseline: missing files render as `缺失`, and short or missing baseline
files do not hide later entries. Starting at layer 2, a layer becomes active only when
every file in that group exists as UTF-8 text and meets its own minimum character
count. Validation stops at the first failed layer, so a later layer cannot skip over a
failed earlier one. Groups choose layers independently. If none of the configured
files exists, the plugin injects nothing. A configured `[system]` role is emitted as
`user` so the inserted message remains compatible with Providers that reject system
messages after ordinary conversation turns.
