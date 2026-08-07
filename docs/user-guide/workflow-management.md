# Workflow 与 Auto 管理

管理台现在提供两个独立入口：

- `Workflow`：用后端节点目录编辑节点、端口连线和节点 JSON 配置。保存后可用聊天消息测试运行；远程模式需临时输入 API Key，密钥只保留在页面内存。运行响应中的普通结果与 artifact 事件保留在原始 JSON 中。
- `Auto`：编辑用户负责的 `route(messages)` Python 脚本。脚本返回 `{'kind': 'agent'|'workflow', 'public_id': 'agent-...'|'workflow-...'}`，管理台可调用 resolve 接口验证目标。

公开模型 ID 使用固定命名空间：Workflow 为 `workflow-<小写字母和横杠>`，Auto 为 `auto-<小写字母和横杠>`。名称为空或无法生成 ASCII slug 时，默认使用 `*-config`；用户手动修改后不会被名称变化覆盖。

当前编辑器是列表形式，不是拖拽画布。`layout` 字段仍按后端 Workflow DSL 保存，为后续画布提供稳定数据基础。节点插件、任意 Python 节点、CodeMirror 和 Vue Flow 不属于当前版本。
