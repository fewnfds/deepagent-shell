# 自定义 Middleware

每份自定义 Middleware 配置拥有一个独占的 `agent-middleware` Python 扩展：

```yaml
name: Request Middleware
python_package:
  folder: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  editable_files:
    - main.py
```

新建配置时，可以从 `data/templates/agent/custom_middleware/<template-key>/` 加载静态模板，也可以【套用空模板】从空的
`main.py` 开始编辑。首次保存会把当前草稿写入
`data/config/python_package_instances/agent-middleware/`，生成属于该配置的 `package.json` 和文件夹引用。此后配置只读取、
编辑自己的扩展代码目录，模板修改不会传播。

编辑器默认显示 `main.py`。用户可以逐行增加包内相对文件路径；编辑器按清单顺序显示并保存这些文本文件。
不存在的文件只显示警告，填写内容并保存后创建；未列出的额外文件保持原样。

`main.py` 必须提供 `create_middleware(agent)`，并且只返回一个官方 LangChain `AgentMiddleware`。一个 Middleware 类可以实现
多个官方 hook；这些 hook 属于同一个实例，不单独排序。这里的
`agent` 是只含 `id`、`type`、`name`、`package_id` 的 Agent Shell 身份字典，不是 LangChain Agent 对象。
目录结构、扩展模板/配置扩展生命周期、依赖与安全边界见[文件化 Python 扩展](../user-guide/middleware-packages.md)。

每份 Custom Middleware 配置只定义一个 Middleware。Main Agent 和 Subagent 分别保存自己的有序 `middleware_refs`，按列表
顺序装配多个配置；它不再进入 capability 的继承、替换或关闭规则。复制该组件会同时复制新的扩展代码目录。

排序遵循 LangChain 官方 middleware 列表语义：`before_*` 按列表从前到后执行，`after_*` 按列表从后到前执行，
`wrap_*` 按列表形成嵌套调用。管理台调整的是 Middleware 实例顺序，不对同一实例内部的多个 hook 分别排序。
