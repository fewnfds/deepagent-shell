# Rule-based Command

这是 Command Node 的可修改示例。示例读取 `state["shared_vars"]["score"]`，分数不低于 `60` 时激活 `matched`，
否则激活 `below_threshold`，并通过 `update` 记录 `shared_vars.last_route`。这些字段、规则和更新都不是平台要求，应按当前
Workflow 的真实 State contract 修改。

画布为该 Command 建立两条 Branch Edge，并分别填写 `branch_key=matched` 与 `branch_key=below_threshold`。

## 稳定 contract

- `create_command()` 是无参数同步工厂；
- 工厂返回固定签名的 `async command(state, runtime)`；
- `command` 可以读取完整 Workflow State、官方 Runtime Context 和 Store；
- `activate` 只包含画布 Branch Edge key，不包含 Node ID；
- `update` 是正式能力，可以更新当前 Workflow State 已声明的任意顶层 channel，也可以返回空对象；
- package 不 import 或返回 LangGraph `Command`。

按业务需要选择 `state`、`runtime.context` 或 `runtime.store` 中的输入。要并行激活多个目标，可以在 `activate` 中返回多个
不同 key；返回空列表时只提交 `update`，当前路径在该节点自然结束。

模板只使用 Python 标准语法，`requirements.txt` 保持为空。
