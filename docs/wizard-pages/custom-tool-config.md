# 自定义工具

```json
{
  "name": "Writing tools",
  "tools": ["word_count", "local_search"]
}
```

页面扫描 `data/resources/custom_tools/*.py`，从每个文件中找到第一个带 `@tool` 或属性 `.tool`
装饰器的顶层同步/异步函数。可选项必须同时满足：文件资源名符合保存规则；函数提供 docstring
或显式 decorator `description`；每个输入参数有类型标注，或 decorator 显式提供 `args_schema`。
语法、编码、文件名或上述结构无效的文件不进入列表，而是显示在逐文件扫描错误中。扫描过程不
import 或执行代码；模型可见工具名采用 `snake_case` 是 LangChain 建议，不是本项目的硬拒绝规则。

资源名、Python 函数名和模型可见 Tool 名不是同一个字段。数据库只保存资源名；静态扫描另外返回
`function`，并在 `@tool` 使用函数默认名或字面量名称时返回 `tool_name`。保存、仓库和 API Server
启动只用 AST 能安全确定的 `tool_name` 检查冲突，不会把文件名误当 Tool 名；动态表达式名称和文件
后来变化仍在真实请求物化后检查。

`tools` 最多 200 项，名称匹配 `[A-Za-z_][A-Za-z0-9_-]*`，按首次出现去重并保留顺序。保存
不要求文件仍存在，所以配置可在资源临时缺失时继续查看。

真实请求只有在 Agent 选择本 block 后才：

1. 将资源名解析为同名 `.py` 文件；
2. 重新做静态扫描并 import 该文件；
3. 取得扫描到的函数绑定并校验为 LangChain `BaseTool`；
4. 以最终对象 `.name` 检查模型可见工具名冲突；
5. 按 block 顺序传入 `create_deep_agent(tools=...)`。

未选择或列表为空时不 import。Subagent 对整份 block 使用 inherit/replace/disabled。
Middleware 自带的工具不属于本 block。

数据库只保存资源名，不保存文件内容或 hash。每次新请求构造 Agent 时都重新扫描并 import 当时的
文件，所以保存后修改源码会在下一次请求生效；运行时还会检查导出对象确实是 `BaseTool`。

`GET /api/tools/custom` 与 Middleware/Skill 发现接口一样返回：

```json
{"catalog": [], "errors": {"bad name.py": "文件名去掉 .py 后必须……"}}
```

有效项包含 `name`（资源名）、`function`、`tool_name`、`description` 和 `filename`；静态无法确定
Tool 名时 `tool_name` 为 `null`，不因此拒绝保存。
