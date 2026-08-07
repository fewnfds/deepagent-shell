# Workflow 管理

Workflow（工作流）是管理台保存的固定 Graph（图）定义：节点、控制连线、可选数据绑定和画布布局。Graph Definition（图定义）与 Graph Run（运行实例）分离；保存新 revision（修订版）不会改变已经运行的实例。

入口脚本（Entry Script）是 OpenAI-compatible API（兼容 OpenAI 的接口）的唯一模型选择键。用户自行填写名称，名称只能使用大写字母、小写字母和横杠，例如 `research-graph` 或 `Research-Graph`；平台不会自动添加 `agent-`、`workflow-`、`auto-` 前缀，也不再提供 Auto 路由对象。

入口脚本的可选 `prepare(messages)` 函数只负责把标准 Chat Completions 消息转换为本次 Graph 的初始 State（状态），例如写入 `shared` 或 `inputs`。节点如何读取、组装提示词和写回结果由节点自身决定。

管理台提供固定画布、节点目录、节点检查器和运行面板。运行面板通过管理 SSE（Server-Sent Events，服务器推送事件）显示节点状态，并提供暂停、继续和停止按钮；OpenAI 客户端仍然只是被动接收流。
