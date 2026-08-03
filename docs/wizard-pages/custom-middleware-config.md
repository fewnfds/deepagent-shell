# 自定义 Middleware

一条组件保存最多 100 个有序 Python 构造项：

```json
{
  "name": "可靠性中间件",
  "middlewares": [{
    "name": "工具重试",
    "enabled": true,
    "source": "from langchain.agents.middleware import ToolRetryMiddleware\n\nmiddleware = ToolRetryMiddleware(max_retries=3)"
  }]
}
```

每段源码最多 100,000 字符，执行后必须在顶层绑定一个 `AgentMiddleware`，或由它们组成的 list/tuple。
enabled 项按保存顺序执行和展平；不同项使用独立 namespace。运行名称必须唯一。

`data/resources/custom_middlewares/*.py` 只作为可复制模板目录，发现阶段仅做 UTF-8 与 AST 检查。
源码会在真实请求中执行，不要写入 secret。Subagent 可继承、替换或关闭整份组件。
