# 自定义工具

页面扫描 `data/resources/custom_tools/*.py`，静态查找第一个带 `@tool` 或 `.tool` 装饰器的顶层函数。
扫描不 import 代码；语法、编码、文件名、说明或参数 schema 不合规时显示逐文件错误。

```json
{"name": "Writing tools", "tools": ["word_count", "local_search"]}
```

组件 YAML 保存资源名，最多 200 个。真实请求只物化当前 Agent 选择的资源：重新扫描、import、取得
`BaseTool` 并检查最终模型可见名称冲突。未选择的文件不会执行。依赖必须已经包含在发行 runtime 中；
管理台不安装 Python 包。Subagent 可继承、替换或关闭整份工具组件。
