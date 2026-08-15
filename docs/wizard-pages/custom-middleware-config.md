# 自定义 Middleware

每份自定义 Middleware 配置拥有一个独占的 `agent-middleware` 私有包：

```yaml
name: Request Middleware
python_package:
  folder: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa--request-middleware--bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
  config: {}
```

新建配置时，编辑器从 `data/templates/agent/custom_middleware/<template-key>/` 加载静态模板。首次保存会把模板完整复制到
`data/config/python_package_instances/agent-middleware/`，生成属于该配置的 `package.json` 和文件夹引用。此后配置只读取、
编辑自己的私有包，模板修改不会传播。

编辑器提供完整 `main.py`、`requirements.txt` 和 `config_schema` 生成的普通输入框。普通输入只更新
`python_package.config`；代码框保存对应文件。额外 Python 模块、vendor 目录和其他文件由用户直接在私有包文件夹维护，
编辑器不会解析或改写。

`main.py` 必须提供 `create_middleware(config, agent)`，并返回官方 LangChain `AgentMiddleware` 或非空列表/元组。这里的
`agent` 是只含 `id`、`type`、`name`、`package_id` 的 Agent Shell 身份字典，不是 LangChain Agent 对象。
包结构、模板/私有包生命周期、依赖与安全边界见[文件化 Python 扩展](../user-guide/middleware-packages.md)。

Subagent 可以按现有 capability 规则继承、替换或关闭整份 Custom Middleware 配置。无论由多少 Agent 使用，该组件始终只引用
自己的一个私有包；复制该组件会同时复制新的私有包。
