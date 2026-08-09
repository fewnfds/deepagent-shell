# Custom Middleware package examples

Each child folder is a complete `api_version: 1` custom Middleware package. Copy one
child folder into `data/resources/custom_middlewares/`, then select it in a Custom
Middleware component attached to a Main Agent or inherited by a direct Subagent.

- `main-agent-message-injection` transforms the immutable OpenAI-compatible request
  messages in `AgentMiddleware.abefore_agent`.
- `subagent-message-injection` transforms Deep Agents' delegated Subagent messages.
- `subagent-filesystem-prompt-injection` reads grouped files from shared Agent state or
  configured mapped paths and inserts messages before the delegated task.

Every package contains `middleware.json` and `main.py`. `main.py` exports exactly one
synchronous factory:

```python
def create_middleware(ctx) -> AgentMiddleware | list[AgentMiddleware]:
    ...
```

The returned objects are ordinary LangChain `AgentMiddleware` instances. LangChain
owns their hooks, state updates, tools, `Command` values, reducers, and failures.
Agent Shell only discovers the package, validates configuration, prepares optional
`requirements.txt` dependencies, builds request-local context, and imports the factory.

The package runs in the Agent Shell process and is not sandboxed. Business data that
must survive checkpoints belongs in graph state. Package context is construction
metadata: immutable request input, Agent identity, configuration, package files,
request-local runtime files, and configured mapped paths.

The filesystem example accepts this layout:

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
```

Every entry in one group declares the same number of file layers. Layer 1 is the
baseline. Later layers become active in order only when every file in that group exists
as UTF-8 text and meets its minimum character count.
